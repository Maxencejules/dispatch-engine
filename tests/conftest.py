import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.db import get_db
from app.models import Base


TEST_DB_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://dispatch:dispatch@localhost:5432/dispatch",
)


@pytest.fixture(scope="session")
def engine():
    engine = create_engine(TEST_DB_URL, pool_pre_ping=True)
    return engine


@pytest.fixture(scope="function")
def db_session(engine):
    Base.metadata.create_all(bind=engine)

    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = SessionLocal()

    db.execute(text("TRUNCATE TABLE assignments, orders, couriers RESTART IDENTITY CASCADE;"))
    db.commit()

    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="function")
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
