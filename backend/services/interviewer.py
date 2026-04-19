import json
from pathlib import Path
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from services.llm import chat_completion
from services.knowledge import get_interview_context
from services.knowledge_retrieval import semantic_interview_context

PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "interviewer.md"
SYSTEM_PROMPT = PROMPT_PATH.read_text(encoding="utf-8")

SCRIPT_GENERATION_PROMPT = """Based on the interview conversation above, generate the structured dream script as JSON. Follow the exact format specified in your instructions. Output ONLY the JSON, no other text."""


# ---- Cost guards ----------------------------------------------------------
#
# Long interviews used to ship the entire chat_history every turn, costing
# O(N²) tokens. We cap the recent window and replace older turns with a
# single LLM-summary message. The user's experience is identical (the AI
# still "remembers" earlier turns via the summary); the bill drops sharply.
#
# Cap chosen empirically: 10 turns covers the deepest dream interviews we've
# seen. After 10 user-turns, the dream is usually fully scoped anyway.

RECENT_TURNS_CAP = 10                 # last N user+assistant pairs kept verbatim
SUMMARY_TRIGGER = RECENT_TURNS_CAP    # rebuild summary when N+1 user turns accumulate
SUMMARY_MAX_TOKENS = 200


async def _build_system_prompt(
    text: str, db: Optional[AsyncSession], dream_id: Optional[str] = None
) -> tuple[str, list[str]]:
    """Combine keyword + semantic knowledge. Returns (prompt, cited_ids)."""
    parts = [SYSTEM_PROMPT]
    cited: list[str] = []
    keyword_ctx = get_interview_context(text)
    if keyword_ctx:
        parts.append(keyword_ctx)
    if db is not None:
        semantic_ctx, ids = await semantic_interview_context(db, text, dream_id=dream_id)
        if semantic_ctx:
            parts.append(semantic_ctx)
        cited = ids
    return "\n\n".join(parts), cited


def _user_turn_count(chat_history: list[dict]) -> int:
    return sum(1 for m in chat_history if m.get("role") == "user")


async def _maybe_compact(chat_history: list[dict]) -> list[dict]:
    """If chat_history exceeds RECENT_TURNS_CAP user turns, replace the
    early portion with a system-message summary. Idempotent: if already
    compacted, no-op (cap stays bounded).

    Shape after compaction:
      [system: "earlier in this dream the user said..."]
      [last 2*RECENT_TURNS_CAP messages verbatim]
    """
    if _user_turn_count(chat_history) <= RECENT_TURNS_CAP:
        return chat_history

    keep_last = RECENT_TURNS_CAP * 2  # user + assistant pairs
    older = chat_history[:-keep_last] if len(chat_history) > keep_last else []
    recent = chat_history[-keep_last:] if len(chat_history) > keep_last else chat_history

    if not older:
        return chat_history

    # Build a one-shot summary of older turns
    older_text = "\n".join(
        f"{m.get('role','?')}: {m.get('content','')[:300]}"
        for m in older if m.get("role") in ("user", "assistant")
    )
    try:
        summary = await chat_completion(
            messages=[{"role": "user", "content":
                "Summarize the earlier portion of this dream interview in 3-5 sentences. "
                "Capture: what the dream is about, key images, emotions named, characters, "
                "locations. Output prose only, no JSON or headers.\n\n"
                f"---\n{older_text}\n---"
            }],
            system="You are a careful summarizer of dream-interview conversations.",
            max_tokens=SUMMARY_MAX_TOKENS,
            temperature=0.0,    # deterministic + cache-eligible
            timeout_s=20.0,
        )
    except Exception:
        # If summary fails, drop older turns entirely rather than ship cost-bombed history.
        summary = "(earlier interview turns omitted)"

    return [
        {"role": "system", "content": f"[Earlier in this dream interview]\n{summary}"},
        *recent,
    ]


class DreamInterviewer:
    async def start_interview(
        self, initial_input: str, db: Optional[AsyncSession] = None
    ) -> tuple[str, list[dict], list[str]]:
        """Start a new dream interview. Returns (ai_response, chat_history, citation_ids)."""
        chat_history = [{"role": "user", "content": initial_input}]
        # No dream_id yet on start — first retrieval counts toward Attribution.
        system, cited = await _build_system_prompt(initial_input, db)

        ai_message = await chat_completion(
            messages=chat_history,
            system=system,
            max_tokens=500,
        )

        chat_history.append({"role": "assistant", "content": ai_message})
        return ai_message, chat_history, cited

    async def continue_interview(
        self,
        user_message: str,
        chat_history: list[dict],
        db: Optional[AsyncSession] = None,
        dream_id: Optional[str] = None,
    ) -> tuple[str, list[dict], bool, list[str]]:
        """Continue the interview. Returns (ai_response, updated_history, is_complete, citation_ids).

        Cost-bounded: the chat_history sent to the LLM is capped at
        RECENT_TURNS_CAP recent turns plus a summary system message. Storage
        history (caller-side) keeps everything for forensics and replay.
        """
        chat_history.append({"role": "user", "content": user_message})

        # Embed the LATEST user message only — earlier turns already shaped
        # the previous knowledge retrieval. Avoids re-embedding the entire
        # transcript every round (which was a hidden quadratic cost).
        system, cited = await _build_system_prompt(user_message, db, dream_id=dream_id)

        # Compact for the LLM call only — we still return the FULL history
        # to the caller so it gets persisted and shown to the user.
        compacted = await _maybe_compact(chat_history)

        ai_message = await chat_completion(
            messages=compacted,
            system=system,
            max_tokens=500,
        )

        chat_history.append({"role": "assistant", "content": ai_message})
        is_complete = "[DREAM_COMPLETE]" in ai_message

        return ai_message, chat_history, is_complete, cited

    async def generate_script(self, chat_history: list[dict]) -> dict:
        """Generate structured dream script from the interview conversation."""
        messages = chat_history + [
            {"role": "user", "content": SCRIPT_GENERATION_PROMPT}
        ]

        raw = await chat_completion(
            messages=messages,
            system=SYSTEM_PROMPT,
            max_tokens=4000,
        )

        from services.interpreter import _repair_json
        return _repair_json(raw)
