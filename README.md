# MUDHOTECH HR RECRUITING SYSTEM

AI-powered, human-controlled recruitment platform and Applicant Tracking System by **MudhoTech Solutions (Pvt) Ltd**, Harare, Zimbabwe.

Organisations advertise vacancies, receive applications and CVs, ask job-specific screening questions, and get
**explainable, evidence-based** candidate assessments. HR staff stay in control of every shortlist, interview,
offer and hiring decision.

**Stack:** Next.js + TypeScript · Django + DRF · PostgreSQL (pgvector) · Celery + Redis · S3 · Docker · AWS

## Repository guide
| Path | Purpose |
|---|---|
| `CLAUDE.md` | Project memory & rules for the Claude Code agent (read first) |
| `PROGRESS.md` | Live implementation tracker (phases, tasks, session log) |
| `AGENT_START_PROMPT.md` | Prompt to start/resume the agent |
| `docs/` | Final specifications (SRS, architecture, DB, API, AI engine, security, edge cases, UI, testing, ops, decisions, glossary) |
| `phases/` | 16 implementation phases with task checklists and exit criteria |
| `backend/`, `frontend/`, `infrastructure/`, `scripts/` | Created during Phase 01 |

## Roadmap
| Release | Phases | Outcome |
|---|---|---|
| MVP / v1.0 pilot | 01–11 | Multi-tenant ATS + AI-assisted screening + human shortlist approval, live on AWS |
| v1.1 | 12–14 | Interviews, offers & hiring, talent pool, analytics, platform admin & Paynow billing |
| v1.2 | 15–16 | Integrations (calendar, SSO, SMS/WhatsApp, webhooks, public API), localisation, final release |

## Quick start
Prerequisites: Docker Desktop (WSL2 backend), Git, Node.js LTS (optional, for frontend tooling outside Docker).

```powershell
git clone <repo-url> "D:\mudhotech_2026\MUDHOTECH HR RECRUITING SYSTEM"
cd "D:\mudhotech_2026\MUDHOTECH HR RECRUITING SYSTEM"
./scripts/dev-up.ps1        # copies .env.example -> .env, builds & starts the stack, migrates, seeds
```
```bash
./scripts/dev-up.sh         # same on Git Bash / WSL / Linux / macOS
```

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| API | http://localhost:8000/api/v1/ |
| API docs (Swagger) | http://localhost:8000/api/docs/ |
| Mailpit | http://localhost:8025 |
| S3 (SeaweedFS, dev) | http://localhost:9000 (filer UI :8888) |
| Flower | http://localhost:5555 |

The repository path contains spaces: always quote paths. `docker-compose.yml` sets `name: mhrs`.

Source blueprint: `MUDHOTECH_HR_RECRUITING_SYSTEM_Complete_Project_Blueprint.docx`.
