# DreamApp - Product Document v1

> DreamApp is not a dream journal. It is a Dream Operating System.
> Users record dreams, see dreams, understand dreams, share dreams, and create anything based on dreams.

---

## 1. Product Vision

Every night, the human brain produces a unique film that plays once and disappears forever. No technology in human history has been able to reconstruct it. AI video generation makes this possible for the first time.

**Dream is the last human experience layer that has never been digitized.** Steps, heart rate, social interactions, photos, spending — every waking second is recorded. But 6-8 hours of nightly dreaming remains a complete black box.

DreamApp opens this black box.

---

## 2. Core Triangle

```
     ① CREATE (造梦)
        /          \
       /            \
      /   Content    \
     /    Flywheel    \
    /                  \
② INTERPRET (解梦) ——— ③ SOCIAL (社交)
```

Three pillars, each independently viable, mutually reinforcing:
- CREATE produces content
- INTERPRET gives it depth and meaning
- SOCIAL circulates content and drives new recording

---

## 3. Foundation Layer: Dream Knowledge Engine

All upper-layer features are powered by this knowledge base.

### Data Sources
- **Academic**: Global dream research papers, sleep science literature
- **Cultural**: Dream interpretation traditions across civilizations, mythological archetypes, religious texts
- **Clinical**: Psychotherapy case studies, dream-disease correlation research
- **Cinematic**: Visual language and narrative techniques from dream-related films (Tarkovsky, Lynch, Kon Satoshi, Nolan)
- **User Corpus**: Accumulated dream data from users (improves over time)

### Implementation
- Vectorized knowledge graph
- Powers: questioning logic, dream interpretation, video generation guidance, sleep incubation recommendations
- Core differentiator: AI doesn't "guess" your dream — it understands your dream based on thousands of years of human knowledge about dreaming
- User perception: "It understands my dreams better than I do"

### 3.1 Genesis-inspired Knowledge Loop (implemented 2026-04-16)

The knowledge base is not a static lookup — it has a feedback loop modeled on Genesis 玄武 memory architecture.

**Three-tier storage** (via pgvector in PostgreSQL)
- **L0 — Index**: fast lookup (id, tags, score), ~50 tokens
- **L1 — Knowledge**: full interpretations, injected into LLM prompts, ~200-500 tokens
- **L2 — Evidence**: raw papers & dream corpus, not injected, used as audit trail & distillation source

Current distribution: 220 entries — 150 L1 (symbols/archetypes/narratives/TCM/cultural/film_techniques/emotion_visual/prompt_styles/dreamcore/incubation) + 70 L2 (papers, dream_corpus).

**Semantic retrieval** with Attribution
- Every stage (interview / director / interpreter) pulls top-K semantically relevant entries via BAAI/bge-small-zh-v1.5 (512-dim bilingual embeddings)
- Each retrieval increments `use_count`, promotes probation → graduated at 3 uses
- Citation IDs stored on the dream record — users can see which knowledge drove each stage

**User feedback closes the loop**
- 👍 on an interpretation → `success_count++` + confidence bump on all cited entries
- 👎 → `failure_count++` + confidence drop
- Quarantine trigger: failure ratio > 60% AND total feedback ≥ 3 (avoids punishing innocent co-cited entries)

**Sleep Cycle distillation** — weekly background job
- **Decay**: entries unused for 14+ days lose 0.05 confidence
- **Promote**: L2 entries with 5+ uses graduate to L1 (corpus patterns become reference knowledge)
- **Merge**: near-duplicate L1 entries (cosine distance < 0.05) collapse, lower-confidence one quarantined
- **Prune**: confidence < 0.1 → quarantined (soft delete)

**Why this matters for the product**
- The AI's dream interpretations actually get better over time based on what users find resonant
- Real dreams in the corpus that keep surfacing semantically get promoted into canonical knowledge
- Quality drift is self-healing: bad interpretations get quarantined, proven interpretations rise in confidence

---

## 4. Pillar ① — CREATE (造梦系统)

### 4.1 Dream Capture (梦境捕获)

**Core Interaction: AI Director Interview**

