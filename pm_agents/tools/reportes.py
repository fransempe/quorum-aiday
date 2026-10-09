"""Tools de reportes y bitácora de eventos."""

from datetime import date, datetime, time
from typing import Literal

from strands import tool

from pm_agents.store import get_store
from pm_agents.tools._comun import ejecutar

AGENTE = "reportes"


@tool
def listar_eventos(tipo: str | None = None, desde: str | None = None, limite: int = 30) -> str:
    """Lista la bitácora de cambios, más recientes primero.

    Args:
        tipo: por ejemplo compromiso.creado, compromiso.vencido o riesgo.actualizado. Opcional.
        desde: fecha AAAA-MM-DD; solo eventos desde ese día. Opcional.
        limite: cantidad máxima de eventos (por defecto 30).
    """

    def operacion():
        inicio = datetime.combine(date.fromisoformat(desde), time.min) if desde else None
        return get_store().listar_eventos(tipo=tipo, desde=inicio, limite=limite)

    return ejecutar(operacion)


@tool
def guardar_reporte(tipo: Literal["semanal", "ejecutivo", "alerta"], periodo: str, contenido: str) -> str:
    """Guarda un reporte en markdown.

    Args:
        tipo: semanal, ejecutivo o alerta.
        periodo: período cubierto, por ejemplo "2026-10-05 a 2026-10-11".
        contenido: texto completo del reporte en markdown.
    """
    return ejecutar(
        lambda: get_store().guardar_reporte(tipo=tipo, periodo=periodo, contenido=contenido, agente=AGENTE)
    )
