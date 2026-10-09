"""Tools de riesgos."""

from typing import Literal

from strands import tool

from pm_agents.store import get_store
from pm_agents.tools._comun import ejecutar, sin_vacios

AGENTE = "riesgos"


@tool
def listar_riesgos(estado: str | None = None, severidad_minima: int | None = None) -> str:
    """Lista riesgos ordenados por severidad (probabilidad x impacto), de mayor a menor.

    Args:
        estado: filtra por abierto, mitigado o cerrado. Opcional.
        severidad_minima: solo riesgos con severidad mayor o igual (1 a 25). Opcional.
    """
    return ejecutar(lambda: get_store().listar_riesgos(estado, severidad_minima))


@tool
def registrar_riesgo(
    titulo: str,
    descripcion: str,
    probabilidad: int,
    impacto: int,
    mitigacion: str,
    compromisos_relacionados: list[str] | None = None,
) -> str:
    """Registra un riesgo nuevo. Si ya hay uno abierto sobre el mismo tema, usar actualizar_riesgo.

    Args:
        titulo: título corto del riesgo.
        descripcion: hecho concreto que origina el riesgo.
        probabilidad: de 1 (baja) a 5 (casi segura).
        impacto: de 1 (menor) a 5 (crítico).
        mitigacion: acción concreta para reducirlo.
        compromisos_relacionados: ids de compromisos vinculados, por ejemplo ["C-001"].
    """
    return ejecutar(
        lambda: get_store().registrar_riesgo(
            titulo=titulo,
            descripcion=descripcion,
            probabilidad=probabilidad,
            impacto=impacto,
            mitigacion=mitigacion,
            compromisos_relacionados=compromisos_relacionados,
            agente=AGENTE,
        )
    )


@tool
def actualizar_riesgo(
    id: str,
    probabilidad: int | None = None,
    impacto: int | None = None,
    mitigacion: str | None = None,
    estado: Literal["abierto", "mitigado", "cerrado"] | None = None,
    descripcion: str | None = None,
    compromisos_relacionados: list[str] | None = None,
) -> str:
    """Actualiza un riesgo existente. Solo se cambian los campos indicados.

    Args:
        id: id del riesgo, por ejemplo R-001.
        probabilidad: nueva probabilidad de 1 a 5.
        impacto: nuevo impacto de 1 a 5.
        mitigacion: nueva mitigación.
        estado: nuevo estado.
        descripcion: nueva descripción.
        compromisos_relacionados: lista completa de ids de compromisos vinculados.
    """
    cambios = sin_vacios(
        probabilidad=probabilidad,
        impacto=impacto,
        mitigacion=mitigacion,
        estado=estado,
        descripcion=descripcion,
        compromisos_relacionados=compromisos_relacionados,
    )
    return ejecutar(lambda: get_store().actualizar_riesgo(id, cambios, agente=AGENTE))
