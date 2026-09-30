from fastapi import FastAPI
from prometheus_client import generate_latest
from sqlalchemy import text
from starlette.responses import Response

from app.db import DbSession
from app.errors import install_error_handlers
from app.logging import setup_logging
from app.routes import couriers, dispatch, orders

setup_logging()

app = FastAPI(title="Dispatch Engine", version="0.1.0")
install_error_handlers(app)

app.include_router(couriers.router)
app.include_router(orders.router)
app.include_router(dispatch.router)


@app.get("/health")
def health(db: DbSession):
    db.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type="text/plain")
