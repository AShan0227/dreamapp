# DreamApp · Production deployment runbook

> Goal: take a fresh Linux box → fully working DreamApp at `https://your-domain` in ~30 minutes.
> Assumes you have: a domain pointed at the box, root SSH, Docker installed.

---

## 0 · Prerequisites checklist

```bash
docker --version        # >= 24
docker compose version  # >= 2
git --version           # any
nginx --version         # only if NOT terminating TLS in the docker frontend
```

DNS: `A` record for `dreamapp.example.com` → server IP. Wait for propagation before TLS.

---

## 1 · Clone + .env

```bash
sudo mkdir -p /srv && cd /srv
sudo chown $USER:$USER .
git clone https://github.com/AShan0227/dreamapp.git
cd dreamapp

cp .env.example .env
$EDITOR .env
```

### Minimum required (boot)

```env
POSTGRES_PASSWORD=<openssl rand -hex 24>
MINIO_ROOT_USER=dreamapp
MINIO_ROOT_PASSWORD=<openssl rand -hex 24>
DREAM_AUTH_SECRET=<openssl rand -hex 32>
DREAM_LLM_BASE_URL=https://api.ofox.ai/v1     # or your provider
DREAM_LLM_API_KEY=<your MiniMax/OpenAI key>
```

Without payment/notification credentials, those subsystems silently no-op.
The app boots, you can register, record dreams, get interpretations, generate
videos. See `.env.example` for the rest grouped by section.

---

## 2 · First boot

```bash
docker compose up -d
docker compose logs -f backend          # wait for "Application startup complete"
docker compose ps                        # all services 'healthy'
```

Verify:

```bash
curl -s http://localhost:8000/health             # {"status":"ok"}
curl -s http://localhost/                        # frontend HTML
curl -s http://localhost:8000/openapi.json | jq '.paths | keys | length'  # ~171
```

---

## 3 · TLS via nginx (recommended)

DreamApp's bundled `nginx.conf` only serves HTTP on :80. For production
TLS, run a separate nginx in front (or terminate at Cloudflare):

```bash
sudo apt install -y nginx certbot python3-certbot-nginx
sudo certbot --nginx -d dreamapp.example.com
```

Sample upstream block (add to `/etc/nginx/sites-available/dreamapp`):

```nginx
server {
    listen 443 ssl http2;
    server_name dreamapp.example.com;

    ssl_certificate     /etc/letsencrypt/live/dreamapp.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/dreamapp.example.com/privkey.pem;

    # Frontend SPA
    location / {
        proxy_pass http://localhost;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Backend API + webhooks
    location /api/ {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;     # match LLM timeout
    }
}
```

> ⚠ **Configure DREAM_TRUSTED_PROXIES** to include nginx's IP CIDR.
> Without it, the app rejects `X-Forwarded-For` from nginx and rate-limits
> by your reverse-proxy IP instead of the real client. Default `127.0.0.0/8`
> covers single-host nginx.

---

## 4 · Payment webhook URLs (after TLS works)

In each provider's dashboard, set the notify URL to:

| Provider | URL |
|---|---|
| WeChat Pay v3 | `https://dreamapp.example.com/api/payments/webhook/wechat` |
| Alipay | `https://dreamapp.example.com/api/payments/webhook/alipay` |
| Stripe | `https://dreamapp.example.com/api/payments/webhook/stripe` |

Then fill the `DREAM_*` payment env vars (see `.env.example`) and
`docker compose restart backend`. All three webhooks are fail-closed:
without correct env, signature verification rejects every request → no
fraudulent "paid" upgrades possible.

Verify with provider's test webhook tool. Audit trail lives in
`payment_webhook_events` table.

---

## 5 · Backups (cron)

```bash
sudo bash scripts/install-cron.sh
```

This installs:
- **Daily 03:00 UTC**: `scripts/backup.sh` — pg_dump + MinIO mirror + GPG encrypt + offsite copy
- **Weekly Sunday 04:00 UTC**: `scripts/restore.sh --verify` — restore-test on a throwaway DB

Verify backups land:

```bash
ls -la /srv/dreamapp/backups/
sudo journalctl -u dreamapp-backup -n 50
```

---

## 6 · Observability

### Sentry

1. Create project at sentry.io, copy DSN
2. Add to `.env`: `DREAM_SENTRY_DSN=https://...@sentry.io/...`
3. `docker compose restart backend`
4. Trigger any test exception → should appear in Sentry within 30s with
   `request_id`, `user_id`, `path` tags attached automatically.

### Prometheus

Backend exposes `/metrics` on internal port 8000. Set `DREAM_METRICS_TOKEN`
to a long random secret + scrape with bearer auth:

