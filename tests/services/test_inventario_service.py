
import pytest
from uuid import uuid4
from datetime import date, timedelta
from src.services import inventario_service as svc
from src.domain.models import (
    Producto, Bodega, Ubicacion, Lote, Inventario, 
    CertificacionTipoEnum, PaisEnum, InventarioEstadoEnum
)

# --- Fixtures de Datos --- 

@pytest.fixture
def setup_productos(session):
    p1 = svc.crear_producto(session, sku="P1", nombre="Producto A", categoria="C1", temp_min=0, temp_max=0, controlado=False)
    p2 = svc.crear_producto(session, sku="P2", nombre="Producto B", categoria="C2", temp_min=0, temp_max=0, controlado=True)
    return p1, p2

@pytest.fixture
def setup_infra(session):
    b1 = svc.crear_bodega(session, direccion="B1", ciudad="Bogota", pais=PaisEnum.CO)
    u1 = svc.crear_ubicacion(session, bodega_id=b1.id, pasillo="A", estante="1", posicion="1")
    u2 = svc.crear_ubicacion(session, bodega_id=b1.id, pasillo="A", estante="1", posicion="2")
    return b1, u1, u2

@pytest.fixture
def setup_completo(session, setup_productos, setup_infra):
    p1, p2 = setup_productos
    b1, u1, u2 = setup_infra
    
    l1_p1 = svc.crear_lote(session, producto_id=p1.id, codigo="L1-P1", vencimiento=date.today() + timedelta(days=10))
    l2_p1 = svc.crear_lote(session, producto_id=p1.id, codigo="L2-P1", vencimiento=date.today() + timedelta(days=5))
    l3_p1_nv = svc.crear_lote(session, producto_id=p1.id, codigo="L3-P1-NV", vencimiento=None)

    svc.recibir_entrada(session, lote_id=l1_p1.id, ubicacion_id=u1.id, cantidad=100)
    svc.recibir_entrada(session, lote_id=l2_p1.id, ubicacion_id=u1.id, cantidad=50)
    svc.recibir_entrada(session, lote_id=l3_p1_nv.id, ubicacion_id=u2.id, cantidad=200)

    return p1, p2, b1, u1, u2, l1_p1, l2_p1, l3_p1_nv

# --- Tests --- 

def test_crear_producto_exitoso(session):
    producto = svc.crear_producto(session, sku="SKU123", nombre="Producto Test", categoria="A", temp_min=10.0, temp_max=20.0, controlado=False)
    assert producto.id is not None

def test_crear_producto_sku_duplicado(session, setup_productos):
    with pytest.raises(ValueError, match="SKU ya existe"):
        svc.crear_producto(session, sku="P1", nombre="Otro", categoria="O", temp_min=0, temp_max=0, controlado=False)

def test_asociar_certificacion_exitosa(session, setup_productos):
    p1, _ = setup_productos
    cert = svc.asociar_certificacion(session, producto_id=p1.id, autoridad="INVIMA", tipo=CertificacionTipoEnum.INVIMA, vigencia=date(2025, 1, 1))
    session.refresh(p1)
    assert len(p1.certificaciones) == 1

def test_crear_bodega_duplicada(session, setup_infra):
    with pytest.raises(ValueError, match="La bodega ya existe"):
        svc.crear_bodega(session, direccion="B1", ciudad="Bogota", pais=PaisEnum.CO)

def test_crear_ubicacion_duplicada(session, setup_infra):
    b1, _, _ = setup_infra
    with pytest.raises(ValueError, match="La ubicación ya existe"):
        svc.crear_ubicacion(session, bodega_id=b1.id, pasillo="A", estante="1", posicion="1")

def test_crear_lote_producto_no_existe(session):
    with pytest.raises(ValueError, match="Producto no existe"):
        svc.crear_lote(session, producto_id=uuid4(), codigo="LOTE001", vencimiento=date(2025, 1, 1))

