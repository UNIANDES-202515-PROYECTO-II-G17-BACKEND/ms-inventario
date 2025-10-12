from __future__ import annotations
from typing import Optional, List, Tuple
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from src.domain.models import (
    Producto, Lote, Inventario, Ubicacion, Bodega, CertificacionSanitaria,
    CertificacionTipoEnum, InventarioEstadoEnum
)

# ---------- Producto ----------
def crear_producto(session: Session, *, sku: str, nombre: str,
                   categoria: Optional[str], temp_min: Optional[float],
                   temp_max: Optional[float], controlado: bool) -> Producto:
    p = Producto(
        sku=sku,
        nombre=nombre,
        categoria=categoria,
        temp_min=temp_min,
        temp_max=temp_max,
        controlado=controlado,
    )
    session.add(p)
    try:
        session.commit()
    except IntegrityError as e:
        session.rollback()
        # sku es único
        raise ValueError("SKU ya existe") from e
    session.refresh(p)
    return p

def asociar_certificacion(session: Session, *, producto_id: str, autoridad: str,
                          tipo: CertificacionTipoEnum, vigencia) -> CertificacionSanitaria:
    prod = session.get(Producto, producto_id)
    if not prod:
        raise ValueError("Producto no existe")
    cert = CertificacionSanitaria(autoridad=autoridad, tipo=tipo, vigencia=vigencia)
    prod.certificaciones.append(cert)
    session.commit()
    session.refresh(cert)
    return cert

# ---------- Bodega / Ubicación ----------
def crear_bodega(session: Session, *, direccion: str, ciudad: str, pais) -> Bodega:
    b = Bodega(direccion=direccion, ciudad=ciudad, pais=pais)
    session.add(b)
    try:
        session.commit()
    except IntegrityError as e:
        session.rollback()
        raise ValueError("La bodega ya existe") from e
    session.refresh(b)
    return b

def crear_ubicacion(session: Session, *, bodega_id: str, pasillo: str, estante: str, posicion: str) -> Ubicacion:
    u = Ubicacion(bodega_id=bodega_id, pasillo=pasillo, estante=estante, posicion=posicion)
    session.add(u)
    try:
        session.commit()
    except IntegrityError as e:
        session.rollback()
        # uq_ubicacion_slot: (bodega_id, pasillo, estante, posicion)
        raise ValueError("La ubicación ya existe en la bodega (pasillo/estante/posición)") from e
    session.refresh(u)
    return u

# ---------- Lote ----------
def crear_lote(session: Session, *, producto_id: str, codigo: str, vencimiento) -> Lote:
    prod = session.get(Producto, producto_id)
    if not prod:
        raise ValueError("Producto no existe")
    l = Lote(producto_id=producto_id, codigo=codigo, vencimiento=vencimiento)
    session.add(l)
    try:
        session.commit()
    except IntegrityError as e:
        session.rollback()
        # uq_lote_codigo_por_producto: (producto_id, codigo)
        raise ValueError("El código de lote ya existe para este producto") from e
    session.refresh(l)
    return l

# ---------- Inventario ----------
def recibir_entrada(session: Session, *, lote_id: str, ubicacion_id: str, cantidad: int,
                    estado: InventarioEstadoEnum = InventarioEstadoEnum.DISPONIBLE) -> Inventario:
    if cantidad <= 0:
        raise ValueError("Cantidad debe ser positiva")
    
    lote = session.get(Lote, lote_id)
    if not lote:
        raise ValueError("Lote no existe")

    ubicacion = session.get(Ubicacion, ubicacion_id)
    if not ubicacion:
        raise ValueError("Ubicación no existe")

    inv = session.scalar(select(Inventario).where(
        Inventario.lote_id == lote_id,
        Inventario.ubicacion_id == ubicacion_id,
        Inventario.estado == estado
    ))
    if inv:
        inv.cantidad += cantidad
    else:
        inv = Inventario(lote_id=lote_id, ubicacion_id=ubicacion_id,
                         cantidad=cantidad, estado=estado)
        session.add(inv)
    session.commit()
    session.refresh(inv)
    return inv

def salida_por_fefo(session: Session, *, producto_id: str, cantidad: int,
                    ubicacion_id: Optional[str] = None) -> List[Tuple[Inventario, int]]:
    if cantidad <= 0:
        raise ValueError("Cantidad debe ser positiva")

    q = (select(Inventario)
         .join(Inventario.lote)
         .where(Lote.producto_id == producto_id,
                Inventario.estado == InventarioEstadoEnum.DISPONIBLE))
    if ubicacion_id:
        q = q.where(Inventario.ubicacion_id == ubicacion_id)
    q = q.order_by(Lote.vencimiento.is_(None), Lote.vencimiento.asc(), Inventario.fecha_ingreso.asc())

    registros = list(session.scalars(q))
    restante = cantidad
    consumos: List[Tuple[Inventario,int]] = []

    for inv in registros:
        if restante == 0:
            break
        toma = min(inv.cantidad, restante)
        if toma <= 0:
            continue
        if inv.cantidad < toma:
            raise ValueError("Stock insuficiente en registro")
        inv.cantidad -= toma
        consumos.append((inv, toma))
        restante -= toma

    if restante > 0:
        raise ValueError("Stock insuficiente total")

    for inv, _ in consumos:
        if inv.cantidad == 0:
            session.delete(inv)
    session.commit()
    return consumos

def stock_por_producto(session: Session, producto_id: str) -> int:
    total = session.scalar(
        select(func.coalesce(func.sum(Inventario.cantidad), 0))
        .join(Inventario.lote)
        .where(Lote.producto_id == producto_id,
               Inventario.estado == InventarioEstadoEnum.DISPONIBLE)
    )
    return total or 0

def stock_detallado(session: Session, producto_id: str):
    q = (select(Lote.codigo, Lote.vencimiento, Ubicacion.id.label("ubicacion_id"),
                func.sum(Inventario.cantidad).label("cantidad"))
         .join(Inventario.lote)
         .join(Inventario.ubicacion)
         .where(Lote.producto_id == producto_id)
         .group_by(Lote.codigo, Lote.vencimiento, Ubicacion.id)
         .order_by(Lote.vencimiento))
    rows = session.execute(q)
    return [dict(r._mapping) for r in rows.all()]