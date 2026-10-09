"""CLI de quorum: minuta, revision, preguntar, reporte."""

import logging
import sys
from collections.abc import Callable
from pathlib import Path

import typer
from strands.types.exceptions import MaxTokensReachedException

from pm_agents import llm
from pm_agents.llm import CupoExcedido, ErrorDeConfiguracion, ErrorModelo
from pm_agents.models import Evento
from pm_agents.store import get_store

app = typer.Typer(help="quorum: gestión de proyectos con agentes.", no_args_is_help=True)


@app.callback()
def principal() -> None:
    """quorum: gestión de proyectos con agentes."""


def describir_evento(e: Evento) -> str:
    p = e.payload
    if e.tipo == "compromiso.creado":
        responsable = p["responsable"] or "sin responsable"
        fecha = p["fecha_limite"] or "sin fecha"
        return f"+ {p['id']} {p['descripcion']} ({responsable}, {fecha})"
    if e.tipo == "compromiso.vencido":
        return f"! {p['id']} vencido (fecha límite {p['fecha_limite']})"
    if e.tipo in ("compromiso.actualizado", "riesgo.actualizado"):
        cambios = ", ".join(f"{c}: {v['antes']} → {v['despues']}" for c, v in p["cambios"].items())
        return f"~ {p['id']} {cambios}"
    if e.tipo == "riesgo.creado":
        return f"+ {p['id']} {p['titulo']} (severidad {p['severidad']})"
    if e.tipo == "reporte.generado":
        return f"+ {p['id']} reporte {p['tipo']} ({p['periodo']})"
    return f"{e.tipo} {p}"


def ejecutar_con_resumen(accion: Callable[[], str]) -> None:
    """Corre una acción con cupo nuevo, muestra la respuesta y los cambios registrados en la bitácora."""
    logging.basicConfig(level=logging.WARNING, format="aviso: %(message)s")
    # Strands avisa en cada turno que descarta el razonamiento de Nemotron del historial: es esperado.
    logging.getLogger("strands").setLevel(logging.ERROR)
    store = get_store()
    ejecucion = llm.iniciar_ejecucion()
    desde = store.ultimo_evento_id()
    codigo = 0
    try:
        respuesta = accion()
        typer.echo(f"\n{respuesta.strip()}\n")
    except ErrorDeConfiguracion as e:
        typer.echo(f"Error de configuración: {e}", err=True)
        raise typer.Exit(2)
    except (CupoExcedido, ErrorModelo, MaxTokensReachedException) as e:
        typer.echo(f"\nEl flujo se cortó: {e}", err=True)
        codigo = 1

    cambios = store.eventos_posteriores(desde)
    typer.echo(f"Cambios registrados ({len(cambios)}):")
    for evento in cambios:
        typer.echo(f"  {describir_evento(evento)}")
    if not cambios:
        typer.echo("  (ninguno)")
    typer.echo(f"Solicitudes al modelo: {ejecucion.usadas}/{ejecucion.maximo}")
    if codigo:
        raise typer.Exit(codigo)


@app.command()
def minuta(
    archivo: Path = typer.Argument(..., help="Archivo de texto con la minuta, o '-' para leer de la entrada estándar."),
    origen: str | None = typer.Option(None, help="Id de la minuta. Por defecto, el nombre del archivo."),
) -> None:
    """Procesa una minuta: extrae compromisos y resume los cambios."""
    from pm_agents.flows import procesar_minuta

    if str(archivo) == "-":
        texto, origen = sys.stdin.read(), origen or "minuta"
    else:
        if not archivo.is_file():
            typer.echo(f"No existe el archivo {archivo}.", err=True)
            raise typer.Exit(2)
        texto, origen = archivo.read_text(encoding="utf-8"), origen or archivo.stem
    if not texto.strip():
        typer.echo("La minuta está vacía.", err=True)
        raise typer.Exit(2)

    typer.echo(f"Procesando minuta '{origen}'...")
    ejecutar_con_resumen(lambda: procesar_minuta(texto, origen))


if __name__ == "__main__":
    app()
