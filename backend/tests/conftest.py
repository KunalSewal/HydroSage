import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings


@pytest.fixture()
def db_session():
    """A real Postgres session (via the Docker Compose `postgis` service)
    wrapped in a transaction that's rolled back after the test. Uses a
    SAVEPOINT so a `session.commit()` inside the code under test (e.g. an
    endpoint that legitimately needs to commit in production) doesn't end
    the outer transaction early -- without this, rollback() at teardown
    becomes a silent no-op and test data leaks permanently into the shared
    dev database."""
    settings = get_settings()
    engine = create_engine(settings.database_url)
    connection = engine.connect()
    transaction = connection.begin()
    TestSession = sessionmaker(bind=connection)
    session = TestSession()

    nested = connection.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def restart_savepoint(sess, trans):
        nonlocal nested
        if not nested.is_active:
            nested = connection.begin_nested()

    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
        engine.dispose()
