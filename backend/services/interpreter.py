import json
import re
from pathlib import Path
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from services.llm import chat_completion
from services.knowledge import get_interpretation_context

PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "interpreter.md"
SYSTEM_PROMPT = PROMPT_PATH.read_text(encoding="utf-8")


def _repair_json(raw: str) -> dict:
    """Try to parse JSON, with fallback repair for truncated output."""
    # Extract from code blocks
    if "```json" in raw:
        raw = raw.split("```json")[1].split("```")[0]
    elif "```" in raw:
        raw = raw.split("```")[1].split("```")[0]

    raw = raw.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Try to fix truncated JSON by closing brackets
    fixed = raw
    open_braces = fixed.count("{") - fixed.count("}")
    open_brackets = fixed.count("[") - fixed.count("]")

    # Close any unclosed strings
    if fixed.count('"') % 2 != 0:
        fixed += '"'

    fixed += "]" * open_brackets
    fixed += "}" * open_braces

    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        # Last resort: return raw text as summary
        return {
            "summary": raw[:500],
            "symbols": [],
            "emotion_analysis": "",
            "psychological_lens": "",
            "narrative_archetype": "",
            "life_insight": "",
        }


class DreamInterpreter:
    async def interpret(
        self,
        dream_script: dict,
        chat_history: list[dict],
        db: Optional[AsyncSession] = None,
        dream_id: Optional[str] = None,
    ) -> tuple[dict, list[str]]:
        """Interpret a dream. Returns (interpretation, citation_ids).

        `dream_id` (when supplied) deduplicates Attribution counting
        against upstream interview/director retrievals on the same dream.
        """
        interview_text = "\n".join(
            f"{'User' if m['role'] == 'user' else 'Interviewer'}: {m['content']}"
            for m in chat_history
        )

        symbol_ctx = get_interpretation_context(dream_script)
        semantic_ctx = ""
        cited: list[str] = []
        if db is not None:
            from services.knowledge_retrieval import semantic_interpretation_context
            semantic_ctx, cited = await semantic_interpretation_context(db, dream_script, dream_id=dream_id)

        ctx_block = "\n\n".join(c for c in (symbol_ctx, semantic_ctx) if c)

        user_message = f"""Here is the dream interview transcript:

{interview_text}

And here is the structured dream script:

```json
{json.dumps(dream_script, ensure_ascii=False, indent=2)}
```

{ctx_block}

Provide a comprehensive dream interpretation following your framework. Output ONLY valid JSON, no extra text."""

        raw = await chat_completion(
            messages=[{"role": "user", "content": user_message}],
            system=SYSTEM_PROMPT,
            max_tokens=4000,
        )

        return _repair_json(raw), cited
