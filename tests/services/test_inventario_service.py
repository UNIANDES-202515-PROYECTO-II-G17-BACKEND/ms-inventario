
import pytest
from uuid import uuid4
from datetime import date, timedelta
from src.services import inventario_service as svc
from src.domain.models import (
    Producto, Bodega, Ubicacion, Lote, Inventario, 
    CertificacionTipoEnum, PaisEnum, InventarioEstadoEnum
)

# Helper para crear datos de prueba complejos
@pytest.fixture
def setup_data(session):
    p1 = svc.crear_producto(session, sku="P1", nombre="Producto A", categoria="C1", temp_min=0, temp_max=0, controlado=False)
    p2 = svc.crear_producto(session, sku="P2", nombre="Producto B", categoria="C2", temp_min=0, temp_max=0, controlado=True)
    
    b1 = svc.crear_bodega(session, direccion="B1", ciudad="Bogota", pais=PaisEnum.CO)
    u1 = svc.crear_ubicacion(session, bodega_id=b1.id, pasillo="A", estante="1", posicion="1")
    u2 = svc.crear_ubicacion(session, bodega_id=b1.id, pasillo="A", estante="1", posicion="2")
    
    # Lotes para P1
    l1_p1 = svc.crear_lote(session, producto_id=p1.id, codigo="L1-P1", vencimiento=date.today() + timedelta(days=10))
    l2_p1 = svc.crear_lote(session, producto_id=p1.id, codigo="L2-P1", vencimiento=date.today() + timedelta(days=5)) # Vence antes
    
    # Inventario para P1
    svc.recibir_entrada(session, lote_id=l1_p1.id, ubicacion_id=u1.id, cantidad=100)
    svc.recibir_entrada(session, lote_id=l2_p1.id, ubicacion_id=u1.id, cantidad=50)
    svc.recibir_entrada(session, lote_id=l1_p1.id, ubicacion_id=u2.id, cantidad=25)
    # Inventario bloqueado para P1 (no debe contarse en stock disponible)
    svc.recibir_entrada(session, lote_id=l1_p1.id, ubicacion_id=u1.id, cantidad=10, estado=InventarioEstadoEnum.BLOQUEADO)

    return p1, p2, b1, u1, u2, l1_p1, l2_p1

# (Se mantienen los tests anteriores de create, associate, recibir_entrada, salida_por_fefo)

# ---------- Consultas de Stock ----------
def test_stock_por_producto(session, setup_data):
    """Prueba que el stock total se calcula correctamente, ignorando estados no disponibles."""
    p1, p2, *_ = setup_data
    # Stock de P1 = 100 (l1,u1) + 50 (l2,u1) + 25 (l1,u2) = 175. El bloqueado no cuenta.
    assert svc.stock_por_producto(session, p1.id) == 175
    # P2 no tiene stock
    assert svc.stock_por_producto(session, p2.id) == 0

def test_stock_detallado(session, setup_data):
    """Prueba que el detalle de stock se agrupa y suma correctamente."""
    p1, *_ = setup_data
    detalle = svc.stock_detallado(session, p1.id)
    
    # Esperamos 3 grupos: (l1,u1), (l2,u1), (l1,u2). El bloqueado se suma al disponible del mismo lote/ubicacion.
    assert len(detalle) == 3
    # Verificamos una de las entradas para asegurar que los datos son correctos
    item_l1_u1 = next((item for item in detalle if item['codigo'] == 'L1-P1' and item['ubicacion_id'] == setup_data[3].id), None)
    assert item_l1_u1 is not None
    assert item_l1_u1['cantidad'] == 110 # 100 disponibles + 10 bloqueados

# ---------- Consultas de Producto ----------
def test_producto_detalle(session, setup_data):
    """Prueba que el detalle completo de un producto es correcto."""
    p1, _, _, u1, u2, l1_p1, l2_p1 = setup_data
    svc.asociar_certificacion(session, producto_id=p1.id, autoridad="TestAuth", tipo=CertificacionTipoEnum.FDA, vigencia=date.today())

    detalle = svc.producto_detalle(session, p1.id)

    assert detalle['id'] == p1.id
    assert detalle['sku'] == "P1"
    assert detalle['stock_total'] == 185 # 175 disponibles + 10 bloqueados
    assert len(detalle['certificaciones']) == 1
    assert detalle['certificaciones'][0]['autoridad'] == "TestAuth"
    assert len(detalle['lotes']) == 2
    
    lote_detalle = next(l for l in detalle['lotes'] if l['codigo'] == 'L1-P1')
    assert lote_detalle['cantidad_total'] == 135 # 100 + 25 + 10

def test_producto_detalle_no_encontrado(session):
    """Prueba que se lanza un error si el producto no se encuentra."""
    with pytest.raises(ValueError, match="Producto no encontrado"):
        svc.producto_detalle(session, uuid4())

def test_ubicaciones_con_stock_por_producto(session, setup_data):
    """Prueba que se listan las ubicaciones correctas con su stock."""
    p1, *_ = setup_data
    u1, u2 = setup_data[3], setup_data[4]

    ubicaciones = svc.ubicaciones_con_stock_por_producto(session, p1.id)

    assert len(ubicaciones) == 2
    # Ubicacion 1 tiene stock de l1 (100+10) y l2 (50) = 160
    ubicacion1_info = next(u for u in ubicaciones if u['ubicacion_id'] == u1.id)
    assert ubicacion1_info['cantidad'] == 160
    # Ubicacion 2 tiene stock de l1 (25)
    ubicacion2_info = next(u for u in ubicaciones if u['ubicacion_id'] == u2.id)
    assert ubicacion2_info['cantidad'] == 25

def test_list_productos(session, setup_data):
    """Prueba el listado de productos con y sin filtros."""
    p1, p2, *_ = setup_data
    
    # Listar todos
    todos = svc.list_productos(session)
    assert len(todos) == 2
    assert todos[0].nombre == "Producto A" # Ordenado por nombre ASC

    # Con límite
    limitados = svc.list_productos(session, limit=1)
    assert len(limitados) == 1

    # Con offset
    offseteados = svc.list_productos(session, limit=1, offset=1)
    assert len(offseteados) == 1
    assert offseteados[0].nombre == "Producto B"

    # Por IDs
    por_ids = svc.list_productos(session, ids=[p2.id])
    assert len(por_ids) == 1
    assert por_ids[0].id == p2.id

# (Aquí irían los tests de las funciones que ya estaban, como crear_producto, etc.)
# Para brevedad, no los repito, pero deben estar en el archivo.
