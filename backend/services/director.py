import json
from pathlib import Path
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from services.llm import chat_completion
from services.knowledge import get_director_context
from services.knowledge_retrieval import semantic_director_context
from services.interpreter import _repair_json

PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "director.md"
SYSTEM_PROMPT = PROMPT_PATH.read_text(encoding="utf-8")


class VideoDirector:
    async def create_shot_plan(
        self, dream_script: dict, db: Optional[AsyncSession] = None,
        dream_id: Optional[str] = None,
    ) -> tuple[dict, list[str]]:
        """Convert a dream script into a multi-shot storyboard. Returns (plan, citation_ids).

        `dream_id` (when supplied) deduplicates Attribution counting against
        upstream interview retrievals on the same dream.
        """
        technique_ctx = get_director_context(dream_script)
        semantic_ctx = ""
        cited: list[str] = []
        if db is not None:
            semantic_ctx, cited = await semantic_director_context(db, dream_script, dream_id=dream_id)

        ctx_block = "\n\n".join(c for c in (technique_ctx, semantic_ctx) if c)

        user_message = f"""Dream script:

```json
{json.dumps(dream_script, ensure_ascii=False, indent=2)}
```

{ctx_block}

Create a 6-8 shot storyboard. CRITICAL: each shot prompt MUST be 40-50 words maximum. Dense, specific, every word visual. Output ONLY JSON."""

        raw = await chat_completion(
            messages=[{"role": "user", "content": user_message}],
            system=SYSTEM_PROMPT,
            max_tokens=4000,
        )

        return _repair_json(raw), cited

    async def create_video_prompt(
        self, dream_script: dict, db: Optional[AsyncSession] = None
    ) -> str:
        """Legacy: returns the full shot plan as JSON string."""
        plan, _cited = await self.create_shot_plan(dream_script, db=db)
        return json.dumps(plan, ensure_ascii=False)

    def extract_shot_prompts(self, shot_plan: dict) -> list[str]:
        """Extract individual shot prompts. Keep them short — do NOT append extra text."""
        shots = shot_plan.get("shots", [])
        return [shot.get("prompt", "") for shot in shots if shot.get("prompt")]
