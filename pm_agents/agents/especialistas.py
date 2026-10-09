"""Especialistas expuestos como tools (patrón agents-as-tools)."""

from datetime import date

from strands import Agent, tool

from pm_agents.agents.prompts import PROMPT_COMPROMISOS
from pm_agents.config import settings
from pm_agents.llm import crear_modelo
from pm_agents.tools import (
    actualizar_compromiso,
    crear_compromiso,
    listar_compromisos,
    marcar_vencidos,
)

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def hoy_legible(hoy: date | None = None) -> str:
    """Ej.: 'viernes 2026-10-09'. El día de la semana ayuda a resolver fechas relativas."""
    hoy = hoy or date.today()
    return f"{DIAS[hoy.weekday()]} {hoy.isoformat()}"


def crear_agente_compromisos() -> Agent:
    return Agent(
        model=crear_modelo(settings.model_specialist),
        system_prompt=PROMPT_COMPROMISOS.format(hoy=hoy_legible()),
        tools=[listar_compromisos, crear_compromiso, actualizar_compromiso, marcar_vencidos],
        callback_handler=None,
    )


@tool
def agente_compromisos(pedido: str) -> str:
    """Gestiona compromisos del proyecto: los extrae de reuniones, los crea, actualiza o marca vencidos.
    Usar para tareas, acuerdos, responsables o fechas.

    Args:
        pedido: qué hacer, con todo el contexto necesario (por ejemplo, el texto de la minuta).
    """
    return str(crear_agente_compromisos()(pedido))
