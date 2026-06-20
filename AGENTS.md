# Repository Notes

- Monorepo scaffold: `apps/api` contains FastAPI, `apps/web` contains Next.js, and root `docker-compose.yml` orchestrates PostGIS, API, and web.
- `apps/api/requirements.txt` must be treated as append-only for dependency updates; never regenerate or delete existing lines. Add only pinned dependencies.
- Root `pytest.ini` points pytest at `apps/api/tests` and sets `pythonpath = apps/api` to avoid the previous gate failure where PostGIS started but pytest reported `no tests ran`.
- Docker is not available in the current execution environment, so Compose validation may need to be performed by CI/gate.
