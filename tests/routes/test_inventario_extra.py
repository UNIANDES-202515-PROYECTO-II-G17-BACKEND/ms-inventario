import json
from uuid import uuid4
from unittest.mock import patch, MagicMock

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