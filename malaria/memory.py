"""Session memory, one JSON file per phone number.

Loaded on every inbound message so the agent has full session context and can
pick up where the last exchange ended. No database needed.
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .config import SESSION_DIR


def _path(phone: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9+]", "_", phone)
    return SESSION_DIR / f"{safe}.json"


def load(phone: str) -> dict:
    p = _path(phone)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"phone": phone, "turns": []}


def save(phone: str, session: dict) -> None:
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    _path(phone).write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")


def _extract(field: str, text: str) -> Optional[str]:
    m = re.search(rf"{field}\s*:\s*(.+)", text, flags=re.IGNORECASE)
    return m.group(1).strip() if m else None


def record_turn(session: dict, message: str, reply: str, region_key: Optional[str] = None) -> None:
    """Append a conversational turn and keep lightweight facts on the session."""
    if region_key:
        session["region_key"] = region_key
    session.setdefault("turns", []).append(
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "message": message,
            "reply": reply,
            "region_key": region_key,
        }
    )


def is_first_contact(session: dict) -> bool:
    return not session.get("turns")


def context_for(session: dict, max_turns: int = 3) -> str:
    """Compact prior-conversation summary handed to the advisor."""
    turns = session.get("turns", [])
    if not turns:
        return ""
    lines = []
    if session.get("region_key"):
        lines.append(f"Area in focus: {session['region_key'].replace('_', ' ').title()}")
    lines.append("Recent exchanges (oldest first):")
    for t in turns[-max_turns:]:
        reply = t.get("reply") or t.get("recommendation") or ""
        snippet = reply if len(reply) <= 500 else reply[:500] + " …"
        lines.append(f'- Worker: "{t["message"]}"')
        lines.append("  You: " + snippet.replace("\n", "\n  "))
    lines.append(
        "Respond in the SAME language you used previously for this worker. "
        "Build on the conversation; don't repeat the greeting or options already given."
    )
    return "\n".join(lines)


# Backwards-compatible alias for the legacy three-agent loop / eval script.
context_for_navigator = context_for
