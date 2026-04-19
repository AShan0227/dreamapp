# DreamApp Operations Runbook

Last updated: 2026-04-16

A practical reference for running DreamApp in production. Keep this
short — link out for anything detailed.

---

## Deploy

```bash
cd ~/.openclaw/workspace/projects/dreamapp
docker compose up -d
```

Services:

| Container             | Port      | Purpose                       |
|-----------------------|-----------|-------------------------------|
| `dreamapp-frontend-1` | 80        | nginx serving H5 build        |
| `dreamapp-backend-1`  | 8000      | FastAPI (uvicorn)             |
| `dreamapp-db-1`       | 5432      | PostgreSQL 16 + pgvector      |
| `dreamapp-minio-1`    | 9000/9001 | Video object storage          |

After every container recreate, verify Alembic migrations succeeded:

```bash
docker exec dreamapp-backend-1 alembic current
```

Expected output: `0003_video_object_name (head)`.

---

## Required env

Set these in `backend/.env` (NEVER commit):

| Var                         | Notes |
|-----------------------------|-------|
| `DREAM_AUTH_SECRET`         | Required. `openssl rand -hex 32` |
| `DREAM_DATABASE_URL`        | `postgresql+asyncpg://...` |
| `DREAM_LLM_API_KEY`         | MiniMax key |
| `DREAM_KLING_ACCESS_KEY/SECRET` | Kling video gen |
| `DREAM_SEEDANCE_API_KEY`    | (alt. video provider) |
| `DREAM_CORS_ORIGINS`        | Comma list — e.g. `https://dreamapp.cn` |

Optional but recommended in production:

| Var                            | Notes |
|--------------------------------|-------|
| `DREAM_SENTRY_DSN`             | Errors → Sentry |
| `DREAM_SENTRY_TRACES_SAMPLE_RATE` | Default 0.1 |
| `DREAM_DAILY_VIDEO_QUOTA`      | Default 5 per user/day |
| `DREAM_SMS_PROVIDER`           | `aliyun` (default noop) |
| `DREAM_SMS_ALIYUN_*`           | See `services/notifier.py` |
| `DREAM_EMAIL_PROVIDER`         | (still noop — wire when ready) |

Dev/SQLite escape hatch: `DREAM_ALLOW_INSECURE_SECRET=1`.

---

## Production env template

Copy `backend/.env.production.example` to `backend/.env` on the server,
fill in real secrets. Never commit `.env`. Rotate the included demo
passwords (`dreamapp_secret`, `dreamapp_minio_secret`) before going live.

```bash
cp backend/.env.production.example backend/.env
# Then edit. At minimum, set:
#   DREAM_AUTH_SECRET    (openssl rand -hex 32)
#   DREAM_DATABASE_URL   (real PG password)
#   DREAM_LLM_API_KEY    (real MiniMax key)
#   DREAM_CORS_ORIGINS   (your real domain(s))
#   DREAM_EMAIL_PROVIDER (mailgun or smtp — required for password reset)
```

## Backups

A backup script is provided at `scripts/backup.sh`. It:

1. `pg_dump` (custom format) of the `dreamapp` database
2. Mirrors the MinIO `dreamapp-videos` bucket via `mc`
3. Snapshots `backend/knowledge/*.json`
4. Writes a `MANIFEST.json` with sizes + timestamp
5. Prunes backups older than `RETENTION_DAYS` (default 14)

Run `scripts/install-cron.sh` to add a daily 03:00 backup entry to your
user crontab. Idempotent — re-running won't duplicate.

Or by hand:

```
0 3 * * *  /Users/sylvan/.openclaw/workspace/projects/dreamapp/scripts/backup.sh
```

To restore from a backup directory:

```bash
scripts/restore.sh ./backups/2026-04-16
```

The script will prompt before dropping the live DB. **Don't run unattended.**

---

## Observability

- `GET /health` — liveness check, no auth.
- `GET /metrics` — Prometheus exposition. Counters defined in
  `services/observability.py`. Scrape from same network only (no auth).

Key metrics to watch:

- `dreamapp_video_failures_total / dreamapp_video_generations_total` —
  if > 5%, look at `dream.failure_reason` for recent dreams.
- `dreamapp_quota_exhausted_total` — if rising, consider lifting
  `DREAM_DAILY_VIDEO_QUOTA` or scaling out.
- `dreamapp_request_duration_seconds_sum / _count` — average latency.
  Spikes usually mean LLM (MiniMax) or video provider degradation.
- `dreamapp_knowledge_retrievals_total` — should be roughly 3 × dreams
  (interview + director + interpreter, modulo dedup).

---

## Knowledge base maintenance

The pgvector knowledge table is seeded **incrementally** at startup
from `backend/knowledge/*.json`. To add or update entries:

1. Edit the JSON file.
2. Restart the backend container.
3. The seeder upserts by `(source, source_id)` and re-embeds changed
   entries. `use_count` / `success_count` / `confidence` are preserved.

Sleep cycle (decay / promote / merge / prune) runs automatically every
7 days, first run 15 minutes after container start. Trigger manually:

```bash
curl -X POST http://localhost:8000/api/plaza/knowledge/sleep-cycle
```

Inspect:

```bash
curl http://localhost:8000/api/plaza/knowledge/scheduler        # status
curl http://localhost:8000/api/plaza/knowledge/quarantined      # to review
curl 'http://localhost:8000/api/plaza/knowledge/top?by=use_count'
```

To resurrect a quarantined entry:

```bash
curl -X POST http://localhost:8000/api/plaza/knowledge/{id}/restore
```

---

## Embedding model

Vectors are tied to one model. The knowledge table records
`embedding_model` per row; the backend refuses to start if the configured
`DREAM_EMBEDDING_MODEL` doesn't match what's already in the DB. To change
models:

1. Update `DREAM_EMBEDDING_MODEL`.
2. Drop the `knowledge_embeddings` table OR set every row's
   `embedding_model` to the new value (only safe if you also re-embed).
3. Restart — the seeder will refill.

---

## Dual-driver dev

The codebase supports both PostgreSQL (production) and SQLite (single-
user dev). Key differences:

- **Migrations**: Alembic only runs against PG. SQLite uses
  `Base.metadata.create_all` at boot (lifespan in `main.py`).
- **pgvector**: SQLite has no vector type — semantic search returns
  empty when running on SQLite.
- **OTP store**: in-process for both; multi-replica needs Redis.

Switch via `DREAM_DATABASE_URL`:

- `sqlite+aiosqlite:///./data/dreamapp.db` (dev)
- `postgresql+asyncpg://dreamapp:dreamapp_secret@db:5432/dreamapp` (prod)

For PG/SQLite parity in CI, **always** use PG.

---

## Tests

```bash
docker exec dreamapp-backend-1 python /app/tests/test_all_endpoints.py
```

Tests run against the live backend and clean up everything they create
(soft-deletes all dreams, leaves user rows). Set
`DREAMAPP_KEEP=1` to skip teardown when investigating a failure.

Tests cover: health, auth (anon/email/phone/login/duplicate/wrong-pass),
ownership 403s, plaza public reads, citations, feedback, sleep cycle,
scheduler, knowledge L1+L2 retrieval, daily quota.

CI runs the same script via `.github/workflows/test.yml` against a
fresh PG service container.

---

## Known limitations

- **Rate limit + OTP in-process**: counts reset on restart, don't share
  between replicas. Single-replica is fine; for multi-replica, swap in
  Redis. (See `middleware.py`, `services/otp.py`.)
- **Sleep cycle scheduler in-process**: each replica runs its own. Use
  external cron + the API endpoint if you scale out.
- **Token is a bare random hex**: no expiry, no refresh. Rotation =
  manual UPDATE. JWT migration is planned.
- **Email provider is noop**: password reset codes only get logged.
  Wire `DREAM_EMAIL_PROVIDER=mailgun` (or implement another) before
  shipping.
- **MinIO presigned URLs auto-resign on read** but the public TTL is
  7 days. Anyone who scrapes a URL has 7 days to fetch it.