Not a diary. An AI interviewer actively probes to complete the dream narrative:
- "You said you were flying — were you flapping wings like a bird, or floating?"
- "Could you see that person's face? Who did it feel like?"
- "What was the light like? What color tone?"
- "What emotion — excitement or fear?"

5-10 rounds of questioning → complete narrative script → feed to video model.

**Why this works**: The questioning is precise because the Knowledge Engine has ingested global dream research. Human dreams have patterns and correlations. We know what to ask.

### 4.2 Dream Visualization (梦境影视化)

**AI Director System** — a professional film production layer between the user's narrative and the generic video model:

| Role | Responsibility |
|------|---------------|
| Screenwriter | User narration → structured narrative script (three-act / non-linear / stream-of-consciousness) |
| Storyboard Artist | Script → camera language (shot types, camera movement, transitions) |
| Director | Emotional pacing, narrative tension, overall tone control |
| Art Director | Style consistency (user-selectable: surreal / ink wash / cyberpunk / Ghibli / film noir...) |
| Composer | AI music generation matching dream emotional arc |
| Producer | Video model selection, multi-segment stitching, quality control, cost optimization |
| Time Technician | Cinematic time techniques: slow motion, jump cuts, time loops — recreating the time distortion felt in dreams |

### 4.3 Active Dreaming / Dream Incubation (主动造梦)

Based on peer-reviewed research (Deirdre Barrett, Harvard):
- User sets intention: "Tonight I want to dream about the ocean"
- System provides targeted pre-sleep stimuli:
  - Specific images/video clips
  - Custom soundscapes (ocean waves + Theta wave binaural beats)
  - Meditation/guided relaxation scripts
  - Scent recommendations (see: Soundscape & Scent integration)
- After waking → record dream → compare with intention → refine for next cycle

**Closed loop: See your dream → Want to control the next one → Active dreaming → Record → Visualize → Repeat**

### 4.4 Soundscape Integration (声景融合)

Not generic white noise. Customized sound environments based on dream intention:
- Want to dream of the beach → ocean waves + specific Theta frequency guidance
- Want to dream of a forest → birdsong + insects + low-frequency ambient
- Sound design informed by acoustic ecology research and binaural beat studies
- Integrated with the dream music module for a complete pre-sleep → during-sleep → post-sleep audio experience

---

## 5. Pillar ② — INTERPRET (解梦系统)

### 5.1 Multi-dimensional Analysis

**Per-dream analysis:**
- Symbol interpretation (powered by Knowledge Engine)
- Emotional tone analysis
- Life event correlation (based on user-logged events)
- Psychological lens: Jungian archetypes, shadow, anima/animus
- Evolutionary psychology lens: "Your brain is training you to handle [X scenario]" (Revonsuo's Threat Simulation Theory)
- Narrative archetype: Hero's journey / descent / chase / metamorphosis / labyrinth

**Long-term tracking:**
- Dream emotion curve over weeks/months
- Recurring symbols and characters
- Thematic periodicity
- Color palette analysis of your dreams over time

### 5.2 Health Integration (健康数据交叉)

- Sync with Apple Watch / Oura / Whoop / other wearables
- Cross-reference: HRV + deep/light sleep + REM timing + blood oxygen × dream content/emotion
- Complete sleep portrait = physiological data + dream data
- Personalized sleep recommendations
- Anomaly detection: "Your nightmare frequency has increased 200% in the past two weeks"

### 5.3 Dream Therapy / Nightmare Rewrite (梦境疗愈)

Based on Imagery Rehearsal Therapy (clinically validated for PTSD):
- Nightmare → AI visualizes the dream
- **User directs the rewrite** — they set the plot direction, not the AI
- Generate the "ending you wanted" version
- Play the rewritten version before sleep → desensitization
- User has full control — this is empowerment, not passive treatment

### 5.4 Traditional Medicine Perspectives (传统医学视角)

- Chinese Medicine: Dream-organ correspondence from Huangdi Neijing (e.g., liver excess → angry dreams)
- Ayurveda: Dream types mapped to Vata/Pitta/Kapha constitution
- Combined with wearable HRV/temperature data for cross-validation
- Personalized wellness suggestions (diet, routine, herbal tea)
- Strong resonance in Chinese-speaking markets; Ayurveda for international differentiation

---

## 6. Pillar ③ — SOCIAL (社交系统)

### 6.1 Dream Plaza (梦境广场)
- Browse others' dream videos (anonymous or named, user's choice)
- Topic-based dream collections
- Trending dreams

