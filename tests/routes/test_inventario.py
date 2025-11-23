import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import date
from uuid import uuid4
import base64

from src.app import app
from src.config import settings
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

def _mk_csv(lines):
    return ("\n".join(lines)).encode("utf-8")

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

def _mk_csv(lines):
    return ("\n".join(lines)).encode("utf-8")


@patch("src.routes.inventario.publish_event")
def test_upload_csv_async_publica_evento_ok(mock_publish_event, client):
    # 👇 Configurar TOPIC_INVENTARIO para el entorno de test
    settings.TOPIC_INVENTARIO = "projects/test/topics/test-inventario"

    proveedor_id = str(uuid4())
    csv_bytes = _mk_csv([
        "sku,nombre,categoria,temp_min,temp_max,controlado,precio,moneda,lead_time_dias,lote_minimo,activo",
        "SKU-1,Prod 1,Cat,1.5,10.2,true,100,COP,7,10,true",
        "SKU-2,Prod 2,Cat,0,25,false,200,COP,3,5,false",
    ])
    files = {"file": ("productos.csv", csv_bytes, "text/csv")}
    headers = {"X-Country": "co", "proveedor_id": proveedor_id}

    resp = client.post("/v1/inventario/productos/upload-csv", files=files, headers=headers)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "accepted"
    assert body["event"] == "creacion_masiva_producto"
    assert "trace_id" in body

    mock_publish_event.assert_called_once()
    kwargs = mock_publish_event.call_args.kwargs
    event = kwargs["data"]

    assert event["event"] == "creacion_masiva_producto"
    assert event["proveedor_id"] == proveedor_id
    assert event["ctx"]["country"] == "co"

    decoded_csv = base64.b64decode(event["csv_base64"]).decode("utf-8").strip()
    assert "SKU-1" in decoded_csv
    assert "SKU-2" in decoded_csv


@patch("src.routes.inventario.publish_event", side_effect=RuntimeError("Falla PubSub"))
def test_upload_csv_error_al_publicar_pubsub_retorna_500(mock_publish_event, client):
    # 👇 También aquí: si no se setea, nunca entra al branch de publish_event
    settings.TOPIC_INVENTARIO = "projects/test/topics/test-inventario"

    proveedor_id = str(uuid4())
    csv_bytes = _mk_csv([
        "sku,nombre,categoria,temp_min,temp_max,controlado,precio,moneda,lead_time_dias,lote_minimo,activo",
        "SKU-ERR,Prod,Cat,1,2,true,100,COP,1,1,true",
    ])
    files = {"file": ("productos.csv", csv_bytes, "text/csv")}
    headers = {"X-Country": "co", "proveedor_id": proveedor_id}

    resp = client.post("/v1/inventario/productos/upload-csv", files=files, headers=headers)

    assert resp.status_code == 500
    assert "Error publicando evento en Pub/Sub" in resp.text

# ---------- upload-csv: extensión inválida (400) ----------
def test_upload_csv_extension_invalida(client):
    proveedor_id = str(uuid4())
    files = {"file": ("productos.txt", b"cualquier cosa", "text/plain")}
    headers = {"X-Country": "co", "proveedor_id": proveedor_id}
    resp = client.post("/v1/inventario/productos/upload-csv", files=files, headers=headers)
    assert resp.status_code == 400
    assert "El archivo debe ser .csv" in resp.text  # inventario.py valida extensión .csv  :contentReference[oaicite:3]{index=3}


# ---------- upload-csv: proveedor_id inválido (400) ----------
def test_upload_csv_proveedor_id_invalido_400(client):
    files = {"file": ("productos.csv", b"sku,nombre\nS1,Prod\n", "text/csv")}
    headers = {"X-Country": "co", "proveedor_id": "no-es-uuid"}
    resp = client.post("/v1/inventario/productos/upload-csv", files=files, headers=headers)
    assert resp.status_code == 400
    assert "UUID válido" in resp.text  # conversión UUID en router  :contentReference[oaicite:4]{index=4}


# ---------- producto_detalle: cache con JSON inválido -> ignora cache y va a DB ----------
@patch("src.routes.inventario.svc.producto_detalle")
def test_producto_detalle_cache_invalido(mock_svc_call, client):
    producto_id = str(uuid4())
    # Respuesta del servicio (DB) válida
    mock_svc_call.return_value = {
        "id": producto_id, "sku": "SKU-X", "nombre": "X", "categoria": "A",
        "controlado": False, "stock_total": 0, "certificaciones": [], "lotes": []
    }

    with patch("src.routes.inventario.get_redis") as mock_get_redis:
        r = MagicMock()
        # Cache corrupto: bytes que NO son JSON válido del Pydantic
        r.get.return_value = b"{not-json"
        mock_get_redis.return_value = r

        resp = client.get(f"/v1/inventario/producto/{producto_id}/detalle")
        assert resp.status_code == 200
        # Al ser inválido, debe llamar a DB
        mock_svc_call.assert_called_once()
        # Y debe intentar setear nuevamente
        assert r.set.call_count == 1  # write-back del buen valor  :contentReference[oaicite:5]{index=5}


# ---------- producto_detalle: fallo al escribir en cache -> no rompe (warning) ----------
@patch("src.routes.inventario.svc.producto_detalle")
def test_producto_detalle_cache_set_falla_no_rompe(mock_svc_call, client, caplog):
    producto_id = str(uuid4())
    mock_svc_call.return_value = {
        "id": producto_id, "sku": "SKU-Y", "nombre": "Y", "categoria": "B",
        "controlado": False, "stock_total": 0, "certificaciones": [], "lotes": []
    }

    with patch("src.routes.inventario.get_redis") as mock_get_redis:
        r = MagicMock()
        r.get.return_value = None  # miss
        r.set.side_effect = RuntimeError("Falla Redis")
        mock_get_redis.return_value = r

        resp = client.get(f"/v1/inventario/producto/{producto_id}/detalle")
        assert resp.status_code == 200
        # Se registró un warning pero no se cae el endpoint  :contentReference[oaicite:6]{index=6}
        assert any("No se pudo escribir en Redis" in rec.message for rec in caplog.records)
