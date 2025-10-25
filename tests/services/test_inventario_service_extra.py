import pytest
from uuid import uuid4
from unittest.mock import patch, MagicMock
from datetime import date
from src.services import inventario_service as svc


# ---------- _to_bool inválido (acumula error en CSV) ----------
def test_csv_bool_invalido_genera_error(session):
    csv_bytes = (
        b"sku,nombre,categoria,temp_min,temp_max,controlado,precio,moneda,lead_time_dias,lote_minimo,activo\n"
        b"SKU-1,Prod 1,Cat,0,1,quiza,10,COP,1,1,true\n"  # 'quiza' es inválido
    )
    with patch("src.services.inventario_service.MsClient") as MockC:
        MockC.return_value = MagicMock()
        res = svc.procesar_csv_productos(session, "co", uuid4(), csv_bytes)
    assert res["total"] == 1
    assert res["insertados"] == 0
    assert len(res["errores"]) == 1


# ---------- headers faltantes (400) ----------
def test_csv_headers_faltantes_400(session):
    csv_bytes = b"sku,nombre,categoria\nSKU-1,Prod,Cat\n"
    with pytest.raises(Exception) as exc:
        svc.procesar_csv_productos(session, "co", uuid4(), csv_bytes)
    assert "Faltan columnas" in str(exc.value)


# ---------- idempotencia por SKU (crear o recuperar) ----------
def test_crear_o_recuperar_producto_idempotente(session):
    core = {
        "sku": "IDEMP",
        "nombre": "P",
        "categoria": "C",
        "temp_min": 0,
        "temp_max": 0,
        "controlado": False,
    }
    p1 = svc.crear_o_recuperar_producto(session, core)
    p2 = svc.crear_o_recuperar_producto(session, core)
    assert p1.id == p2.id  # misma entidad por SKU


# ---------- FEFO errores: cantidad <=0 y stock insuficiente ----------
def test_fefo_cantidad_invalida_y_stock_insuficiente(session):
    # crea producto sin inventario
    p = svc.crear_producto(
        session,
        sku="SINSTOCK",
        nombre="S",
        categoria="C",
        temp_min=0,
        temp_max=0,
        controlado=False,
    )
    # cantidad <= 0
    with pytest.raises(ValueError, match="Cantidad debe ser positiva"):
        svc.salida_por_fefo(session, producto_id=p.id, cantidad=0)
    # stock insuficiente
    with pytest.raises(ValueError, match="Stock insuficiente total"):
        svc.salida_por_fefo(session, producto_id=p.id, cantidad=10)


# ---------- entrada errores: lote/ubicación no existe ----------
def test_recibir_entrada_lote_ubicacion_inexistentes(session):
    with pytest.raises(ValueError, match="Lote no existe"):
        svc.recibir_entrada(session, lote_id=uuid4(), ubicacion_id=uuid4(), cantidad=1)


# ---------- crear_lote: duplicado y producto inexistente ----------
def test_crear_lote_duplicado_y_no_existe(session):
    from datetime import timedelta

    p = svc.crear_producto(
        session, sku="SKU-L", nombre="PL", categoria="C", temp_min=0, temp_max=0, controlado=False
    )
    l1 = svc.crear_lote(session, producto_id=p.id, codigo="L-1", vencimiento=date.today() + timedelta(days=10))
    assert l1.id  # creado

    with pytest.raises(ValueError, match="El código de lote ya existe"):
        svc.crear_lote(session, producto_id=p.id, codigo="L-1", vencimiento=date.today())

    with pytest.raises(ValueError, match="Producto no existe"):
        svc.crear_lote(session, producto_id=uuid4(), codigo="L-X", vencimiento=None)