### 6.2 Dream Matching (梦境匹配)
- "147 people had a similar dream to yours last night"
- Natural icebreaker — deeper than zodiac compatibility
- Dream compatibility scores

### 6.3 Co-Dreaming (共梦)
- Two or more people agree on a dream theme
- Each records their dream independently
- Compare and generate combined video
- Trigger for offline meetups

### 6.4 Social Spread Flywheel
Dream videos are inherently shareable on short-video platforms (Douyin/TikTok/Xiaohongshu) → External viewers see dream videos → Download app to record their own → Generate content → Share again

---

## 7. Customization & Remix (定制化与二创)

### 7.1 Dream Customization (梦境定制)

User is the director of their own dream video:
- **Style**: Surreal / cyberpunk / ink wash / film grain / anime...
- **Mood**: Same dream → "horror version" vs "healing version"
- **Camera**: First-person immersion / third-person observer / god's-eye view
- **Completion**: Dream cut off? User writes the second half, AI generates complete version
- **Music**: Ambient / piano / electronic / silence
- **Time**: That 3-second fall → stretched to 30-second slow-motion experience

### 7.2 Dream Remix (梦境二创)

- **Self-remix**: Splice two different nights' dreams into one narrative
- **Remix others**: See a dream on the plaza, regenerate in your own style
- **Dream chain**: A's dream ending = B's dream beginning, community co-creates an epic dream
- **Dream dialogue**: Two people's dreams side by side, AI analyzes hidden connections
- **Dream challenges**: Same keyword, see what different people's subconscious generates

Remix turns dreams from **private experience into social creative material** — the content engine for the social system.

---

## 8. Dream Archive (梦境档案系统)

The long-term retention moat. The longer you use it, the more irreplaceable it becomes.

### 8.1 Dream Journal
Each entry contains:
- Original narration + AI-completed full narrative
- Generated dream video
- Emotion tags, symbol tags, character tags
- Physiological data from that night (wearable sync)
- User-added life event notes

### 8.2 Timeline
Browse all dreams chronologically. Filter by symbol / character / emotion / theme. After a year, see the panoramic view of 300+ dreams.

### 8.3 Cross-temporal Correlation (跨时间关联) — Killer Feature

**Recurring dream detection:**
- Scene recurrence: "You dreamed about the same building in March 2025 and January 2026"
  → Auto-link, compare differences
  → "What changed in your life between these two dreams?"

**Character tracking:**
- "The faceless person has appeared for the 7th time"
  → Timeline marking all appearances
  → Emotion/context comparison across occurrences

**Thematic periodicity:**
- "You dream about water every time the season changes"
  → Periodic pattern recognition
  → Correlation with physiological/psychological/life rhythms

**Narrative evolution:**
- "Same dream, but the ending is different every time"
  → Track narrative evolution trajectory
  → Reflects inner state changes over time

### 8.4 Deja Reve (梦境-现实交叉)

When reality overlaps with a dream:
- User can tag at any time: "I think I dreamed about this"
- AI automatically searches dream archive for best match
- Side-by-side display: dream record from then vs. what's happening now
- **This moment gives the user chills** — the product's "wow moment"

Proactive mode: AI analyzes user's life event log and pushes — "What you experienced today is highly similar to a dream from 3 months ago. Want to see it?"

### 8.5 Dream Health Index (梦境健康指数)

Long-term monitoring generates:
- Monthly/quarterly dream reports
- Nightmare frequency trends
- Emotional tone trajectory
- Sleep quality × dream quality cross-analysis
- Anomaly alerts

---

## 9. Dream OS Architecture (可变形App架构)

### 9.1 Core Concept

The app is a shell. Every user's app looks different.

