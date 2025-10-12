
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from uuid import uuid4
from datetime import date, datetime

# Asumimos que la app se puede importar de esta manera
from src.app import app
from src.domain.models import CertificacionTipoEnum, PaisEnum, InventarioEstadoEnum

client = TestClient(app)

# ---------- PRODUCTO ----------
@patch('src.routes.inventario.svc.crear_producto')
def test_crear_producto_exitoso(mock_svc_call):
    producto_data = {
        "sku": "SKU-TEST-001", "nombre": "Producto de Prueba", "categoria": "A",
        "controlado": False, "temp_min": 10.0, "temp_max": 20.0
    }
    mock_return = MagicMock()
    mock_return.id = uuid4()
    mock_return.sku = producto_data["sku"]
    mock_return.nombre = producto_data["nombre"]
    mock_return.categoria = producto_data["categoria"]
    mock_return.controlado = producto_data["controlado"]
    mock_svc_call.return_value = mock_return

    response = client.post("/v1/inventario/producto", json=producto_data)
    assert response.status_code == 200
    assert response.json()["sku"] == producto_data["sku"]

@patch('src.routes.inventario.svc.crear_producto')
def test_crear_producto_conflicto(mock_svc_call):
    producto_data = {"sku": "SKU-EXISTENTE", "nombre": "Producto Existente", "categoria": "B", "controlado": True, "temp_min": 0, "temp_max": 0}
    error_message = "El SKU 'SKU-EXISTENTE' ya existe"
    mock_svc_call.side_effect = ValueError(error_message)
    response = client.post("/v1/inventario/producto", json=producto_data)
    assert response.status_code == 409
    assert response.json() == {"detail": error_message}

# ---------- CERTIFICACION ----------
@patch('src.routes.inventario.svc.asociar_certificacion')
def test_agregar_certificacion_exitosa(mock_svc_call):
    producto_id = uuid4()
    # Corregido: Usar un valor válido del Enum, ej: "INVIMA"
    cert_data = {"autoridad": "INVIMA", "tipo": "INVIMA", "vigencia": "2025-12-31"}
    
    mock_return = MagicMock()
    mock_return.id = uuid4()
    mock_return.autoridad = cert_data["autoridad"]
    mock_return.tipo = CertificacionTipoEnum.INVIMA
    mock_return.vigencia = date.fromisoformat(cert_data["vigencia"])
    mock_svc_call.return_value = mock_return

    response = client.post(f"/v1/inventario/producto/{producto_id}/certificacion", json=cert_data)
    assert response.status_code == 200
    assert response.json()["autoridad"] == cert_data["autoridad"]

@patch('src.routes.inventario.svc.asociar_certificacion')
def test_agregar_certificacion_producto_no_existe(mock_svc_call):
    producto_id = uuid4()
    # Corregido: Usar un valor válido del Enum
    cert_data = {"autoridad": "INVIMA", "tipo": "INVIMA", "vigencia": "2025-12-31"}
    error_message = f"Producto no existe: {producto_id}"
    mock_svc_call.side_effect = ValueError(error_message)
    response = client.post(f"/v1/inventario/producto/{producto_id}/certificacion", json=cert_data)
    assert response.status_code == 404
    assert response.json() == {"detail": error_message}

# ---------- BODEGA / UBICACION ----------
@patch('src.routes.inventario.svc.crear_bodega')
def test_crear_bodega_exitosa(mock_svc_call):
    # Corregido: Usar valor en minúscula para el país, ej: "co"
    bodega_data = {"direccion": "Calle Falsa 123", "ciudad": "Springfield", "pais": "co"}
    mock_return = MagicMock()
    mock_return.id = uuid4()
    mock_return.direccion = bodega_data["direccion"]
    mock_return.ciudad = bodega_data["ciudad"]
    mock_return.pais = PaisEnum.CO
    mock_svc_call.return_value = mock_return

    response = client.post("/v1/inventario/bodega", json=bodega_data)
    assert response.status_code == 200
    assert response.json()["direccion"] == bodega_data["direccion"]

