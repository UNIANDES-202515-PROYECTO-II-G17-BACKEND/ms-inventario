
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from uuid import uuid4
from datetime import date

from src.app import app
from src.domain.models import Base, CertificacionTipoEnum, PaisEnum, InventarioEstadoEnum
from src.dependencies import get_session

# --- Configuración de la Base de Datos y Mocks de Prueba ---
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Sobrescribimos la dependencia de la sesión de BD para usar la de prueba
def override_get_session():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
app.dependency_overrides[get_session] = override_get_session

@pytest.fixture(scope="function", autouse=True)
def apply_mocks():
    """Fixture para crear la BD y mockear Redis para cada test."""
    Base.metadata.create_all(bind=engine)
    with patch('src.routes.inventario.get_redis') as mock_get_redis:
        mock_redis_instance = MagicMock()
        mock_redis_instance.get.return_value = None # Default: cache miss
        mock_get_redis.return_value = mock_redis_instance
        yield mock_redis_instance
    Base.metadata.drop_all(bind=engine)

client = TestClient(app)

# ---------- PRODUCTO ----------
@patch('src.routes.inventario.svc.crear_producto')
def test_crear_producto_exitoso(mock_svc_call):
    producto_data = {"sku": "SKU-TEST-001", "nombre": "Producto de Prueba", "categoria": "A", "controlado": False, "temp_min": 10.0, "temp_max": 20.0}
    mock_return = MagicMock(id=uuid4(), **producto_data)
    mock_svc_call.return_value = mock_return
    response = client.post("/v1/inventario/producto", json=producto_data)
    assert response.status_code == 200
    assert response.json()["sku"] == producto_data["sku"]

@patch('src.routes.inventario.svc.crear_producto')
def test_crear_producto_conflicto(mock_svc_call):
    producto_data = {"sku": "SKU-EXISTENTE", "nombre": "Producto Existente", "categoria": "B", "controlado": True, "temp_min": 0, "temp_max": 0}
    mock_svc_call.side_effect = ValueError("El SKU 'SKU-EXISTENTE' ya existe")
    response = client.post("/v1/inventario/producto", json=producto_data)
    assert response.status_code == 409

# ---------- CERTIFICACION ----------
@patch('src.routes.inventario.svc.asociar_certificacion')
def test_agregar_certificacion_exitosa(mock_svc_call):
    producto_id = uuid4()
    cert_data = {"autoridad": "INVIMA", "tipo": "INVIMA", "vigencia": "2025-12-31"}
    mock_return = MagicMock(id=uuid4(), autoridad=cert_data["autoridad"], tipo=CertificacionTipoEnum.INVIMA, vigencia=date.fromisoformat(cert_data["vigencia"]))
    mock_svc_call.return_value = mock_return
    response = client.post(f"/v1/inventario/producto/{producto_id}/certificacion", json=cert_data)
    assert response.status_code == 200

# ... (resto de tests que no interactúan con el cache) ...

# ---------- CONSULTAS CON CACHE ----------
@patch('src.routes.inventario.svc.producto_detalle')
def test_producto_detalle_sin_cache(mock_svc_call, apply_mocks):
    """Test con cache miss (comportamiento por defecto del mock)."""
    producto_id = uuid4()
    mock_svc_call.return_value = {"id": producto_id, "sku": "SKU123", "nombre": "Test", "categoria": "A", "controlado": False, "stock_total": 0, "certificaciones": [], "lotes": []}
    
    response = client.get(f"/v1/inventario/producto/{producto_id}/detalle")
    
    assert response.status_code == 200
    mock_svc_call.assert_called_once() # Se llamó a la DB
    apply_mocks.get.assert_called_once_with(f"co-{producto_id}") # Se intentó leer de Redis
    apply_mocks.set.assert_called_once() # Se intentó escribir en Redis

@patch('src.routes.inventario.svc.producto_detalle')
def test_producto_detalle_con_cache(mock_svc_call, apply_mocks):
    """Test con cache hit, configurando el mock que nos da el fixture."""
    producto_id = uuid4()
    mock_json_data = f'{{"id": "{producto_id}", "sku": "SKU-CACHE", "nombre": "Producto Cacheado", "categoria": "A", "controlado": false, "stock_total": 120, "certificaciones": [], "lotes": []}}'
    
    # Personalizamos el mock para este test
    apply_mocks.get.return_value = mock_json_data.encode('utf-8')

    response = client.get(f"/v1/inventario/producto/{producto_id}/detalle")
    
    assert response.status_code == 200
    assert response.json()['nombre'] == "Producto Cacheado"
    mock_svc_call.assert_not_called() # No se debe llamar a la DB
    apply_mocks.get.assert_called_once_with(f"co-{producto_id}") # Se leyó de Redis
    apply_mocks.set.assert_not_called() # No se escribió en Redis
