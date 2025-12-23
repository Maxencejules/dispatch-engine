from fastapi import FastAPI
from prometheus_client import generate_latest
from starlette.responses import Response

from app.logging import setup_logging
from app.routes import couriers, orders, dispatch

setup_logging()

app = FastAPI(title="Dispatch Engine", version="0.1.0")

app.include_router(couriers.router)
app.include_router(orders.router)
app.include_router(dispatch.router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type="text/plain")
