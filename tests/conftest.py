import os

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.db import get_db
from app.main import app


@pytest.fixture(scope="session")
def engine():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.fail("Set TEST_DATABASE_URL to a dedicated disposable PostgreSQL database")
    engine = create_engine(url, pool_pre_ping=True, isolation_level="READ COMMITTED")
    assert engine.dialect.name == "postgresql"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    command.upgrade(config, "head")
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def db_session(engine):
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE assignments, orders, couriers CASCADE"))
    with sessionmaker(bind=engine, autoflush=False)() as db:
        yield db


@pytest.fixture
def client(engine, db_session):
    sessions = sessionmaker(bind=engine, autoflush=False)

    def override_get_db():
        # Every request owns its Session/transaction, including simultaneous requests.
        with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client
    finally:
        app.dependency_overrides.clear()
