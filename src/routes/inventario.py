import logging
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, Header, UploadFile, File, Request
from sqlalchemy.orm import Session
from uuid import UUID
import json
from src.dependencies import get_session
from src.services import inventario_service as svc
from src.config import settings
from src.infrastructure.infrastructure import get_redis
from src.domain.schemas import (
    ProductoCreate, ProductoOut, CertificacionCreate, CertificacionOut,
    BodegaCreate, BodegaOut, UbicacionCreate, UbicacionOut,
    LoteCreate, LoteOut, EntradaCreate, FEFOOut, InventarioOut, StockDetalladoItem,
    ProductoDetalleOut, UbicacionStockOut
)
from typing import List, Dict, Any, Optional
import csv
import io
import codecs

log = logging.getLogger(__name__)
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


# ---------- CARGA MASIVA POR CSV ----------
@router.post("/productos/upload-csv")
async def upload_csv_productos(
            request: Request,
            session: Session = Depends(get_session),
            file: Optional[UploadFile] = File(default=None, description="Archivo CSV con productos"),
    ):
        # 1) multipart/form-data (UploadFile)
        if file is not None:
                if not file.filename.lower().endswith(".csv"):
                    raise HTTPException(status_code=400, detail="El archivo debe ser .csv")
                try:
                    # decodificación por streaming, soporta UTF-8 con BOM
                    text_stream = io.TextIOWrapper(file.file, encoding="utf-8-sig", newline="")
                    reader = svc._iter_dict_reader(text_stream)
                    svc._validate_headers(reader)
                    inserted, errors = svc._process_rows(reader, session, UUID(request.headers.get("proveedor_id")), request.headers.get("X-Country"))
                finally:
                    await file.close()
                return {
                    "total": inserted + len(errors),
                    "insertados": inserted,
                    "errores": errors
                }
        raise HTTPException(
            status_code=415,
            detail="Contenido no soportado. Usa multipart/form-data con campo 'file' o text/csv en el body."
        )

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

@router.get("/producto/{producto_id}/detalle", response_model=ProductoDetalleOut)
def producto_detalle(
    producto_id: UUID,
    session: Session = Depends(get_session),
    country: str | None = Header(default=None, alias=settings.COUNTRY_HEADER),
):
    redis = get_redis()
    country_key = (country or settings.DEFAULT_SCHEMA).strip().lower()
    cache_key = f"{country_key}-{producto_id}"

    # 1) Intento de caché seguro
    if redis:
        cached = redis.get(cache_key)
        if cached:
            try:
                model = ProductoDetalleOut.model_validate_json(cached)
                return model
            except Exception as e:
                # Cache corrupto: lo ignoramos y seguimos a DB
                log.warning("Cache inválido para %s: %s", cache_key, e)

    # 2) DB
    try:
        data_dict = svc.producto_detalle(session, producto_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    model = ProductoDetalleOut(**data_dict)

    if redis:
        try:
            redis.set(cache_key, model.model_dump_json(), ex=300)
        except Exception as e:
            log.warning("No se pudo escribir en Redis %s: %s", cache_key, e)

    return model

@router.get("/producto/{producto_id}/ubicaciones", response_model=List[UbicacionStockOut])
def ubicaciones_con_stock(producto_id: UUID,session: Session = Depends(get_session)):
    return svc.ubicaciones_con_stock_por_producto(session, producto_id)


@router.get("/productos/todos", response_model=List[ProductoOut])
def productos_todos(
    limit: Optional[int] = Query(default=None, ge=1, le=1000, description="Máximo de filas a devolver"),
    offset: int = Query(default=0, ge=0, description="Desplazamiento para paginación"),
    session: Session = Depends(get_session),
):
    return svc.list_productos(session, ids=None, limit=limit, offset=offset)



