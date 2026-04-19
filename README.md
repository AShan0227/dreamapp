# DreamApp

> **A cinema of dreams.** Record what you dreamt, get a deep multi-frame interpretation, watch your dream become a short film.

[![CI](https://github.com/AShan0227/dreamapp/actions/workflows/ci.yml/badge.svg)](https://github.com/AShan0227/dreamapp/actions/workflows/ci.yml)
![License](https://img.shields.io/badge/license-private-lightgrey)

DreamApp is a full-stack dream operating system. You speak your dream into a warm AI interviewer; it produces a structured script, hands the script to an AI director, and ships back a multi-shot cinematic video plus a layered interpretation grounded in 492 retrievable knowledge entries (Freud, Jung, Hartmann, contemporary neuroscience, TCM, internet aesthetics, Gen Z subculture, reality-shifting, lucid dreaming, sleepmaxxing wellness — bilingual zh/en).

It also has a working social layer (Threads-style: handles, mentions, threaded comments, quote-dreams, FYP, mutual-follow DMs), monetization (WeChat Pay v3 / Alipay / Stripe with cryptographically-verified webhooks), a crisis safety net (acute distress is detected, AI suspends interpretation, real hotlines surface), and three growth mechanics: daily streak, year-in-dreams Wrapped, and dream remix duets.

---

## What's inside

```
backend/                   FastAPI async, 14.5k LOC, 171 endpoints
  ├── services/            50+ domain services (interpreter, director, payments,
  │                        crisis, moderation, streak, wrapped, duet, ...)
  ├── routers/             16 routers grouped by domain
  ├── models/              SQLAlchemy 2.0 + pgvector
  ├── alembic/versions/    9 migrations (head: 0009_wave_m)
  ├── knowledge/           18 JSON files — 492 retrievable entries
  ├── prompts/             Editable .md prompt files (interpreter, interviewer, director)
  └── tests/               51 unit + 8 integration, all green in CI

frontend/                  UniApp Vue 3 → H5 / WeChat MP / Android
  ├── src/pages/           32 pages (record, dream, plaza, profile, wrapped, duet, ...)
  ├── src/components/      DreamAtmosphere · DreamSplash · CrisisOverlay · DreamOrb
  ├── src/styles/          "Dream Cinema" design system (Inception · Paprika · Spirited
  │                        Away · Solaris · Shinkai aesthetic palette + Cormorant serif)
  └── src/utils/           Emotion → atmosphere variant mapper

docker-compose.yml         4 services: db (pgvector pg16) · backend · frontend (nginx) · minio
.github/workflows/ci.yml   3-job CI: unit · alembic round-trip · frontend build
.env.example               6-section env template (LLM · Payments · Notifications ·
                           Observability · Trust boundaries · Misc)
docs/                      Architecture notes
scripts/                   Backup · restore · cron install · CI handoff
```

## Highlights

- **Cinema-grade frontend.** Aurora gradients, multi-layer parallax starfields, breathing pulse animations on REM cycle, film grain overlays. Five film-referenced atmosphere variants (`moonrise` / `inception` / `spirited` / `shinkai` / `solaris` / `mulholland`) chosen automatically from each dream's emotion tags.
- **Knowledge-grounded interpretation.** Every interpretation cites the specific knowledge entries that shaped it (`/api/dreams/{id}/citations`). pgvector HNSW for sub-50ms retrieval against 492 bilingual entries spanning academic, cultural, and modern subculture content.
- **Real-money safe payments.** WeChat Pay v3 (RSA-SHA256 over signed payload + AES-GCM ciphertext decrypt), Alipay (RSA2 over sorted params), Stripe (HMAC-SHA256 with timestamp tolerance). All three verified, replay-protected, idempotent. Audit trail in `payment_webhook_events`.
- **Crisis safety net.** 26 high-severity bilingual patterns (zh + en) detect acute distress, suicidal ideation, or psychosis signals. On trigger: AI interpretation suspended, video generation gated, hotline surfaced (24h locale-aware), human-review queue populated. Tested in `test_crisis.py`.
- **Content moderation.** 5-category classifier (hard / NSFW / slur / spam / injection), public-vs-private surface policy, 3-report auto-hide, human review queue. Banned users excluded from plaza queries via SQL helper.
- **Production observability.** Structured JSON logging, request-id propagation, Sentry user/request tagging, /metrics with LLM cost counters + cache hit rate + 9-bucket latency histogram. Per-LLM-call retries with exponential backoff.

## Quick start

### One-shot Docker (production-shape)

```bash
cp .env.example .env                       # fill the REQUIRED block
docker compose up -d
open http://localhost                      # frontend
open http://localhost:8000/openapi.json    # 171 endpoints
```

### Local dev

```bash
# Backend
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env                    # fill DREAM_AUTH_SECRET at minimum
python main.py                             # http://localhost:8000

# Frontend
cd frontend
npm ci
npm run dev:h5                             # http://localhost:5173
```

### Tests

```bash
cd backend
pytest tests/test_payment_webhooks.py \
       tests/test_crisis.py \
       tests/test_moderation.py \
       tests/test_agent_sandbox.py -v
```

## Architecture

```
┌──────────────────┐    ┌─────────────────┐    ┌──────────────────┐
│   UniApp H5/MP   │───▶│  FastAPI async  │───▶│  PostgreSQL+     │
│   Vue 3 +        │    │  171 endpoints  │    │  pgvector (HNSW) │
│   Cinema design  │    │                 │    └──────────────────┘
└──────────────────┘    │  ┌─────────┐    │    ┌──────────────────┐
                        │  │  LLM    │────┼───▶│  MiniMax m2.5    │
                        │  │ client  │    │    └──────────────────┘
                        │  │ +cache  │    │    ┌──────────────────┐
                        │  │ +retry  │    │───▶│  Kling video gen │
                        │  └─────────┘    │    │  SeedDance       │
                        │                 │    └──────────────────┘
                        │  ┌─────────┐    │    ┌──────────────────┐
                        │  │ Crisis  │    │───▶│  MinIO (S3)      │
                        │  │ Mod     │    │    │  presigned URLs  │
                        │  │ Streak  │    │    └──────────────────┘
                        │  │ Wrapped │    │    ┌──────────────────┐
                        │  │ Duet    │    │───▶│  WeChat / Alipay │
                        │  │ Webhook │    │    │  / Stripe        │
                        │  └─────────┘    │    └──────────────────┘
                        └─────────────────┘
```

## Key endpoints

| Domain | Endpoint | What it does |
|---|---|---|
| Dream loop | `POST /api/dreams/start` | Begin AI interview |
| | `POST /api/dreams/chat` | Continue interview |
| | `POST /api/dreams/{id}/interpret` | Multi-lens interpretation |
| | `POST /api/dreams/{id}/generate` | Multi-shot video |
| Streak | `GET /api/streak/me` | My current streak + next milestone |
| | `GET /api/streak/today-prompt` | Tonight's "try to dream of..." |
| Wrapped | `GET /api/wrapped/me?period=2026` | My year in dreams |
| | `GET /api/wrapped/slug/{slug}` | Anonymous public Wrapped |
| Duet | `POST /api/duet/start` | Remix another dreamer's dream |
| Safety | `POST /api/moderation/report` | Report content |
| Payments | `POST /api/payments/create` | WeChat / Alipay / Stripe |
| | `POST /api/payments/webhook/*` | Cryptographically-verified callbacks |

Full list: [openapi.json](http://localhost:8000/openapi.json) when running, or browse `backend/routers/`.

## Configuration

`.env.example` documents 50+ variables grouped into 6 sections:
- **Required for boot** (POSTGRES_PASSWORD, DREAM_AUTH_SECRET, ...)
- **LLM** (MiniMax base URL + key + model)
- **Payments** (WeChat / Alipay / Stripe — all three webhooks fail-closed without these)
- **Notifications** (FCM / WeChat templates / SMTP / Aliyun SMS — silent no-op without these)
- **Observability** (Sentry DSN, PostHog, /metrics token, trusted-proxy CIDRs)
- **Misc** (request size cap, embedding model, debug flags)

Without payment / notification credentials, those subsystems gracefully no-op (failures logged, never crash). The app is fully functional in dev with just `DREAM_AUTH_SECRET` set.

## Deployment

See [docs/DEPLOY.md](./docs/DEPLOY.md) for production runbook (TLS, backup cron, log shipping, Sentry hookup).

## License

Private — not yet decided whether to open source. The repo is currently public to enable free GitHub Actions; the underlying license is TBD.

---

Built across roughly 10 development "Waves":
- **A–F** — core dream loop (record · script · video · interpret)
- **G** — agent runtime + sandbox
- **H–I** — engagement + Threads-style social
- **J** — subculture knowledge expansion (492 entries)
- **K** — safety + payments integrity (crisis · moderation · webhooks · analytics)
- **L1–L6** — performance + code quality (HNSW indexes · LLM cache fix · async correctness · tests · observability · security residuals)
- **M–O** — growth mechanics (streak · Wrapped · duet) + technical debt closeout
- **P** (current) — frontend integration of M/O/N + production deploy runbook
