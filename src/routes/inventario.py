from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from uuid import UUID
from src.dependencies import get_session
from src.services import inventario_service as svc
from src.domain.schemas import (
    ProductoCreate, ProductoOut, CertificacionCreate, CertificacionOut,
    BodegaCreate, BodegaOut, UbicacionCreate, UbicacionOut,
    LoteCreate, LoteOut, EntradaCreate, FEFOOut, InventarioOut, StockDetalladoItem
)

router = APIRouter(prefix="/v1/inventario", tags=["Inventario"])

# ---------- PRODUCTO ----------
@router.post("/producto", response_model=ProductoOut)
def crear_producto(payload: ProductoCreate, session: Session = Depends(get_session)):
    try:
        p = svc.crear_producto(
            session,
            sku=payload.sku,
            nombre=payload.nombre,
            categoria=payload.categoria,
            temp_min=payload.temp_min,
            temp_max=payload.temp_max,
            controlado=payload.controlado,
        )
        return p
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

@router.post("/producto/{producto_id}/certificacion", response_model=CertificacionOut)
def agregar_certificacion(producto_id: str, payload: CertificacionCreate, session: Session = Depends(get_session)):
    try:
        return svc.asociar_certificacion(
            session,
            producto_id=producto_id,
            autoridad=payload.autoridad,
            tipo=payload.tipo,
            vigencia=payload.vigencia,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

# ---------- BODEGA / UBICACION ----------
@router.post("/bodega", response_model=BodegaOut)
def crear_bodega(payload: BodegaCreate, session: Session = Depends(get_session)):
    try:
        return svc.crear_bodega(session, direccion=payload.direccion, ciudad=payload.ciudad, pais=payload.pais)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/ubicacion", response_model=UbicacionOut)
def crear_ubicacion(payload: UbicacionCreate, session: Session = Depends(get_session)):
    try:
        return svc.crear_ubicacion(session, bodega_id=payload.bodega_id, pasillo=payload.pasillo,
                               estante=payload.estante, posicion=payload.posicion)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
# ---------- LOTE ----------
@router.post("/lote", response_model=LoteOut)
def crear_lote(payload: LoteCreate, session: Session = Depends(get_session)):
    try:
        return svc.crear_lote(session, producto_id=payload.producto_id, codigo=payload.codigo, vencimiento=payload.vencimiento)
    except ValueError as e:
        if "Producto no existe" in str(e):
            raise HTTPException(status_code=404, detail=str(e))
        else:
            raise HTTPException(status_code=409, detail=str(e))

# ---------- INVENTARIO ----------
@router.post("/entrada", response_model=InventarioOut)
def entrada(payload: EntradaCreate, session: Session = Depends(get_session)):
    try:
        return svc.recibir_entrada(session, lote_id=payload.lote_id, ubicacion_id=payload.ubicacion_id,
                                   cantidad=payload.cantidad, estado=payload.estado)
    except ValueError as e:
        if "Lote no existe" in str(e) or "Ubicación no existe" in str(e):
            raise HTTPException(status_code=404, detail=str(e))
        else:
            raise HTTPException(status_code=400, detail=str(e))

@router.post("/salida/fefo", response_model=List[FEFOOut])
def salida_fefo(producto_id: str, cantidad: int, ubicacion_id: Optional[str] = None,
                session: Session = Depends(get_session)):
    try:
        consumos = svc.salida_por_fefo(session, producto_id=producto_id, cantidad=cantidad, ubicacion_id=ubicacion_id)
        return [{"inventario_id": inv.id, "consumido": qty} for inv, qty in consumos]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

# ---------- CONSULTAS ----------
@router.get("/stock/{producto_id}")
def stock(producto_id: str, session: Session = Depends(get_session)):
    return {"producto_id": producto_id, "stock": svc.stock_por_producto(session, producto_id)}

@router.get("/stock/{producto_id}/detalle", response_model=List[StockDetalladoItem])
def stock_detalle(producto_id: str, session: Session = Depends(get_session)):
    return svc.stock_detallado(session, producto_id)