def test_crear_lote_codigo_duplicado(session, setup_productos):
    p1, _ = setup_productos
    svc.crear_lote(session, producto_id=p1.id, codigo="LOTE001", vencimiento=date(2025, 1, 1))
    with pytest.raises(ValueError, match="El código de lote ya existe"):
        svc.crear_lote(session, producto_id=p1.id, codigo="LOTE001", vencimiento=date(2026, 1, 1))

def test_recibir_entrada_nueva(session, setup_completo):
    p1, _, _, u2, _, l2_p1, _, _ = setup_completo
    inv = svc.recibir_entrada(session, lote_id=l2_p1.id, ubicacion_id=u2.id, cantidad=100)
    assert inv.cantidad == 200

def test_recibir_entrada_existente(session, setup_completo):
    _, _, _, u1, _, _, l2_p1, _ = setup_completo
    inv = svc.recibir_entrada(session, lote_id=l2_p1.id, ubicacion_id=u1.id, cantidad=30)
    assert inv.cantidad == 80 # 50 existentes + 30 nuevos

def test_recibir_entrada_cantidad_negativa(session, setup_completo):
    _, _, _, u1, _, l1_p1, _, _ = setup_completo
    with pytest.raises(ValueError, match="Cantidad debe ser positiva"):
        svc.recibir_entrada(session, lote_id=l1_p1.id, ubicacion_id=u1.id, cantidad=0)

def test_salida_fefo_lote_sin_vencimiento(session, setup_completo):
    p1, _, _, _, _, l1_p1, l2_p1, l3_p1_nv = setup_completo
    consumos = svc.salida_por_fefo(session, producto_id=p1.id, cantidad=150)
    assert len(consumos) == 2
    assert consumos[0][0].lote_id == l2_p1.id and consumos[0][1] == 50
    assert consumos[1][0].lote_id == l1_p1.id and consumos[1][1] == 100
    
    consumos_2 = svc.salida_por_fefo(session, producto_id=p1.id, cantidad=75)
    assert len(consumos_2) == 1
    assert consumos_2[0][0].lote_id == l3_p1_nv.id

def test_producto_detalle_sin_lotes_ni_certificaciones(session, setup_productos):
    _, p2 = setup_productos
    detalle = svc.producto_detalle(session, p2.id)
    assert detalle["stock_total"] == 0 and not detalle["certificaciones"] and not detalle["lotes"]

def test_list_productos_con_filtro_ids(session, setup_productos):
    p1, p2 = setup_productos
    productos = svc.list_productos(session, ids=[p2.id])
    assert len(productos) == 1 and productos[0].id == p2.id

def test_recibir_entrada_estado_diferente(session, setup_completo):
    _, _, _, u1, _, l1_p1, _, _ = setup_completo
    inv2 = svc.recibir_entrada(session, lote_id=l1_p1.id, ubicacion_id=u1.id, cantidad=20, estado=InventarioEstadoEnum.BLOQUEADO)
    assert inv2.cantidad == 20
    assert session.query(Inventario).filter_by(lote_id=l1_p1.id, ubicacion_id=u1.id).count() == 2

def test_stock_por_producto(session, setup_completo):
    p1, p2, *_ = setup_completo
    assert svc.stock_por_producto(session, p1.id) == 350
    assert svc.stock_por_producto(session, p2.id) == 0

def test_stock_detallado(session, setup_completo):
    p1, *_ = setup_completo
    detalle = svc.stock_detallado(session, p1.id)
    assert len(detalle) == 3

def test_producto_detalle(session, setup_completo):
    p1, *_ = setup_completo
    svc.asociar_certificacion(session, producto_id=p1.id, autoridad="TestAuth", tipo=CertificacionTipoEnum.FDA, vigencia=date.today())
    detalle = svc.producto_detalle(session, p1.id)
    assert detalle["stock_total"] == 350
    assert len(detalle["certificaciones"]) == 1
    assert len(detalle["lotes"]) == 3

def test_ubicaciones_con_stock_por_producto(session, setup_completo):
    p1, *_ = setup_completo
    ubicaciones = svc.ubicaciones_con_stock_por_producto(session, p1.id)
    assert len(ubicaciones) == 2
