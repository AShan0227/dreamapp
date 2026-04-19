# Dream Knowledge Engine — Architecture

Inspired by Genesis Xuanwu (玄武) memory system. Adapted for dream domain.

## Three-Tier Knowledge Architecture

### L0 — Index (fast lookup)
**What**: Symbol name, frequency, tags, category
**Size**: ~50 tokens per entry
**Use**: Quick matching during AI interview — "user mentioned water, what follow-up questions should I ask?"
**Storage**: In-memory dict loaded from symbols.json at startup

### L1 — Knowledge (injected into prompts)
**What**: Full symbol interpretation, cultural variants, interview questions, film techniques
**Size**: ~200-500 tokens per entry
**Use**: Injected into system prompts when relevant symbols/themes detected
**Storage**: JSON files in knowledge/ directory

### L2 — Evidence (deep reference)
**What**: Full papers, film analyses, cultural texts, user dream corpus
**Size**: Unlimited
**Use**: Not injected into prompts. Used for distillation into L1. Audit trail.
**Storage**: Future — vector DB (ChromaDB/Qdrant)

## Knowledge Categories

```
knowledge/
├── symbols.json           # 55 dream symbols (L1) ✅
├── film_techniques.json   # Cinematic technique taxonomy (L1) ✅
├── archetypes.json        # Jungian archetypes (L1) — TODO
├── tcm_dreams.json        # TCM dream-organ mapping (L1) — TODO
├── narratives.json        # Story archetype patterns (L1) — TODO
├── dream_corpus/          # Collected dream texts (L2) — TODO
└── papers/                # Research paper summaries (L2) — TODO
```

## Feedback Loop (Genesis-inspired)

### Attribution
When user rates interpretation quality or shares video:
- Track which symbols were matched
- Track which film techniques were used in video prompt
- Track user satisfaction signal

### Sleep Cycle (Distillation)
Periodic process:
1. **Decay**: Symbols/techniques not used decay in priority
2. **Merge**: Similar user dream patterns clustered
3. **Promote**: L2 evidence distilled into L1 knowledge when patterns emerge
4. **Prune**: Remove low-quality or contradicted knowledge

### Probation System
New knowledge entries start in probation:
- 3 successful uses → graduated (full confidence)
- 2 failures in probation → quarantined
- Prevents bad interpretations from spreading

## Injection Strategy

### During Interview
1. User says "我梦到水"
2. L0 lookup → match "water" symbol
3. Load L1 data for "water" → get follow-up questions specific to water dreams
4. Inject: "Based on dream research, ask about: water clarity, depth, temperature, motion, breathing ability"

### During Direction
1. Dream script contains: underwater scene, transition to surface
2. L0 lookup → match film techniques for underwater + transition
3. Inject: "Use Tunnel/Passage transition, Subjective Time Expansion, Color-Temperature Coding (deep blue → surface silver)"

### During Interpretation
1. Dream contains: water + moon + floating + transformation
2. L0 lookup → match all four symbols
3. Inject full L1 interpretation data for each
4. Add: Jungian archetype (Self/individuation), narrative archetype (transformation)
