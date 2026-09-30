# Dispatch Engine

A small FastAPI/PostgreSQL dispatch-service prototype. It reserves courier capacity
using a greedy distance/load/staleness score and stores a replayable assignment
receipt. It is an unauthenticated simulation: deployment requires access control,
operational tuning and a complete delivery lifecycle.

## Run locally

Python 3.11 or 3.12 and PostgreSQL 16 or 17 are covered by CI. Docker Compose can
start a local PostgreSQL 16 instance; an existing PostgreSQL server also works.
The Compose port binds to loopback and keeps the existing `dispatch_engine_pgdata`
volume name. These credentials are for local development only.

```bash
docker compose up -d --wait
python -m venv .venv
```

Activate `.venv` (`source .venv/bin/activate` on POSIX or
`.venv\Scripts\Activate.ps1` in PowerShell), then:

```bash
python -m pip install -c constraints.txt -e ".[dev]"
```

Set the application's database URL before running migrations or the server:

```bash
# POSIX
export DATABASE_URL='postgresql+psycopg://dispatch:dispatch@127.0.0.1:5432/dispatch'
```

```powershell
# PowerShell
$env:DATABASE_URL='postgresql+psycopg://dispatch:dispatch@127.0.0.1:5432/dispatch'
```

```bash
python -m alembic upgrade head
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open [API documentation](http://127.0.0.1:8000/docs).
`GET /health` checks database connectivity; `/metrics` exposes process-local
Prometheus counters. Matching logs include order, courier and assignment IDs.
`constraints.txt` records tested direct dependency versions; it does not freeze
every transitive/platform dependency. The application wheel contains the `app`
subpackages; migrations and demo scripts run from this repository.

## API and receipts

| Endpoint | Purpose |
| --- | --- |
| `POST /couriers` | Create `{lat, lng, capacity}`; capacity defaults to 1 |
| `GET /couriers/{id}` | Fetch courier |
| `PATCH /couriers/{id}/location` | Set `{lat, lng}` and refresh the heartbeat |
| `PATCH /couriers/{id}/status?status=offline` | Set `available`, `assigned` or `offline` |
| `POST /orders` | Create `{pickup_lat, pickup_lng, dropoff_lat, dropoff_lng}` |
| `GET /orders/{id}` | Fetch order |
| `POST /dispatch/match?order_id={id}` | Reserve capacity or replay the existing receipt |

Creation returns HTTP 200 and is **not idempotent**. Matching is idempotent by
order ID: retries return the same `assignment_id`, courier, score, timestamp,
reason and explanation, with `idempotent: true`. Newly committed assignments
return `idempotent: false`. Receipts survive process restarts; replay does not
re-score the current courier location or heartbeat.

```json
{
  "order_id": "...", "courier_id": "...", "assignment_id": "...",
  "score": 0.25, "assigned_at": "2026-09-29T12:00:00Z",
  "reason": "transactional_min_score",
  "explain": {"distance_km": 0.0, "load_ratio": 0.0, "staleness_min": 0.5},
  "idempotent": false
}
```

Coordinates must be finite JSON numbers within latitude ±90 and longitude ±180.
Capacity must be an integer from 1 through 2,147,483,647; booleans, strings and
fractional capacities are rejected. Path/query identifiers must be UUIDs.
Validation failures return 422 with `{code: "invalid_request", detail: [...]}`.
Other failures return a JSON `code` and `detail`:

| Status | Code | Meaning |
| --- | --- | --- |
| 404 | `order_not_found` / `courier_not_found` | Valid ID has no resource |
| 409 | `order_not_eligible` | No receipt and order is not unassigned |
| 409 | `no_couriers_available` | No eligible remaining capacity |
| 503 | `database_unavailable` | Database connectivity/pool failure |
| 500 | `internal_error` | Unexpected failure, details retained in server logs |

An interrupted response or database error can occur after a commit; retry the
**same order ID** to determine its persisted outcome. Rejected pre-commit matches
roll back order, courier and assignment changes together.

## Assignment correctness and scope

Matching locks the order first, then all currently available couriers in ascending
immutable ID order. Status/location writers take the same courier row lock.
Under explicit PostgreSQL `READ COMMITTED`, load is counted in a fresh statement
after those locks are acquired. Each stored assignment reserves one slot;
capacity cannot be exceeded by concurrent writers following this protocol.
The order uniqueness constraint remains a database guard. Recovery recognizes
only that exact uniqueness violation; unrelated integrity failures remain errors.

A partially filled courier stays available. Once full it becomes assigned.
Manually marking a full courier available does not erase its reservations;
offline/assigned couriers are excluded from new matching. Existing receipts
still replay when their courier goes offline. There is **no completion, capacity
release, cancellation API or assignment deletion** in this prototype: every
assignment row counts, including historical rows. Arbitrary external SQL writers
must follow the lock protocol; database checks alone do not enforce capacity.

The score is `distance_km + 2*load_ratio + 0.5*staleness_min`, with one shared clock
per match. Exact ties use courier ID order. Future heartbeats have zero staleness;
the great-circle distance handles antipodal rounding. This is a heuristic, not a
route/traffic model or an optimal fleet planner. Locking the whole eligible fleet
serializes overlapping matches and suits a small prototype; no throughput or
multi-region claim is made. Metrics are per process and restart with the API.

## Upgrade existing data

The new Alembic revision preserves IDs, statuses and assignment history. It adds
nullable JSON `assignments.explain`, a courier lookup index, and coordinate /
positive-capacity checks. Old receipts have `explain: null`; no historical scoring
explanation is fabricated. An upgrade refuses invalid coordinates/capacity or
already overbooked histories **before DDL** with an actionable error. Reconcile
such data explicitly before retrying; the migration never deletes/reassigns it.

Stop **all old assignment/status/location writers** before upgrading. Do not mix old and new
assignment protocols. Back up the database before schema changes. Downgrading
this revision removes its JSON explanations/checks/index while keeping the old
assignment records; removed explanations cannot be reconstructed.

## Verification and real HTTP demo

Tests require an explicit, dedicated disposable PostgreSQL database and truncate
its dispatch tables before/after each integration test. They never default to the
application database. Set `TEST_DATABASE_URL` separately, then:

```bash
python -m ruff check .
python -m pytest -q --junitxml=reports/pytest.xml
python -m pip wheel --no-deps --wheel-dir reports/wheels .
python scripts/wheel_smoke.py reports/wheels/dispatch_engine-0.1.0-py3-none-any.whl
```

Concurrency tests use independent request sessions, held PostgreSQL row locks and
`pg_stat_activity` to prove real overlap, including different orders competing
for capacity. Legacy migration fixtures use isolated schemas and check unchanged
history/schema on refusal. The wheel smoke installs into a separate environment
and imports outside the checkout, reusing installed third-party dependencies.

Against a server using a **fresh dedicated demo database**:

```bash
python scripts/http_demo.py
# Stop/restart the API with the same DATABASE_URL, then:
python scripts/http_demo.py --verify-receipts
```

The demo proves four parallel same-order requests share one assignment, two slots
can be filled, full/offline couriers cannot accept more work, errors are JSON,
and two persisted receipts replay identically after restart. It creates records
and leaves them in the demo database; it does not reset arbitrary data. CI runs
these checks across Python 3.11/3.12 and PostgreSQL 16/17 and uploads JUnit, wheel,
API log and receipt artifacts.

## License

MIT
