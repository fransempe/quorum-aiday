"""Entidades del estado compartido del proyecto."""

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, computed_field, field_validator

EstadoCompromiso = Literal["pendiente", "cumplido", "vencido", "cancelado"]
EstadoRiesgo = Literal["abierto", "mitigado", "cerrado"]
TipoReporte = Literal["semanal", "ejecutivo", "alerta"]
TipoEvento = Literal[
    "compromiso.creado",
    "compromiso.actualizado",
    "compromiso.vencido",
    "riesgo.creado",
    "riesgo.actualizado",
    "reporte.generado",
]


def ahora() -> datetime:
    return datetime.now().replace(microsecond=0)


class Compromiso(BaseModel):
    id: str
    descripcion: str = Field(min_length=5)
    responsable: str  # "" = sin responsable (no se inventa)
    fecha_limite: date | None = None
    estado: EstadoCompromiso = "pendiente"
    origen: str  # id de la minuta o "manual"
    creado_en: datetime = Field(default_factory=ahora)

    @field_validator("descripcion", "responsable", "origen", mode="before")
    @classmethod
    def _recortar(cls, v: Any) -> Any:
        return v.strip() if isinstance(v, str) else v

    @field_validator("fecha_limite", mode="before")
    @classmethod
    def _fecha_vacia(cls, v: Any) -> Any:
        return None if v == "" else v


class Riesgo(BaseModel):
    id: str
    titulo: str = Field(min_length=3)
    descripcion: str
    probabilidad: int = Field(ge=1, le=5)
    impacto: int = Field(ge=1, le=5)
    mitigacion: str
    compromisos_relacionados: list[str] = Field(default_factory=list)
    estado: EstadoRiesgo = "abierto"

    @field_validator("titulo", "descripcion", "mitigacion", mode="before")
    @classmethod
    def _recortar(cls, v: Any) -> Any:
        return v.strip() if isinstance(v, str) else v

    @computed_field
    @property
    def severidad(self) -> int:
        return self.probabilidad * self.impacto


class Evento(BaseModel):
    id: str
    tipo: TipoEvento
    payload: dict[str, Any]
    agente: str
    creado_en: datetime = Field(default_factory=ahora)


class Reporte(BaseModel):
    id: str
    tipo: TipoReporte
    periodo: str = Field(min_length=1)
    contenido: str = Field(min_length=1)  # markdown
    creado_en: datetime = Field(default_factory=ahora)
