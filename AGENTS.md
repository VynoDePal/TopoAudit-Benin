# Repository Notes

- Monorepo scaffold: `apps/api` contains FastAPI, `apps/web` contains Next.js, and root `docker-compose.yml` orchestrates PostGIS, API, and web.
- `apps/api/requirements.txt` must be treated as append-only for dependency updates; never regenerate or delete existing lines. Add only pinned dependencies.
- Root `pytest.ini` points pytest at `apps/api/tests` and sets `pythonpath = apps/api` to avoid the previous gate failure where PostGIS started but pytest reported `no tests ran`.
- Docker is not available in the current execution environment, so Compose validation may need to be performed by CI/gate.
- Issue #3 adds `apps/api/app/models.py` with SQLAlchemy 2 models (`Project`, `Document`, `Parcel`, `SurveyPoint`) and GeoAlchemy2 PostGIS geometry columns. `SurveyPoint.geom` accepts GeoJSON Point dicts via assignment coercion to `WKTElement` SRID 4326.
- CRS conversion lives in `apps/api/app/crs.py`; it uses `pyproj.Transformer.from_crs(..., always_xy=True)` and returns GeoJSON-ready EPSG:4326 coordinates in `[longitude, latitude]` order. The API exposes it via `POST /api/crs/transform`.
- API route modules should avoid eager imports that require optional/runtime-only database drivers or GeoAlchemy2; keep database engine creation lazy so existing endpoint tests can import `app.main` in minimal environments.
- OCR lives in `apps/api/app/ocr.py` and is exposed via `/api/projects/{project_id}/documents/{document_id}/ocr` plus `/api/ocr`; it validates project/document consistency with SQL text queries before OCR, rate-limits per client in memory, uses mock text when Azure credentials are absent, and must never log Azure keys.

- Geometry validation lives in `apps/api/app/geometry_engine.py` and is exposed at `POST /api/geometry/validate-polygon`; it uses Shapely, normalizes EPSG:4326 Benin latitude/longitude inversions to longitude/latitude, flags self-intersections, and transforms UTM EPSG:32631 polygon rings to GeoJSON-ready EPSG:4326.


- Frontend MapLibre integration lives in `apps/web/app/components/ParcelMap.tsx`; it must remain client-side (`"use client"` / dynamic import with `ssr: false`) because MapLibre depends on browser APIs.

