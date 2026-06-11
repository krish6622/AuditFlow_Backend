# AuditFlow — Backend

FastAPI backend for **AuditFlow** (formerly Elangovan Associates): a multi-tenant
SaaS for small field-service businesses (electrical, plumbing, AC, auditing) to
manage **employees, work orders, and invoices**.

> **Status — Phase 1 complete:** project setup, full database schema,
> authentication & RBAC. Later phases add organization, employee, customer,
> work-order, invoice, and dashboard features.

The React frontend lives in the sibling **`AuditFlow_UI`** project.

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Python · FastAPI · SQLAlchemy 2 · Alembic |
| Database | PostgreSQL (Neon in prod) |
| Auth | JWT (access + rotating refresh) · bcrypt · RBAC |
| Storage / PDF | Cloudflare R2 · ReportLab *(wired from later phases)* |
| Deploy | Backend → Railway · DB → Neon |

## Architecture

Clean, **feature-based** layout. Each feature owns its `schemas` (Pydantic),
`repository` (data access), `service` (business rules), and `router` (HTTP).
Cross-cutting concerns live in `app/core`.

```
app/
├── main.py                 # app factory, CORS, exception handlers, router mount
├── cli.py                  # `python -m app.cli seed-superadmin`
├── api/v1/router.py        # versioned API aggregation (/api/v1)
├── core/                   # config, security (JWT/bcrypt), rbac,
│                           #   dependencies (auth/tenant), logging, exceptions
├── db/                     # declarative Base + mixins, engine/session
├── models/                 # SQLAlchemy models (full schema) + enums
└── features/
    ├── auth/               # login/refresh/logout/forgot/reset/change/me
    ├── organizations/      # (Phase 2)
    └── employees/          # (Phase 3)
alembic/                    # migrations (0001 = initial schema)
tests/                      # unit (no DB) + integration (Postgres)
docs/ER-DIAGRAM.md          # full data model + design rationale
docker-compose.yml          # Postgres + API for local dev
Dockerfile
requirements.txt
.env.example
```

## Quick start (local, without Docker)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

Copy-Item .env.example .env        # then set JWT_SECRET_KEY + DATABASE_URL
python -c "import secrets; print(secrets.token_urlsafe(64))"   # -> JWT_SECRET_KEY

alembic upgrade head               # create the schema
python -m app.cli seed-admin       # create the bootstrap org + first ADMIN from .env
python -m app.cli seed-demo        # (optional) + sample employees & audit activity
uvicorn app.main:app --reload --port 8000
```

Open **http://localhost:8000/docs** for interactive Swagger UI.

## Quick start (Docker)

```bash
cp .env.example .env     # set JWT_SECRET_KEY
docker compose up --build
docker compose exec api python -m app.cli seed-admin
```

## Configuration

All configuration is environment-based (`.env`, see `.env.example`). Nothing
environment-specific is hardcoded. Key variables: `DATABASE_URL`,
`JWT_SECRET_KEY`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `REFRESH_TOKEN_EXPIRE_DAYS`,
`CORS_ORIGINS`, `SUPERADMIN_EMAIL`/`SUPERADMIN_PASSWORD`.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_security.py tests/test_rbac.py   # no DB needed

# Integration tests (need a throwaway Postgres):
$env:TEST_DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/elangovan_test"
.\.venv\Scripts\python.exe -m pytest
```

## Deployment notes

- **Backend → Railway:** set `DATABASE_URL` (Neon), `JWT_SECRET_KEY`,
  `ENVIRONMENT=production`, `CORS_ORIGINS` (Vercel URL). The Docker `CMD` runs
  `alembic upgrade head` before starting Uvicorn on `$PORT`.
- **Database → Neon:** append `?sslmode=require` to the connection string.

See `docs/ER-DIAGRAM.md` for the data model and `docs/PHASE-1.md` for the API
reference and testing walkthrough.
