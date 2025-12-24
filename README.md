# Dispatch Engine

A production-style dispatching service (DoorDash-style) built with FastAPI + Postgres.
Implements courier/order management, a scoring-based matching algorithm, transactional assignment with idempotency, observability (Prometheus metrics), and CI.

## Features
- Couriers API: create couriers, update location/status, fetch by id
- Orders API: create orders, fetch by id
- Dispatch matching using a scoring function (distance, load, staleness)
- Concurrency-safe assignment with row-level locking and idempotency
- Observability via Prometheus metrics and structured logging
- Unit and integration tests (Postgres-backed)
- GitHub Actions CI (lint + tests)

## Architecture

Client / Swagger
        |
        v
   FastAPI App
      |    |
      |    +--> Matching Algorithm
      |
      +--> Postgres
      |
      +--> /metrics (Prometheus)

## Local Setup

### Requirements
- Python 3.11+ (recommended 3.12)
- Docker Desktop

### Start Postgres:
docker compose up -d

### Install dependencies:
python -m venv .venv
# Windows
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"

### Run migrations:
alembic upgrade head

### Run the API:
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload

Open:
- Swagger UI: http://127.0.0.1:8000/docs
- Metrics: http://127.0.0.1:8000/metrics

## Testing:
python -m pytest -q

## Notes on correctness
Dispatch assignment is protected by:
- SELECT ... FOR UPDATE on the order row
- Uniqueness constraint on assignments.order_id
- IntegrityError recovery to ensure idempotent behavior

## License
MIT
