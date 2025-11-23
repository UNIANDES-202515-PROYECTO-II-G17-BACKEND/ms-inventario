from unittest.mock import patch, MagicMock

from uuid import uuid4
import pytest
from src.services import inventario_service as svc
from src.domain.models import Inventario
from src.domain.models import InventarioEstadoEnum

from src.services.inventario_service import _to_bool, _to_float, _to_int
from src.services.inventario_service import _row_to_payload, _row_to_asociacion


# ---------- util ----------
def _mk_csv(lines):
    return ("\n".join(lines)).encode("utf-8")


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


# ---------- productos_todos: paginación (limit/offset) ----------

def test_productos_todos_paginacion(client):
    # Usa SKUs únicos para evitar 409 por colisión entre tests
    skus = [f"SKU-{i}-{uuid4().hex[:8]}" for i in range(3)]
    for i, sku in enumerate(skus):
        payload = {
            "sku": sku,
            "nombre": f"P{i}",
            "categoria": "C",
            "controlado": False,
            "temp_min": 0,
            "temp_max": 0,
        }
        r = client.post("/v1/inventario/producto", json=payload)
        # Acepta 200 (creado) o 409 (ya existe) para ser robusto si se re-ejecuta
        assert r.status_code in (200, 409), r.text

    # limit=2
    r1 = client.get("/v1/inventario/productos/todos?limit=2&offset=0")
    assert r1.status_code == 200
    assert len(r1.json()) == 2

    # offset=2
    r2 = client.get("/v1/inventario/productos/todos?limit=2&offset=2")
    assert r2.status_code == 200
    assert 0 <= len(r2.json()) <= 2


def test_producto_detalle_producto_inexistente(session):
    """
    Cubre:
        prod = session.get(Producto, producto_id)
        if not prod: raise ValueError("Producto no encontrado")
    """
    with pytest.raises(ValueError, match="Producto no encontrado"):
        svc.producto_detalle(session, uuid4())


def test_crear_o_recuperar_producto_reutiliza_existente(session):
    core = {
        "sku": "SKU-EXISTE",
        "nombre": "Producto X",
        "categoria": "CAT",
        "temp_min": 0,
        "temp_max": 10,
        "controlado": False,
    }
    p1 = svc.crear_producto(
        session,
        sku=core["sku"],
        nombre=core["nombre"],
        categoria=core["categoria"],
        temp_min=core["temp_min"],
        temp_max=core["temp_max"],
        controlado=core["controlado"],
    )

    p2 = svc.crear_o_recuperar_producto(session, core)
    assert p2.id == p1.id  # misma fila → rama 'existente' cubierta


def test_to_bool_varios_casos():
    assert _to_bool(None) is None            # rama val is None
    assert _to_bool("Sí") is True            # en _TRUE
    assert _to_bool("no") is False           # en _FALSE
    assert _to_bool("1") is True             # dígito → bool(int)
    assert _to_bool("0") is False

    with pytest.raises(ValueError, match="Valor booleano inválido"):
        _to_bool("quizas")                   # rama de error


def test_to_float_y_to_int():
    assert _to_float(None) is None
    assert _to_float("") is None
    assert _to_float("1,5") == 1.5           # reemplaza coma

    assert _to_int(None) is None
    assert _to_int("") is None
    assert _to_int(" 42 ") == 42

def test_row_to_payload_ok_y_obligatorios(session):
    row = {
        "sku": " SKU-1 ",
        "nombre": " Prod 1 ",
        "categoria": " Cat ",
        "temp_min": "1,5",
        "temp_max": "10",
        "controlado": "true",
        "precio": "100",
        "moneda": " COP ",
        "lead_time_dias": " 7 ",
        "lote_minimo": " 10 ",
        "activo": "1",
    }
    payload = _row_to_payload(row)
    assert payload["sku"] == "SKU-1"
    assert payload["nombre"] == "Prod 1"
    assert payload["categoria"] == "Cat"
    assert payload["temp_min"] == 1.5
    assert payload["lead_time_dias"] == 7
    assert payload["activo"] is True

    # ahora forzamos los campos obligatorios vacíos
    row_bad = {
        "sku": "",
        "nombre": "  ",
        "categoria": "",
    }
    with pytest.raises(ValueError, match="Campos obligatorios vacíos"):
        _row_to_payload(row_bad)


def test_row_to_asociacion_campos_requeridos_y_activo_por_defecto():
    producto_id = uuid4()
    row = {
        "sku": " COD-1 ",
        "precio": " 10,0 ",
        "moneda": " COP ",
        "lead_time_dias": " 5 ",
        "lote_minimo": " 1 ",
        # OJO: NO hay clave "activo" → row.get("activo") -> None → _to_bool(None) -> None → default False
    }

    assoc = _row_to_asociacion(row, producto_id)

    assert assoc.producto_id == producto_id
    assert assoc.sku_proveedor == "COD-1"
    assert assoc.precio == 10.0
    assert assoc.moneda == "COP"
    assert assoc.lead_time_dias == 5
    assert assoc.lote_minimo == 1
    assert assoc.activo is False

    # Caso error por campo requerido vacío
    row_bad = {
        "sku": "   ",            # vacío después de strip
        "precio": "10",
        "moneda": "COP",
        "lead_time_dias": "1",
        "lote_minimo": "1",
    }
    with pytest.raises(ValueError, match="Campo requerido vacío en asociación: sku"):
        _row_to_asociacion(row_bad, producto_id)