"""Tools de compromisos."""

from typing import Literal

from strands import tool

from pm_agents.store import get_store
from pm_agents.tools._comun import ejecutar, sin_vacios

AGENTE = "compromisos"


@tool
def listar_compromisos(estado: str | None = None, responsable: str | None = None) -> str:
    """Lista compromisos del proyecto.

    Args:
        estado: filtra por pendiente, cumplido, vencido o cancelado. Opcional.
        responsable: filtra por responsable exacto. Opcional.
    """
    return ejecutar(lambda: get_store().listar_compromisos(estado, responsable))


@tool
def crear_compromiso(
    descripcion: str, responsable: str = "", fecha_limite: str = "", origen: str = "manual"
) -> str:
    """Crea un compromiso nuevo.

    Args:
        descripcion: acción concreta a realizar.
        responsable: persona a cargo. Vacío si no se menciona.
        fecha_limite: fecha en formato AAAA-MM-DD. Vacío si no se menciona.
        origen: id de la minuta o "manual".
    """
    return ejecutar(
        lambda: get_store().crear_compromiso(
            descripcion=descripcion,
            responsable=responsable,
            fecha_limite=fecha_limite or None,
            origen=origen,
            agente=AGENTE,
        )
    )


@tool
def actualizar_compromiso(
    id: str,
    estado: Literal["pendiente", "cumplido", "vencido", "cancelado"] | None = None,
    responsable: str | None = None,
    fecha_limite: str | None = None,
    descripcion: str | None = None,
) -> str:
    """Actualiza campos de un compromiso existente. Solo se cambian los campos indicados.

    Args:
        id: id del compromiso, por ejemplo C-001.
        estado: nuevo estado.
        responsable: nuevo responsable.
        fecha_limite: nueva fecha AAAA-MM-DD.
        descripcion: nueva descripción.
    """
    cambios = sin_vacios(
        estado=estado, responsable=responsable, fecha_limite=fecha_limite, descripcion=descripcion
    )
    return ejecutar(lambda: get_store().actualizar_compromiso(id, cambios, agente=AGENTE))


@tool
def marcar_vencidos() -> str:
    """Marca como vencidos los compromisos pendientes cuya fecha límite ya pasó. Devuelve los afectados."""
    return ejecutar(lambda: get_store().marcar_vencidos(agente=AGENTE))
