# DreamApp

Dream Operating System — Record dreams, visualize them as cinematic AI videos, interpret with multi-dimensional psychology, build automated dream agents.

## Quick Start

### Docker (Recommended)

```bash
cp backend/.env.example backend/.env  # Fill in API keys
docker compose up -d
# Open http://localhost
```

### Local Development

```bash
# Backend
cd backend && python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Fill in API keys
python main.py  # http://localhost:8000

# Frontend
cd frontend && npm install
npm run dev:h5        # Dev: http://localhost:5173
npm run build:h5      # Build H5
npm run build -p mp-weixin  # Build WeChat MP
```

## Architecture

```
Phase 1 (捕梦器):
  Record → AI Interview → Dream Script → AI Director → Multi-Shot Video → Interpretation

Phase 2 (梦境OS):
  Entity Extraction → Cross-Temporal Correlation → Health Index
  Dream Incubation → Dream IP → Agent System → Vibe Coder
```

## Tech Stack

- **Backend**: Python FastAPI (32 files, 42 endpoints)
- **Frontend**: uni-app Vue 3 (9 pages) → H5 / WeChat MP / Android
- **Database**: SQLite (dev) / PostgreSQL (production)
- **LLM**: MiniMax m2.5-highspeed via api.minimax.chat
- **Video**: Kling v3 via openapi.klingai.com
- **Knowledge**: 7 databases, 500KB+ (symbols, archetypes, narratives, TCM, film techniques, dream corpus, incubation)

## API Endpoints (42)

### Dreams
| Method | Path | Description |
|--------|------|-------------|
| POST | /api/dreams/start | Start dream interview |
| POST | /api/dreams/chat | Continue interview |
| POST | /api/dreams/{id}/generate | Generate multi-shot video |
| GET | /api/dreams/{id}/video-status | Poll video generation |
| POST | /api/dreams/{id}/interpret | Multi-dimensional interpretation |
| POST | /api/dreams/{id}/rewrite | Nightmare rewrite (IRT therapy) |
| POST | /api/dreams/{id}/extract-entities | Extract dream entities |
| POST | /api/dreams/voice-to-text | Voice to text |
| GET | /api/dreams/ | List dreams |
| GET | /api/dreams/{id} | Get dream detail |

### Entities & Correlation
| GET | /api/entities/entities | List entities with counts |
| GET | /api/entities/correlations | Cross-dream correlations |
| GET | /api/entities/timeline | Entity appearance timeline |
| POST | /api/entities/correlate | Run correlation analysis |

### Health
| GET | /api/health/current | Current health metrics |
| GET | /api/health/anomalies | Detect anomalies |
| POST | /api/health/generate-report | Generate health report |

### Incubation
| POST | /api/incubation/start | Start dream incubation |
| GET | /api/incubation/{id} | Get session details |
| POST | /api/incubation/{id}/link-dream | Link dream to session |

### Dream IP
| GET | /api/ips/ | List personal mythology |
| POST | /api/ips/detect | Scan for recurring elements |

### Social
| GET | /api/plaza/dreams | Browse public dreams |
| GET | /api/plaza/trending | Trending themes |
| POST | /api/plaza/dreams/{id}/publish | Publish to plaza |

### Agents
| POST | /api/agents/create | Create agent |
| POST | /api/agents/{id}/run | Run agent |
| GET | /api/store/agents | Browse agent store |
| POST | /api/vibe/customize | Customize app layout (NL) |

### Users
| POST | /api/users/register | Register user |
| GET | /api/users/me | Get profile |

## Docker Services

| Service | Port | Description |
|---------|------|-------------|
| db | 5432 | PostgreSQL 16 |
| backend | 8000 | FastAPI |
| frontend | 80 | Nginx + H5 SPA |
