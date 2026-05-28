import asyncio
import base64
import json
import logging
import os
from collections import deque
from typing import List, Optional, Tuple

import anthropic
from telegram import Update
from telegram.ext import ContextTypes

from core.auth import auth
from core.config import WORK_DIR
from core.memory import load_memory, save_memory
from core.utils import send_long_message

logger = logging.getLogger(__name__)

_claude_sessions = {}
_chat_history = {}
_msg_responses = {}
_MSG_RESPONSES_CAP = 200

_CLAUDE_HARD_TIMEOUT_S = 1800
_PROGRESS_INTERVAL_S = 30
_SYSTEM_PROMPT_BASE = (
    "Be efficient: batch multiple independent tool calls in a single turn. "
    "For example, read multiple files at once, or make multiple edits at once. "
    "Minimize total turns used."
)


def _record_response(sent_msgs, response: str) -> None:
    for msg in sent_msgs:
        _msg_responses[msg.message_id] = response
    if len(_msg_responses) > _MSG_RESPONSES_CAP:
        oldest_keys = sorted(_msg_responses)[:len(_msg_responses) - _MSG_RESPONSES_CAP]
        for k in oldest_keys:
            del _msg_responses[k]


async def _call_claude_vision(img_b64: str, prompt: str, model: str, max_tokens: int) -> str:
    client = anthropic.Anthropic()
    loop = asyncio.get_running_loop()

    def _call():
        return client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": img_b64}},
                    {"type": "text", "text": prompt},
                ],
            }],
        )

    result = await loop.run_in_executor(None, _call)
    return result.content[0].text


async def _describe_image(bot, file_id: str, caption: str = "") -> str:
    photo_file = await bot.get_file(file_id)
    img_bytes = await photo_file.download_as_bytearray()
    img_b64 = base64.standard_b64encode(bytes(img_bytes)).decode()
    prompt = caption or "Describe this image concisely in 1-3 sentences."
    text = await _call_claude_vision(img_b64, prompt, "claude-haiku-4-5-20251001", 256)
    return text.strip()


@auth
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = update.message.photo[-1]
    caption = update.message.caption or "What do you see in this image?"
    thinking_msg = await update.message.reply_text("Processing image...")
    try:
        photo_file = await context.bot.get_file(photo.file_id)
        img_bytes = await photo_file.download_as_bytearray()
        img_b64 = base64.standard_b64encode(bytes(img_bytes)).decode()
        response = await _call_claude_vision(img_b64, caption, "claude-sonnet-4-6", 4096)
        user_id = update.effective_user.id
        await thinking_msg.delete()
        sent_msgs = await send_long_message(update, response)
        _record_response(sent_msgs, response)

        if user_id not in _chat_history:
            _chat_history[user_id] = deque(maxlen=3)
        _chat_history[user_id].append({"user": f"[image] {caption}", "assistant": response[:1000]})
        asyncio.create_task(save_memory(f"[image] {caption}", response))
    except Exception as e:
        await thinking_msg.edit_text(f"Error processing image: {e}")


async def _build_reply_chain(message, bot, max_depth: int = 5) -> List[str]:
    """Walk the reply_to_message chain and return role-labeled context strings, oldest first."""
    chain = []
    msg = message.reply_to_message
    while msg and len(chain) < max_depth:
        if msg.message_id in _msg_responses:
            chain.append(f"Assistant: {_msg_responses[msg.message_id][:800]}")
        elif msg.photo:
            cap = msg.caption or ""
            try:
                desc = await _describe_image(bot, msg.photo[-1].file_id, cap)
                role = "Assistant" if msg.from_user and msg.from_user.is_bot else "User"
                chain.append(f"{role}: [Image: {desc}]")
            except Exception:
                chain.append("User: [Image: unable to describe]")
        elif msg.text:
            role = "Assistant" if msg.from_user and msg.from_user.is_bot else "User"
            chain.append(f"{role}: {msg.text[:800]}")
        msg = msg.reply_to_message
    chain.reverse()
    return chain


def _format_history(user_id: int) -> str:
    """Render the recent rolling conversation history for a user."""
    history = _chat_history.get(user_id, [])
    if not history:
        return ""
    lines = []
    for h in history:
        lines.append(f"User: {h['user'][:300]}")
        lines.append(f"Assistant: {h['assistant'][:500]}")
    return "\n".join(lines)


