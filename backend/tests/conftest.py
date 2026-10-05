import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.core import secrets
from app.database import get_db
from app.main import app
from app.models import Base

# Chiave di cifratura usa e getta: i test non leggono né creano backend/.secrets_key
settings.secrets_key = Fernet.generate_key().decode()
secrets._fernet.cache_clear()


@pytest.fixture()
def session_factory():
    """Database SQLite in memoria: i test non toccano Postgres."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_connection, _record):
        # pysqlite gestisce da solo BEGIN/COMMIT e rompe i SAVEPOINT: lo disattivo e lo emetto io
        dbapi_connection.isolation_level = None
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    @event.listens_for(engine, "begin")
    def _on_begin(connection):
        connection.exec_driver_sql("BEGIN")

    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    engine.dispose()


@pytest.fixture()
def client(session_factory):
    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
