"""Senior investor agent review via Claude CLI subprocess.

Accepts a screen_stocks() DataFrame and returns a brief expert analysis
of VCP/pivot quality and top picks. Calls the local `claude` CLI to
avoid requiring the Anthropic SDK — same pattern as stock/scripts/quant_review_local.py.
"""
from __future__ import annotations
import os
import shutil
import subprocess
from typing import Optional

import pandas as pd

_TIMEOUT_SECONDS = 120

_SYSTEM_PROMPT = """\
You are a senior CANSLIM investor with 20+ years of experience analyzing breakout patterns.
You are reviewing today's algorithmic screen results. Your tasks:

1. Evaluate VCP quality for each stock (contraction count, depth, volume contraction).
2. Assess whether the pivot price is a reasonable breakout entry; suggest a correction if not.
3. Flag any red flags (weak fundamentals despite passing the filter, extended price, etc.).
4. Name your top 2–3 picks with a 2–3 sentence rationale each.

Rules:
- Be concise — under 500 words total.
- Do not restate the raw numbers; reference them by observation.
- Use plain text, no markdown tables.
"""


def _format_df(df: pd.DataFrame) -> str:
    lines = []
    for _, row in df.iterrows():
        parts = [
            f"#{int(row['rank'])} {row['ticker']}",
            f"${row['price']:.2f}",
            f"RS:{row['rs_score']:.0f}",
            f"ADR:{row['adr'] * 100:.1f}%",
            f"Score:{row['composite']:.3f}",
        ]
        if row.get("in_base"):
            n = int(row.get("vcp_contractions", 0))
            vol = " vol✓" if row.get("vol_contracting") else ""
            parts.append(f"[VCP x{n}{vol}]")
            if row.get("vcp_pivot"):
                parts.append(f"Pivot:${row['vcp_pivot']:.2f}")
        else:
            parts.append("[no VCP]")
        if row.get("eps_q_growth") is not None:
            parts.append(f"EPS:{row['eps_q_growth'] * 100:+.0f}%")
        if row.get("rev_growth") is not None:
            parts.append(f"Rev:{row['rev_growth'] * 100:+.0f}%")
        if row.get("eps_accel"):
            parts.append("EPS↑")
        lines.append("  " + "  ".join(parts))
    return "\n".join(lines)


def run_investor_review(df: pd.DataFrame) -> Optional[str]:
    """Call Claude investor agent to review screen results.

    Returns the agent's analysis text, or None if claude CLI is unavailable
    or the subprocess fails/times out.
    """
    if df is None or df.empty:
        return None

    claude_bin = shutil.which("claude")
    if not claude_bin:
        return None

    screen_text = _format_df(df)
    prompt = (
        f"{_SYSTEM_PROMPT}\n\n"
        "--- Screen results ---\n"
        f"{screen_text}\n"
        "--- End of results ---\n\n"
        "Begin your review now."
    )

    try:
        result = subprocess.run(
            [claude_bin, "--permission-mode", "bypassPermissions", "-p", prompt],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        )
    except subprocess.TimeoutExpired:
        return None
    except Exception:
        return None

    if result.returncode != 0:
        return None

    text = result.stdout.strip()
    return text if text else None