@patch('src.routes.inventario.svc.crear_bodega')
def test_crear_bodega_conflicto(mock_svc_call):
    # Corregido: Usar valor en minúscula para el país
    bodega_data = {"direccion": "Calle Falsa 123", "ciudad": "Springfield", "pais": "co"}
    error_message = "La bodega en 'Calle Falsa 123' ya existe"
    mock_svc_call.side_effect = ValueError(error_message)
    response = client.post("/v1/inventario/bodega", json=bodega_data)
    assert response.status_code == 409
    assert response.json() == {"detail": error_message}

@patch('src.routes.inventario.svc.crear_ubicacion')
def test_crear_ubicacion_exitosa(mock_svc_call):
    bodega_id = uuid4()
    ubicacion_data = {"bodega_id": str(bodega_id), "pasillo": "A", "estante": "1", "posicion": "1"}
    mock_return = MagicMock()
    mock_return.id = uuid4()
    mock_return.bodega_id = bodega_id
    mock_return.pasillo = ubicacion_data["pasillo"]
    mock_return.estante = ubicacion_data["estante"]
    mock_return.posicion = ubicacion_data["posicion"]
    mock_svc_call.return_value = mock_return

    response = client.post("/v1/inventario/ubicacion", json=ubicacion_data)
    assert response.status_code == 200
    assert response.json()["pasillo"] == "A"

# ---------- LOTE ----------
@patch('src.routes.inventario.svc.crear_lote')
def test_crear_lote_exitoso(mock_svc_call):
    producto_id = uuid4()
    lote_data = {"producto_id": str(producto_id), "codigo": "LOTE-001", "vencimiento": "2025-01-01"}
    mock_return = MagicMock()
    mock_return.id = uuid4()
    mock_return.producto_id = producto_id
    mock_return.codigo = lote_data["codigo"]
    mock_return.vencimiento = date.fromisoformat(lote_data["vencimiento"])
    mock_svc_call.return_value = mock_return

    response = client.post("/v1/inventario/lote", json=lote_data)
    assert response.status_code == 200
    assert response.json()["codigo"] == lote_data["codigo"]

# ---------- INVENTARIO ----------
@patch('src.routes.inventario.svc.recibir_entrada')
def test_entrada_exitosa(mock_svc_call):
    lote_id = uuid4()
    ubicacion_id = uuid4()
    entrada_data = {"lote_id": str(lote_id), "ubicacion_id": str(ubicacion_id), "cantidad": 100, "estado": "DISPONIBLE"}
    mock_return = MagicMock()
    mock_return.id = uuid4()
    mock_return.lote_id = lote_id
    mock_return.ubicacion_id = ubicacion_id
    mock_return.cantidad = entrada_data["cantidad"]
    mock_return.estado = InventarioEstadoEnum.DISPONIBLE
    mock_return.fecha_ingreso = datetime.now()
    mock_svc_call.return_value = mock_return

    response = client.post("/v1/inventario/entrada", json=entrada_data)
    assert response.status_code == 200
    assert response.json()["cantidad"] == 100

@patch('src.routes.inventario.svc.recibir_entrada')
def test_entrada_lote_o_ubicacion_no_existen(mock_svc_call):
    entrada_data = {"lote_id": str(uuid4()), "ubicacion_id": str(uuid4()), "cantidad": 100, "estado": "DISPONIBLE"}
    error_message = "Lote no existe"
    mock_svc_call.side_effect = ValueError(error_message)
    response = client.post("/v1/inventario/entrada", json=entrada_data)
    assert response.status_code == 404
    assert response.json() == {"detail": error_message}

@patch('src.routes.inventario.svc.recibir_entrada')
def test_entrada_error_de_negocio(mock_svc_call):
    entrada_data = {"lote_id": str(uuid4()), "ubicacion_id": str(uuid4()), "cantidad": -10, "estado": "DISPONIBLE"}
    error_message = "La cantidad debe ser positiva"
    mock_svc_call.side_effect = ValueError(error_message)
    response = client.post("/v1/inventario/entrada", json=entrada_data)
    assert response.status_code == 400
    assert response.json() == {"detail": error_message}

