"""
Conversation service: stores sessions, calls Claude with tools, executes tool calls.

Budget notes: default model is claude-haiku-5-5 (about 20x cheaper than Sonnet 5.5), effort is low,
and the system prompt is cached. One customer turn usually costs 2 API calls (one tool round-trip).

History is append-only and assistant content (including thinking blocks) is stored exactly as the API
returned it: Claude Haiku 5.5 rejects replayed thinking blocks if earlier turns were edited or trimmed.
Long chats are capped by number of customer turns instead of trimming.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any

import anthropic

from .. import db
from ..engine import load_catalogue
from . import tools as T
from .prompts import SYSTEM_PROMPT

log = logging.getLogger("advisor")

MODEL = os.environ.get("ADVISOR_MODEL", "claude-haiku-5-5")
MAX_TOOL_ROUNDS = 6          # safety valve for a single customer turn
MAX_CUSTOMER_TURNS = 25      # after this, offer a human instead of growing the history further
PRODUCT_CODE_RE = re.compile(r"\bP(0[1-9]|1[0-9]|2[0-5])\b")

_client: anthropic.Anthropic | None = None


def client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(max_retries=2, timeout=60.0)
    return _client


# ---------------------------------------------------------------------------
# session persistence
# ---------------------------------------------------------------------------
def create_session(assisted_by: str | None = None, seed_profile: dict[str, Any] | None = None) -> dict[str, Any]:
    session = {
        "id": db.new_id("s"), "created_at": db.now_iso(), "updated_at": db.now_iso(), "stage": "collecting",
        "language": None, "assisted_by": assisted_by, "profile": seed_profile or {}, "messages": [],
        "transcript": [], "recommendation": None, "handoff_id": None,
        "usage": {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0, "api_calls": 0},
    }
    _save(session, insert=True)
    return session


def get_session(session_id: str) -> dict[str, Any] | None:
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    return db.row_to_dict(row)


def _save(session: dict[str, Any], insert: bool = False) -> None:
    session["updated_at"] = db.now_iso()
    values = (session["id"], session["created_at"], session["updated_at"], session["stage"], session.get("language"),
              session.get("assisted_by"), db.dumps(session["profile"]), db.dumps(session["messages"]),
              db.dumps(session["transcript"]), db.dumps(session["recommendation"]) if session.get("recommendation") else None,
              session.get("handoff_id"), db.dumps(session.get("usage")))
    with db.connect() as conn:
        if insert:
            conn.execute("INSERT INTO sessions (id, created_at, updated_at, stage, language, assisted_by, profile_json, "
                         "messages_json, transcript_json, recommendation_json, handoff_id, usage_json) "
                         "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", values)
        else:
            conn.execute("UPDATE sessions SET created_at=?, updated_at=?, stage=?, language=?, assisted_by=?, profile_json=?, "
                         "messages_json=?, transcript_json=?, recommendation_json=?, handoff_id=?, usage_json=? WHERE id=?",
                         values[1:] + (session["id"],))


# ---------------------------------------------------------------------------
# tool execution
# ---------------------------------------------------------------------------
def execute_tool(session: dict[str, Any], name: str, args: dict[str, Any]) -> tuple[str, bool]:
    """Run a tool. Returns (result text for the model, is_error)."""
    if name == "update_profile":
        session["profile"] = T.apply_profile_update(session["profile"], args)
        if args.get("preferred_language"):
            session["language"] = args["preferred_language"]
        if session.get("handoff_id") and args.get("contact_phone"):
            with db.connect() as conn:
                conn.execute("UPDATE handoff_leads SET contact = ? WHERE id = ?", (args["contact_phone"], session["handoff_id"]))
        return db.dumps({"profile": session["profile"], "still_missing": T.missing_fields(session["profile"])}), False

    if name == "get_recommendation":
        missing = [m for m in T.missing_fields(session["profile"]) if not m.startswith("city_tier")]
        rec = T.run_recommendation(session["profile"])
        session["recommendation"] = rec.model_dump(mode="json")
        session["stage"] = "recommended" if session["stage"] != "handoff" else "handoff"
        payload = T.recommendation_for_llm(rec)
        if missing:
            payload["note"] = f"Profile is incomplete ({', '.join(missing)}); defaults were assumed. Confirm with the customer."
        return db.dumps(payload), False

    if name == "create_handoff_lead":
        if session.get("handoff_id"):
            return db.dumps({"handoff_id": session["handoff_id"], "note": "A handoff lead already exists for this conversation."}), False
        handoff_id = T.save_handoff(session, args["reason"], args["summary"], args.get("callback"))
        session["handoff_id"] = handoff_id
        session["stage"] = "handoff"
        return db.dumps({"handoff_id": handoff_id, "message": "A local Accel Business partner will call the customer back."}), False

    return f"Unknown tool {name}", True


# ---------------------------------------------------------------------------
# the turn
# ---------------------------------------------------------------------------
class LLMUnavailable(RuntimeError):
    """No key, no credit, or the API is unreachable: the UI switches to the guided (tap) advisor."""


def llm_available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


INTERNALS_RE = re.compile(r"\b(?:the|our) (?:tool|rule engine|engine)\b", re.IGNORECASE)


def _sanitise(text: str) -> str:
    """Belt and braces: replace any product code that slips through with the product name."""
    cat = load_catalogue()
    text = PRODUCT_CODE_RE.sub(lambda m: cat[m.group(0)].product_name if m.group(0) in cat else m.group(0), text)
    return INTERNALS_RE.sub("our pricing", text)   # "the tool shows Rs 3,298" -> "our pricing shows Rs 3,298"


def _serialise_content(content: list[Any]) -> list[dict[str, Any]]:
    """Store assistant blocks exactly as returned (thinking blocks included, even when their text is empty)."""
    return [block.to_dict() for block in content]


def handle_message(session: dict[str, Any], user_text: str) -> dict[str, Any]:
    """Process one customer message and return the updated state for the UI."""
    user_text = user_text.strip()
    if not user_text:
        return state_for_ui(session, "")
    if not llm_available():
        raise LLMUnavailable("The chat advisor needs ANTHROPIC_API_KEY. Use the tap-to-answer advisor instead.")
    n_turns = sum(1 for t in session["transcript"] if t["role"] == "user")
    if n_turns >= MAX_CUSTOMER_TURNS:
        reply = ("We have covered a lot. Tap 'Continue to quote' to see your bundle, or tap 'Talk to a person' "
                 "and a local Accel Business partner will call you.")
        session["transcript"] += [{"role": "user", "text": user_text}, {"role": "assistant", "text": reply}]
        _save(session)
        return state_for_ui(session, reply)
    session["messages"].append({"role": "user", "content": user_text})
    session["transcript"].append({"role": "user", "text": user_text})

    reply_parts: list[str] = []
    for _ in range(MAX_TOOL_ROUNDS):
        try:
            response = client().messages.create(
                model=MODEL,
                max_tokens=2048,   # thinking counts toward max_tokens on Haiku 5.5
                system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
                tools=T.TOOLS,
                output_config={"effort": "low"},
                messages=session["messages"],
            )
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError, anthropic.APIConnectionError) as exc:
            _rollback_user_turn(session)
            raise LLMUnavailable(f"The chat advisor is unavailable ({type(exc).__name__}). Use the tap-to-answer advisor.") from exc
        except anthropic.BadRequestError as exc:
            if "credit" in str(exc).lower() or "billing" in str(exc).lower():
                _rollback_user_turn(session)
                raise LLMUnavailable("The API account has no credit left. Use the tap-to-answer advisor.") from exc
            raise
        _account_usage(session, response)
        session["messages"].append({"role": "assistant", "content": _serialise_content(response.content)})

        for block in response.content:
            if block.type == "text" and block.text.strip():
                reply_parts.append(block.text.strip())

        if response.stop_reason == "max_tokens" and not any(b.type == "tool_use" for b in response.content):
            break
        if response.stop_reason == "refusal":
            reply_parts.append("Sorry, I can't help with that here. Shall we continue with your business needs?")
            break
        tool_uses = [b for b in response.content if b.type == "tool_use"]
        if response.stop_reason != "tool_use" or not tool_uses:
            break

        results = []
        for tu in tool_uses:
            result, is_error = execute_tool(session, tu.name, tu.input)
            log.info("tool %s -> %s", tu.name, result[:200])
            results.append({"type": "tool_result", "tool_use_id": tu.id, "content": result, "is_error": is_error})
        session["messages"].append({"role": "user", "content": results})

    reply = _sanitise("\n\n".join(reply_parts)) or "..."
    session["transcript"].append({"role": "assistant", "text": reply})
    _save(session)
    return state_for_ui(session, reply)


def _account_usage(session: dict[str, Any], response: Any) -> None:
    u = session.setdefault("usage", {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0, "api_calls": 0})
    u["input_tokens"] += response.usage.input_tokens
    u["output_tokens"] += response.usage.output_tokens
    u["cache_read_input_tokens"] += response.usage.cache_read_input_tokens or 0
    u["api_calls"] += 1


def state_for_ui(session: dict[str, Any], reply: str) -> dict[str, Any]:
    return {
        "session_id": session["id"],
        "reply": reply,
        "stage": session["stage"],
        "language": session.get("language"),
        "profile": session["profile"],
        "recommendation": session.get("recommendation"),
        "handoff_id": session.get("handoff_id"),
        "transcript": session["transcript"],
        "usage": session.get("usage"),
        "llm_available": llm_available(),
    }


def _rollback_user_turn(session: dict[str, Any]) -> None:
    """Undo the customer message we just appended when the first API call never happened (keeps history append-only valid)."""
    if session["messages"] and session["messages"][-1] == {"role": "user", "content": session["transcript"][-1]["text"]}:
        session["messages"].pop()
        session["transcript"].pop()


# ---------------------------------------------------------------------------
# guided (no-LLM) advisor: the UI collects answers with buttons; same engine, same handoff
# ---------------------------------------------------------------------------
def apply_guided_profile(session: dict[str, Any], answers: dict[str, Any], summary_line: str | None) -> dict[str, Any]:
    """Replace the profile with the guided answers and run the rule engine."""
    keep = {k: v for k, v in session["profile"].items() if k in ("business_name", "contact_name", "contact_phone")}
    session["profile"] = T.apply_profile_update(keep, answers)
    session["language"] = answers.get("preferred_language") or session.get("language")
    if summary_line:
        session["transcript"].append({"role": "user", "text": summary_line})
    execute_tool(session, "get_recommendation", {})
    pr = session["recommendation"]["pricing"]
    reply = (f"Your bundle: Rs {pr['monthly_total_inr']:,} per month, setup Rs {pr['setup_total_inr']:,}, "
             f"{pr['contract_months']}-month plan.")
    session["transcript"].append({"role": "assistant", "text": reply})
    _save(session)
    return state_for_ui(session, reply)


def guided_handoff(session: dict[str, Any], reason: str, callback: str | None) -> dict[str, Any]:
    summary = T.deterministic_summary(session["profile"], session.get("recommendation"), reason)
    execute_tool(session, "create_handoff_lead", {"reason": reason, "summary": summary, "callback": callback})
    reply = "Thank you. A local Accel Business partner will call you back" + (f" ({callback})." if callback else " soon.")
    session["transcript"].append({"role": "assistant", "text": reply})
    _save(session)
    return state_for_ui(session, reply)