```yaml
# prometheus.yml
- job_name: dreamapp
  scheme: https
  metrics_path: /metrics
  bearer_token: <your DREAM_METRICS_TOKEN>
  static_configs: [{ targets: ['dreamapp.example.com'] }]
```

Key metrics:
- `dreamapp_requests_total{status}` — RPS by status class
- `dreamapp_request_latency_bucket{le}` — 9-bucket histogram proxy
- `dreamapp_llm_calls_total{model,status,cached}` — LLM cost + cache hit
- `dreamapp_llm_tokens_total{kind}` — billable token usage
- `dreamapp_llm_cache_size` — current LRU size
- `dreamapp_rate_limited_total{path_bucket}` — abuse signal
- `dreamapp_video_generations_total{priority}` — Kling spend

### PostHog (optional product analytics)

```env
DREAM_POSTHOG_API_KEY=phc_...
DREAM_POSTHOG_HOST=https://us.posthog.com
```

Server emits the canonical event taxonomy from `services/analytics.py` —
see `DEFAULT_REVENUE_FUNNEL` for the funnel that's wired into the admin
dashboard at `/api/analytics/overview` (staff-only).

---

## 7 · Logs

Production logs are JSON-line on stdout. Pipe into Loki / Datadog / your
shipper of choice. Filter by `request_id` to follow a single request
across the LLM/Kling/MinIO chain:

```bash
docker compose logs backend | jq -c '. | select(.request_id=="abc123...")'
```

Useful queries:

```bash
# Slow requests
docker compose logs backend | jq -c '. | select(.duration_ms > 5000)'

# All payment webhook activity
docker compose logs backend | jq -c '. | select(.name=="dreamapp.payments")'

# Crisis flags fired in the last hour
docker compose logs backend | jq -c '. | select(.name=="dreamapp.crisis")'
```

---

## 8 · Updates

### Standard deploy (after a CI-green main commit)

```bash
cd /srv/dreamapp
git pull origin main
docker compose pull              # if backend image is rebuilt + pushed
docker compose up -d --build     # if backend Dockerfile changed
docker compose exec backend alembic upgrade head
docker compose logs -f backend
```

> Branch protection on main means anything you `git pull` has already
> passed CI (unit + alembic + frontend build) — you don't need to re-run
> tests on the prod box.

### Rollback

```bash
git log --oneline -10                          # find the last good SHA
git reset --hard <sha>
docker compose up -d --build
docker compose exec backend alembic downgrade <prev_revision>
```

> ⚠ Migrations are mostly idempotent but irreversible (HNSW indexes,
> schema drops). Test downgrades on a copy first.

---

## 9 · Scaling notes

The app is designed to start single-replica. To go multi-replica:

1. **Move rate-limiter to Redis** — current in-memory limiter doesn't
   share counts across replicas. See `services/middleware.py:RateLimitMiddleware`
   for the swap target.
2. **Move LLM cache to Redis** — same issue. `services/llm.py:_LLMCache`.
3. **Externalize MinIO** — bundled MinIO is fine for single-host; for
   multi-replica use real S3 + presigned URLs already work.
4. **Postgres connection pool** — `main.py` uses default pool; tune
   `pool_size` + `max_overflow` per replica count.
5. **WebSocket** — none yet. Notifications are polled via `/api/notifications`.

---

## 10 · One-shot health check

Drop this into cron or a status page:

```bash
#!/usr/bin/env bash
# Returns 0 if healthy, non-zero otherwise.
set -e
curl -sf https://dreamapp.example.com/api/health > /dev/null
docker compose -f /srv/dreamapp/docker-compose.yml ps --format json \
  | jq -e 'select(.Health == "healthy" or .State == "running")' > /dev/null
echo OK
```

---

## Common failure modes

| Symptom | Likely cause | Fix |
|---|---|---|
| Backend boots but `/api/dreams/start` 500s | LLM API key wrong | check `DREAM_LLM_API_KEY` |
| Payment webhooks all 4xx | sig env vars missing/wrong | inspect `payment_webhook_events.verified` |
| `/metrics` returns 401 | `DREAM_METRICS_TOKEN` set but Prometheus not sending bearer | fix scrape config |
| Frontend loads but API calls fail | CORS or proxy misconfig | check nginx + browser console |
| pgvector queries slow | HNSW index missing | check `\\d dreams` for `ix_dreams_embedding_hnsw` |
| Streak doesn't bump | dream record's `user_id` not set | check users.id col + auth flow |
| Crisis hotline phone number wrong locale | user.locale not propagated | check `users.locale` column population at register |