async def _build_context(update: Update, context: ContextTypes.DEFAULT_TYPE, user_msg: str) -> Tuple[str, str]:
    """Build (full_prompt, system_extra) for the next Claude call."""
    context_parts = []

    reply_chain = await _build_reply_chain(update.message, context.bot)
    if reply_chain:
        context_parts.append("[Reply thread context]\n" + "\n".join(reply_chain))

    history_text = _format_history(update.effective_user.id)
    if history_text:
        context_parts.append("[Recent conversation history]\n" + history_text)

    if context_parts:
        full_prompt = "\n\n".join(context_parts) + f"\n\n[Current message]\nUser: {user_msg}"
    else:
        full_prompt = user_msg

    memory = await load_memory(user_msg)
    system_extra = f"{memory}\n\n{_SYSTEM_PROMPT_BASE}" if memory else _SYSTEM_PROMPT_BASE
    return full_prompt, system_extra


async def _invoke_claude(prompt: str, system_extra: str, session_id: Optional[str], thinking_msg) -> Tuple[str, Optional[str], bytes]:
    """Spawn the Claude CLI subprocess, edit the thinking message with progress, and return
    (response_text, new_session_id_or_None, stderr_bytes).

    Raises asyncio.TimeoutError after _CLAUDE_HARD_TIMEOUT_S; kills the subprocess on timeout.
    """
    cmd = ["claude", "--print", "--max-turns", "200",
           "--output-format", "json",
           "--model", "sonnet",
           "--dangerously-skip-permissions",
           "--add-dir", os.path.expanduser("~/works"),
           "--append-system-prompt", system_extra]
    if session_id:
        cmd += ["--resume", session_id, "-p", prompt]
    else:
        cmd += ["-p", prompt]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=os.path.abspath(WORK_DIR),
    )

    elapsed = 0
    while True:
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=_PROGRESS_INTERVAL_S)
            break
        except asyncio.TimeoutError:
            elapsed += _PROGRESS_INTERVAL_S
            if elapsed >= _CLAUDE_HARD_TIMEOUT_S:
                proc.kill()
                await proc.wait()
                raise
            mins, secs = divmod(elapsed, 60)
            dots = "." * ((elapsed // _PROGRESS_INTERVAL_S) % 3 + 1)
            time_str = f"{mins}m{secs:02d}s" if mins else f"{secs}s"
            await thinking_msg.edit_text(f"Still thinking{dots} ({time_str})")

    raw = stdout.decode().strip()
    response = raw
    new_session_id = None
    try:
        data = json.loads(raw)
        response = data.get("result", raw)
        sid = data.get("session_id", "")
        new_session_id = sid or None
    except (json.JSONDecodeError, AttributeError):
        pass

    return response, new_session_id, stderr


async def _finalize(update: Update, response: str, user_msg: str, thinking_msg) -> None:
    """Deliver the response, update local caches, and schedule memory save."""
    await thinking_msg.delete()
    sent_msgs = await send_long_message(update, response)
    _record_response(sent_msgs, response)

    user_id = update.effective_user.id
    if user_id not in _chat_history:
        _chat_history[user_id] = deque(maxlen=3)
    _chat_history[user_id].append({"user": user_msg, "assistant": response[:1000]})
    asyncio.create_task(save_memory(user_msg, response))


async def _run_chat(update: Update, context: ContextTypes.DEFAULT_TYPE, user_msg: str, resume: bool):
    thinking_msg = await update.message.reply_text("Thinking...")
    try:
        user_id = update.effective_user.id
        session_id = _claude_sessions.get(user_id) if resume else None

        full_prompt, system_extra = await _build_context(update, context, user_msg)
        response, new_session_id, stderr = await _invoke_claude(
            full_prompt, system_extra, session_id, thinking_msg,
        )

        if new_session_id:
            _claude_sessions[user_id] = new_session_id

        if not response:
            logger.warning("Claude returned no output. stderr: %s", stderr.decode().strip())
            response = "(no output from Claude)"

        await _finalize(update, response, user_msg, thinking_msg)
    except asyncio.TimeoutError:
        await thinking_msg.edit_text("Claude timed out after 30 minutes.")
    except FileNotFoundError:
        await update.message.reply_text("Claude CLI not found. Make sure 'claude' is in PATH.")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


@auth
async def handle_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_msg = update.message.text
    if not user_msg:
        return
    await _run_chat(update, context, user_msg, resume=False)


@auth
async def cmd_new_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _claude_sessions.pop(update.effective_user.id, None)
    await update.message.reply_text("Started a new conversation.")


@auth
async def cmd_continue_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_msg = " ".join(context.args).strip() if context.args else "continue"
    await _run_chat(update, context, user_msg, resume=True)
