import asyncio
import base64
import json
import logging
import os
from collections import deque

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


async def _describe_image(bot, file_id: str, caption: str = "") -> str:
    photo_file = await bot.get_file(file_id)
    img_bytes = await photo_file.download_as_bytearray()
    img_b64 = base64.standard_b64encode(bytes(img_bytes)).decode()
    prompt = caption or "Describe this image concisely in 1-3 sentences."
    client = anthropic.Anthropic()
    loop = asyncio.get_event_loop()

    def _call():
        return client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=256,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": img_b64}},
                    {"type": "text", "text": prompt},
                ],
            }],
        )

    result = await loop.run_in_executor(None, _call)
    return result.content[0].text.strip()


@auth
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = update.message.photo[-1]
    caption = update.message.caption or "What do you see in this image?"
    thinking_msg = await update.message.reply_text("Processing image...")
    try:
        photo_file = await context.bot.get_file(photo.file_id)
        img_bytes = await photo_file.download_as_bytearray()
        img_b64 = base64.standard_b64encode(bytes(img_bytes)).decode()
        client = anthropic.Anthropic()
        loop = asyncio.get_event_loop()

        def _call():
            return client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=4096,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": img_b64}},
                        {"type": "text", "text": caption},
                    ],
                }],
            )

        result = await loop.run_in_executor(None, _call)
        response = result.content[0].text
        user_id = update.effective_user.id
        await thinking_msg.delete()
        sent_msgs = await send_long_message(update, response)

        for msg in sent_msgs:
            _msg_responses[msg.message_id] = response
        if len(_msg_responses) > 200:
            oldest_keys = sorted(_msg_responses)[:len(_msg_responses) - 200]
            for k in oldest_keys:
                del _msg_responses[k]

        if user_id not in _chat_history:
            _chat_history[user_id] = deque(maxlen=3)
        _chat_history[user_id].append({"user": f"[image] {caption}", "assistant": response[:1000]})
        asyncio.create_task(save_memory(f"[image] {caption}", response))
    except Exception as e:
        await thinking_msg.edit_text(f"Error processing image: {e}")


@auth
async def handle_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_msg = update.message.text
    if not user_msg:
        return

    resume = False
    if user_msg.strip().lower().startswith("/continue"):
        user_msg = user_msg.strip()[len("/continue"):].strip()
        resume = True
        if not user_msg:
            user_msg = "continue"

    if user_msg.strip().lower() == "/new":
        _claude_sessions.pop(update.effective_user.id, None)
        await update.message.reply_text("Started a new conversation.")
        return

    thinking_msg = await update.message.reply_text("Thinking...")
    proc = None
    try:
        user_id = update.effective_user.id
        session_id = _claude_sessions.get(user_id) if resume else None

        context_parts = []
        reply_chain = []
        msg = update.message.reply_to_message
        while msg and len(reply_chain) < 5:
            if msg.message_id in _msg_responses:
                reply_chain.append(f"Assistant: {_msg_responses[msg.message_id][:800]}")
            elif msg.photo:
                cap = msg.caption or ""
                try:
                    desc = await _describe_image(context.bot, msg.photo[-1].file_id, cap)
                    role = "Assistant" if msg.from_user and msg.from_user.is_bot else "User"
                    reply_chain.append(f"{role}: [Image: {desc}]")
                except Exception:
                    reply_chain.append("User: [Image: unable to describe]")
            elif msg.text:
                role = "Assistant" if msg.from_user and msg.from_user.is_bot else "User"
                reply_chain.append(f"{role}: {msg.text[:800]}")
            msg = msg.reply_to_message

        if reply_chain:
            reply_chain.reverse()
            context_parts.append("[Reply thread context]\n" + "\n".join(reply_chain))

        history = _chat_history.get(user_id, [])
        if history:
            conv_lines = []
            for h in history:
                conv_lines.append(f"User: {h['user'][:300]}")
                conv_lines.append(f"Assistant: {h['assistant'][:500]}")
            context_parts.append("[Recent conversation history]\n" + "\n".join(conv_lines))

        if context_parts:
            full_prompt = "\n\n".join(context_parts) + f"\n\n[Current message]\nUser: {user_msg}"
        else:
            full_prompt = user_msg

        memory = await load_memory(user_msg)
        system_extra = (
            "Be efficient: batch multiple independent tool calls in a single turn. "
            "For example, read multiple files at once, or make multiple edits at once. "
            "Minimize total turns used."
        )
        if memory:
            system_extra = f"{memory}\n\n{system_extra}"

        cmd = ["claude", "--print", "--max-turns", "200",
               "--output-format", "json",
               "--model", "sonnet",
               "--dangerously-skip-permissions",
               "--add-dir", os.path.expanduser("~/works"),
               "--append-system-prompt", system_extra]
        if session_id:
            cmd += ["--resume", session_id, "-p", full_prompt]
        else:
            cmd += ["-p", full_prompt]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=os.path.abspath(WORK_DIR),
        )
        elapsed = 0
        interval = 30
        while True:
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=interval)
                break
            except asyncio.TimeoutError:
                elapsed += interval
                if elapsed >= 1800:
                    raise
                mins = elapsed // 60
                secs = elapsed % 60
                dots = "." * ((elapsed // interval) % 3 + 1)
                time_str = f"{mins}m{secs:02d}s" if mins else f"{secs}s"
                await thinking_msg.edit_text(f"Still thinking{dots} ({time_str})")

        raw = stdout.decode().strip()
        response = raw
        try:
            data = json.loads(raw)
            response = data.get("result", raw)
            sid = data.get("session_id", "")
            if sid:
                _claude_sessions[user_id] = sid
        except (json.JSONDecodeError, AttributeError):
            pass

        if not response:
            response = f"(no output)\nstderr: {stderr.decode().strip()}"
        await thinking_msg.delete()
        sent_msgs = await send_long_message(update, response)

        for msg in sent_msgs:
            _msg_responses[msg.message_id] = response
        if len(_msg_responses) > 200:
            oldest_keys = sorted(_msg_responses)[:len(_msg_responses) - 200]
            for k in oldest_keys:
                del _msg_responses[k]

        if user_id not in _chat_history:
            _chat_history[user_id] = deque(maxlen=3)
        _chat_history[user_id].append({"user": user_msg, "assistant": response[:1000]})
        asyncio.create_task(save_memory(user_msg, response))
    except asyncio.TimeoutError:
        if proc:
            proc.kill()
            await proc.wait()
        await thinking_msg.edit_text("Claude timed out after 30 minutes.")
    except FileNotFoundError:
        await update.message.reply_text("Claude CLI not found. Make sure 'claude' is in PATH.")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")
