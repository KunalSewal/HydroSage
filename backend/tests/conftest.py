import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings


@pytest.fixture()
def db_session():
    """A real Postgres session (via the Docker Compose `postgis` service)
    wrapped in a transaction that's rolled back after the test, so tests
    don't leave data behind or depend on ordering."""
    settings = get_settings()
    engine = create_engine(settings.database_url)
    connection = engine.connect()
    transaction = connection.begin()
    TestSession = sessionmaker(bind=connection)
    session = TestSession()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
        engine.dispose()