# ---------- CONSULTAS ----------
@patch('src.routes.inventario.svc.stock_detallado')
def test_stock_detalle(mock_svc_call):
    producto_id = uuid4()
    mock_data = [{
        "codigo": "LOTE-A", "vencimiento": date.today(), 
        "ubicacion_id": uuid4(), "cantidad": 100
    }]
    mock_svc_call.return_value = mock_data
    response = client.get(f"/v1/inventario/stock/{producto_id}/detalle")
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["codigo"] == "LOTE-A"

@patch('src.routes.inventario.svc.ubicaciones_con_stock_por_producto')
def test_ubicaciones_con_stock_producto_existente(mock_svc_call):
    producto_id = uuid4()
    mock_data = [{
        "ubicacion_id": uuid4(), "bodega_id": uuid4(), "ciudad": "Bogota",
        "pasillo": "A1", "estante": "B2", "posicion": "C3", "cantidad": 100
    }]
    mock_svc_call.return_value = mock_data
    response = client.get(f"/v1/inventario/producto/{producto_id}/ubicaciones")
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["pasillo"] == "A1"

@patch('src.routes.inventario.get_redis', return_value=None)
@patch('src.routes.inventario.svc.producto_detalle')
def test_producto_detalle_sin_cache(mock_svc_call, mock_get_redis):
    producto_id = uuid4()
    mock_data = {
        "id": producto_id, "sku": "SKU123", "nombre": "Producto Test", "categoria": "A",
        "controlado": False, "stock_total": 150,
        "certificaciones": [], "lotes": []
    }
    mock_svc_call.return_value = mock_data
    response = client.get(f"/v1/inventario/producto/{producto_id}/detalle")
    assert response.status_code == 200
    assert response.json()['sku'] == "SKU123"
    mock_svc_call.assert_called_once()

@patch('src.routes.inventario.get_redis')
def test_producto_detalle_con_cache(mock_get_redis):
    producto_id = uuid4()
    mock_json_data = f'{{"id": "{producto_id}", "sku": "SKU-CACHE", "nombre": "Producto Cacheado", "categoria": "A", "controlado": false, "stock_total": 120, "certificaciones": [], "lotes": []}}'
    mock_redis_instance = MagicMock()
    mock_redis_instance.get.return_value = mock_json_data.encode('utf-8')
    mock_get_redis.return_value = mock_redis_instance

    with patch('src.routes.inventario.svc.producto_detalle') as mock_svc_call:
        response = client.get(f"/v1/inventario/producto/{producto_id}/detalle")
        assert response.status_code == 200
        assert response.json()['nombre'] == "Producto Cacheado"
        mock_svc_call.assert_not_called()

@patch('src.routes.inventario.svc.list_productos')
def test_productos_todos(mock_svc_call):
    mock_prod_1 = MagicMock()
    mock_prod_1.id=uuid4(); mock_prod_1.sku="SKU1"; mock_prod_1.nombre="Prod 1"; mock_prod_1.categoria="A"; mock_prod_1.controlado=False
    mock_prod_2 = MagicMock()
    mock_prod_2.id=uuid4(); mock_prod_2.sku="SKU2"; mock_prod_2.nombre="Prod 2"; mock_prod_2.categoria="B"; mock_prod_2.controlado=True
    
    mock_svc_call.return_value = [mock_prod_1, mock_prod_2]
    response = client.get("/v1/inventario/productos/todos?limit=10&offset=0")
    assert response.status_code == 200
    assert len(response.json()) == 2
    assert response.json()[0]["sku"] == "SKU1"

# El resto de los tests que ya pasaban se pueden mantener aquí...
@patch('src.routes.inventario.svc.ubicaciones_con_stock_por_producto')
def test_ubicaciones_con_stock_producto_no_existente(mock_svc_call):
    producto_id = uuid4()
    mock_svc_call.return_value = []
    response = client.get(f"/v1/inventario/producto/{producto_id}/ubicaciones")
    assert response.status_code == 200
    assert response.json() == []

@patch('src.routes.inventario.get_redis', return_value=None)
@patch('src.routes.inventario.svc.producto_detalle')
def test_producto_detalle_no_existente(mock_svc_call, mock_get_redis):
    producto_id = uuid4()
    mock_svc_call.side_effect = ValueError("Producto no existe")
    response = client.get(f"/v1/inventario/producto/{producto_id}/detalle")
    assert response.status_code == 404
    assert response.json() == {"detail": "Producto no existe"}
