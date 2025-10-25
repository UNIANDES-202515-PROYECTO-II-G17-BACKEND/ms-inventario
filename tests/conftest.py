from src.domain.models import Base
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from unittest.mock import patch, MagicMock

from src.app import app
# IMPORTA EL MÓDULO COMPLETO PARA REGISTRAR TODAS LAS TABLAS
from src.domain import models as models_mod
from src.dependencies import get_session

# Usar una base de datos SQLite en memoria para las pruebas
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="function")
def session():
    """Crea una nueva sesión de base de datos para cada prueba y limpia después."""
    # Crear todas las tablas
    Base.metadata.create_all(bind=engine)
    
    db_session = TestingSessionLocal()
    
    try:
        yield db_session
    finally:
        db_session.close()
        # Eliminar todas las tablas para la siguiente prueba
        Base.metadata.drop_all(bind=engine)





# --- DB de prueba en memoria, compartida en toda la suite ---
engine = create_engine(
    "sqlite+pysqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,         # <--- clave para compartir la misma conexión
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="session", autouse=True)
def _create_db_schema_once():
    # Crear todas las tablas definidas en src.domain.models
    models_mod.Base.metadata.create_all(bind=engine)
    yield
    models_mod.Base.metadata.drop_all(bind=engine)

@pytest.fixture()
def db_session():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

@pytest.fixture()
def client(db_session):
    # Override de la dependencia de sesión para FastAPI
    def override_get_session():
        try:
            yield db_session
        finally:
            pass
    app.dependency_overrides[get_session] = override_get_session

    # Mock opcional de Redis si tu router lo usa
    with patch("src.routes.inventario.get_redis") as mock_get_redis:
        mock_redis = MagicMock()
        mock_redis.get.return_value = None  # cache miss por defecto
        mock_get_redis.return_value = mock_redis

        c = TestClient(app)
        yield c

    app.dependency_overrides.pop(get_session, None)

