# Phase 1 — Foundation, Schema, Authentication & Authorization

## 1. What was implemented

- **Project setup**: feature-based Clean Architecture backend, environment-based
  config (`pydantic-settings`), structured logging, uniform error envelope,
  Docker + docker-compose, Alembic migrations, API versioning (`/api/v1`),
  OpenAPI/Swagger at `/docs`.
- **Database schema**: the complete data model (organizations, users, tokens,
  customers, work orders + notes/attachments/timeline, invoices + items) in one
  initial migration. See `docs/ER-DIAGRAM.md`.
- **Authentication**: login, refresh (with rotation), logout, forgot-password,
  reset-password, change-password, and `me`.
- **Authorization (RBAC)**: a role→permission matrix (`app/core/rbac.py`) with
  `require_permissions` / `require_roles` dependencies, plus a tenant-context
  dependency that derives `organization_id` from the authenticated user.

## 2. Security model

| Concern | Decision |
|---|---|
| Password storage | bcrypt, cost 12, per-password salt |
| Access token | JWT HS256, 30 min, carries `role` + `org` claims |
| Refresh token | JWT HS256, 7 days, **persisted by `jti` and rotated** on use |
| Token typing | `type` claim enforced — a refresh token can't be used as access |
| Logout | revokes the refresh token (idempotent) |
| Password change/reset | revokes **all** the user's refresh tokens |
| Account enumeration | uniform login error + uniform forgot-password response, with a dummy bcrypt verify on unknown emails to equalize timing |
| Tenant isolation | `organization_id` taken from the token's user, never from client input; CHECK constraint ties role↔org at the DB level |

## 3. API endpoints (`/api/v1/auth`)

| Method | Path | Auth | Body | Purpose |
|---|---|---|---|---|
| POST | `/login` | — | `{email, password}` | Issue access+refresh tokens |
| POST | `/refresh` | — | `{refresh_token}` | Rotate → new token pair |
| POST | `/logout` | — | `{refresh_token}` | Revoke refresh token |
| POST | `/forgot-password` | — | `{email}` | Begin reset (uniform response) |
| POST | `/reset-password` | — | `{token, new_password}` | Complete reset |
| POST | `/change-password` | Bearer | `{current_password, new_password}` | Change own password |
| GET | `/me` | Bearer | — | Current user profile |

Health: `GET /` and `GET /health`. Interactive docs: `GET /docs`.

### Error envelope

```json
{ "error": { "code": "authentication_error", "message": "Incorrect email or password", "details": {} } }
```

## 4. Testing instructions

### Automated

```powershell
cd backend

# Unit tests — no database required (12 tests: JWT, hashing, RBAC matrix)
.\.venv\Scripts\python.exe -m pytest tests/test_security.py tests/test_rbac.py -v

# Integration tests — require a throwaway Postgres
$env:TEST_DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/elangovan_test"
.\.venv\Scripts\python.exe -m pytest
```

> The unit tests and RBAC matrix pass locally (verified). The integration suite
> (`tests/test_auth_api.py`) needs PostgreSQL because the schema uses native
> `UUID`/`ENUM` types and a partial unique index; point `TEST_DATABASE_URL` at an
> empty database and it will create/drop the schema automatically.

### Manual (against a running server)

```powershell
# 0) one-time: create schema + super admin
alembic upgrade head
python -m app.cli seed-superadmin
uvicorn app.main:app --reload --port 8000

# 1) login
curl -s -X POST http://localhost:8000/api/v1/auth/login `
  -H "Content-Type: application/json" `
  -d '{\"email\":\"admin@keplercrew.com\",\"password\":\"ChangeMe!2026\"}'

# 2) call an authed endpoint (paste the access_token)
curl -s http://localhost:8000/api/v1/auth/me -H "Authorization: Bearer <ACCESS_TOKEN>"

# 3) refresh / logout use the refresh_token in the body
```

Or just open **http://localhost:8000/docs** and exercise the endpoints in Swagger.

## 5. Toolchain notes (Python 3.14)

This machine runs **Python 3.14.5**. Several pinned dependencies were advanced to
the first releases shipping cp314 wheels so nothing builds from source:
`sqlalchemy==2.0.46`, `alembic==1.16.5`, `pydantic==2.12.5`,
`pydantic-settings==2.11.0`, `bcrypt==5.0.0`, `psycopg[binary]==3.2.13`. These are
reflected in `requirements.txt`.
