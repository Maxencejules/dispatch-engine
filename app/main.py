from fastapi import FastAPI
from app.routes import couriers, orders, dispatch

app = FastAPI(title="Dispatch Engine", version="0.1.0")

app.include_router(couriers.router)
app.include_router(orders.router)
app.include_router(dispatch.router)

@app.get("/health")
def health():
    return {"status": "ok"}
