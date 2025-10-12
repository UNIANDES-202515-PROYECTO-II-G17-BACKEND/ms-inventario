# src/domain/schemas.py
from __future__ import annotations
from datetime import date, datetime
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel, Field
from src.domain.models import CertificacionTipoEnum, InventarioEstadoEnum, PaisEnum

class OrmModel(BaseModel):
    model_config = {"from_attributes": True}

# -------- Producto --------
class ProductoCreate(BaseModel):
    sku: str
    nombre: str
    categoria: Optional[str] = None
    temp_min: Optional[float] = None
    temp_max: Optional[float] = None
    controlado: bool = False

class ProductoOut(OrmModel):
    id: UUID
    sku: str
    nombre: str
    categoria: Optional[str]
    controlado: bool

# -------- Certificación --------
class CertificacionCreate(BaseModel):
    autoridad: str
    tipo: CertificacionTipoEnum
    vigencia: date

class CertificacionOut(OrmModel):
    id: UUID
    autoridad: str
    tipo: CertificacionTipoEnum
    vigencia: date

# -------- Bodega / Ubicación --------
class BodegaCreate(BaseModel):
    direccion: str
    ciudad: str
    pais: PaisEnum

class BodegaOut(OrmModel):
    id: UUID
    direccion: str
    ciudad: str
    pais: PaisEnum

class UbicacionCreate(BaseModel):
    bodega_id: UUID
    pasillo: str
    estante: str
    posicion: str

class UbicacionOut(OrmModel):
    id: UUID
    bodega_id: UUID
    pasillo: str
    estante: str
    posicion: str

# -------- Lote --------
class LoteCreate(BaseModel):
    producto_id: UUID
    codigo: str
    vencimiento: Optional[date] = None

class LoteOut(OrmModel):
    id: UUID
    producto_id: UUID
    codigo: str
    vencimiento: Optional[date]

# -------- Inventario --------
class EntradaCreate(BaseModel):
    lote_id: UUID
    ubicacion_id: UUID
    cantidad: int
    estado: InventarioEstadoEnum = InventarioEstadoEnum.DISPONIBLE

class FEFOOut(BaseModel):
    inventario_id: UUID
    consumido: int

class InventarioOut(OrmModel):
    id: UUID
    lote_id: UUID
    ubicacion_id: UUID
    cantidad: int
    fecha_ingreso: datetime
    estado: InventarioEstadoEnum

class StockDetalladoItem(BaseModel):
    codigo: str
    vencimiento: Optional[date]
    ubicacion_id: UUID
    cantidad: int
