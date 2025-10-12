
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from src.domain.models import Base

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
