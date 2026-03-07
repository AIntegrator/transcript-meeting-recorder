# AGENTS.md

## Cursor Cloud specific instructions

### Architecture

Single Django application (Python 3.10) with Celery worker, backed by PostgreSQL and Redis. All four services run via `docker compose -f dev.docker-compose.yml`. See `README.md` for full development setup instructions.

### Services (Docker Compose)

| Service | Container | Port |
|---|---|---|
| Django API | `recorder-api` | `8001 -> 8000` |
| Celery worker | `recorder-worker` | - |
| PostgreSQL 15 | `workspace-postgres-1` | 5432 (internal) |
| Redis 7 | `workspace-redis-1` | 6379 (internal) |

### Quick reference

- **Start services:** `sudo docker compose -f dev.docker-compose.yml up -d`
- **Run migrations:** `sudo docker compose -f dev.docker-compose.yml exec recorder-api python manage.py migrate`
- **Lint:** `ruff check` and `ruff format --check` (run from host, requires ruff==0.9.6)
- **Tests:** `sudo docker compose -f dev.docker-compose.yml exec recorder-api python manage.py test --settings=attendee.settings.development --verbosity=2`
- **Logs:** `sudo docker compose -f dev.docker-compose.yml logs -f`
- **Django shell:** `sudo docker compose -f dev.docker-compose.yml exec recorder-api python manage.py shell`
- **Stop:** `sudo docker compose -f dev.docker-compose.yml down`

### Gotchas

- The `.env` file must exist before starting containers. Generate with: `python3 init_env.py > .env`. The `init_env.py` script requires `cryptography` and `django` packages.
- The Makefile references `dev.docker-compose.yaml` (`.yaml` extension) but the actual file is `dev.docker-compose.yml` (`.yml` extension). Use the `.yml` filename directly.
- Ruff version must be 0.9.6 (matching `requirements.txt`). Newer versions reject `line-length = 999` in `pyproject.toml`.
- The `entrypoint.sh` starts PulseAudio (required for meeting recording). It runs automatically inside containers.
- Docker commands require `sudo` in the Cloud Agent environment.
- Pre-existing test failures exist (23 failures, 37 errors out of 202 tests) — these are in the repository, not caused by environment setup.
- The Swagger API docs are at `/schema/swagger-ui/` (not under `/api/v1/`).
- Email confirmation links appear in `recorder-api` container logs (console email backend).