```
Traditional App:  Product team defines features → Users use them
Dream OS:         Product team provides base capabilities → Users assemble their own app with natural language
```

### 9.2 Architecture Stack

```
┌────────────────────────────────┐
│  User-visible layer (morphable)│  ← Natural language → layout/feature composition
│  Each user has a "config file" │     Each user's app looks different
├────────────────────────────────┤
│  Vibe Coder (middleware)       │  ← Understands intent → assembles components
│  Built early, opened late      │     → generates personalized UI + Agent logic
├────────────────────────────────┤
│  Component Library (we maintain)│ ← Video player / recorder / timeline
│                                │    Interpretation card / emotion chart / social feed
│                                │    Agent panel / payment widget / ...
├────────────────────────────────┤
│  Base Capability APIs (stable) │  ← Dream data / video gen / interpretation
│                                │    Social / payment / wearable integration / ...
└────────────────────────────────┘
```

### 9.3 User Scenarios

**Creator type:** Hides interpretation module, homepage = video timeline + style editor + one-click publish to Douyin

**Health type:** Auto emotion scoring after each recording, homepage = emotion trend chart + sleep data + interpretation analysis

**Social type:** Homepage = dream plaza + daily similar-dream match, recording entry minimized

**Dream interpreter (professional):** Order-taking page, clients submit dreams, interpreter replies with video analysis, pricing & queue management

### 9.4 Rollout Strategy

- **Phase 1**: Vibe Coder runs internally, we use it to rapidly iterate features. Users get standard app.
- **Phase 2**: Open "customize homepage" — users rearrange layout and feature priority with natural language.
- **Phase 3**: Full open — users create Agents, modify UI, build services, open shops.

### 9.5 Dream Agent Store

Users can create, share, and sell Agents:
- Free Agents + paid premium Agents
- Creator revenue share (70% to creator)
- Pro users unlock higher API call quotas

**Ecosystem emergence:**
- Dream interpreters (Agent-powered interpretation services)
- Dream content creators (batch dream content production)
- Dream researchers (group dream pattern analysis)
- Dream game designers (interactive narrative experiences)

---

## 10. Value-add Modules (增值模块)

| Module | Description |
|--------|-------------|
| Dream IP | Identify recurring characters/scenes → solidify into user's exclusive "dream characters" → personal mythology |
| Dream Music | Generate soundtrack based on dream emotion → standalone sleep aid audio scene |
| Dream Merch | Poster / picture book / phone case / art book → Print-on-Demand |
| City Dreams | Daily lightweight push: "Last night, 32% of Shanghai dreamed about water" → viral hook + community belonging |
| Creativity Engine | Extract creative seeds from dreams → for creators/entrepreneurs/designers |
| Dream Scent (周边) | Scent products linked to dream themes → essential oils, candles, room sprays. Based on olfactory science research (Mannheim Institute) linking scent to dream content |

---

## 11. Hardware (暂存)

### DreamFrame (画框概念 — 保留待验证)

Digital frame displaying dream videos. Concept preserved but not prioritized.

**Unresolved challenge:** Low repeat usage. Hardware must satisfy:
1. Daily use minimum 2x (pre-sleep + post-wake)
2. Loss aversion when not used (FOMO)
3. Does something phone cannot do

**Decision:** Defer hardware until software is validated and user behavior data reveals what physical interaction the phone truly cannot cover.

---

## 12. Business Model

### Consumer Revenue
- **Free tier**: Text dream journal + basic interpretation
- **Pro subscription (¥30-70/month)**: Video generation + deep interpretation + full archive
- **Premium subscription (¥100-200/month)**: Unlimited video generation + all styles + health integration + active dreaming

### Platform Revenue (Phase 3+)
- Agent Store commission (30%)
- Pro API quota tiers for power users/creators
- Featured placement in Agent Store

### Merch & Physical
- Dream scent product line (aromatherapy collaboration or own brand)
- Print-on-demand dream art (posters, books, phone cases)
- Hardware (when validated)

### B2B (Phase 3+)
- Dream therapy SaaS for psychologists/clinics (per-seat pricing)
- Sleep health data layer for wearable ecosystem integration

---

## 13. Phased Roadmap

### Phase 1 — Dream Capture (捕梦器)
**产品形态：Tool — 一个能把梦变成视频的工具**

Core loop: Record → AI Interview → Generate Video → Interpret

**捕获：**
- Voice/text dream input
- AI Director Interview (5-10 rounds probing, powered by Knowledge Engine)
- Dream narrative completion and structuring

**生成：**
- AI Director System (screenwriter → storyboard → director → art → composer → producer)
- Cinematic time techniques (slow-mo, jump cuts, time loops for dream time distortion)
- Style system (surreal / ink wash / cyberpunk / Ghibli / film noir...)
- Dream customization (style / mood / camera / music / time manipulation)

**解读：**
- Symbol interpretation (Knowledge Engine driven)
- Emotional tone analysis
- Life event correlation
- Multi-lens: Jungian / evolutionary psychology / narrative archetype / TCM
- Nightmare rewrite (user directs the new ending)

**档案：**
- Dream journal with full metadata (narration, video, tags, physiological data)
- Timeline browsing and filtering
- Cross-temporal correlation (recurring dreams, character tracking, thematic periodicity)
- Deja Reve detection (dream-reality overlap)
- Dream health index (emotion trends, nightmare frequency, anomaly alerts)

**辅助：**
- Active dreaming / dream incubation (pre-sleep content recommendations based on research)
- Soundscape integration (custom sound environments matched to dream intentions)
- Health data integration (Apple Watch / Oura / Whoop sync)

**社交（轻量）：**
- Dream video sharing to external platforms (Douyin/TikTok/Xiaohongshu)
- Dream Plaza (browse/discover others' dreams)
- Dream matching, co-dreaming, remix, dream chain, challenges

**This phase validates:** Can we make people record dreams daily? Do they share the videos?

---

### Phase 2 — Dream OS (梦境操作系统)
**产品形态：Platform — 每个用户的App长得不一样**

**Vibe Coder opens to users:**
- Natural language → customize app layout, feature priority, workflows
- Create personal Dream Agents (automated, triggered, or interactive)
- Agent examples:
  - "Every Sunday, summarize my week's dreams, find the lowest-emotion one, auto-generate a healing version"
  - "Track every time I dream about water, cross-reference with weather and moon phase"
  - "Turn my past month's dreams into a series, one dream per episode"

**Dream Agent Store:**
- Users share/sell Agents
- Creator revenue share (70% to creator)
- Pro users unlock higher API quotas
- Ecosystem emergence: dream interpreters, content creators, researchers, game designers

**Full app morphing:**
- Creator type → video workstation layout
- Health type → emotion dashboard layout
- Social type → dream plaza layout
- Professional → client order management layout

**This phase validates:** Will users build on the platform? Does the ecosystem self-sustain?

---

### Phase 3 — Hardware (物理入口)
**产品形态：Device — 软件验证后的精准打击**

Hardware form factor TBD — determined by Phase 1-2 user behavior data.

**Decision criteria:**
1. Must drive daily usage minimum 2x (pre-sleep + post-wake)
2. Must create loss aversion when not used
3. Must do something the phone genuinely cannot do

**Candidate directions (to be validated):**
- Bedside dream station (voice capture + soundscape + scent + non-contact sleep monitoring)
- Dream display frame (living dream art for home)
- Wearable (if data proves comfort is not a barrier)
- New form factor that emerges from user behavior patterns

**This phase validates:** Does hardware drive retention and new acquisition beyond what software alone achieves?

---

## 14. Competitive Moat

1. **Knowledge Engine**: Years of curated dream knowledge across disciplines — not replicable by a weekend hackathon
2. **AI Director System**: Professional film production knowledge baked into video generation — generic video tools can't match this
3. **Dream Archive**: User's irreplaceable personal dream data — migration cost is infinite
4. **Network Effects**: Social features + Agent ecosystem create platform lock-in
5. **Vibe Coder Platform**: When users build on top of you, you become infrastructure

---

*Document version: v1*
*Created: 2026-04-14*
*Author: Sylvan + Surf*
