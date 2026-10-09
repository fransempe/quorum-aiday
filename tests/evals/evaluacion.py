"""Comparación entre compromisos extraídos y esperados (sin LLM)."""

import json
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from pm_agents.models import Compromiso

RAIZ = Path(__file__).resolve().parents[2]
DIR_MINUTAS = RAIZ / "data" / "minutas_ejemplo"
DIR_EVALS = Path(__file__).resolve().parent


def normalizar(texto: str) -> str:
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return " ".join(sin_tildes.lower().split())


def coincide(descripcion: str, palabras_clave: list[str]) -> bool:
    """Cada término debe aparecer; un término acepta alternativas separadas por '|'."""
    d = normalizar(descripcion)
    return all(any(normalizar(alt) in d for alt in termino.split("|")) for termino in palabras_clave)


@dataclass
class Resultado:
    minuta: str
    esperados: int
    encontrados: list[tuple[str, str]] = field(default_factory=list)  # (esperado, id extraído)
    faltantes: list[str] = field(default_factory=list)
    responsables_inventados: list[str] = field(default_factory=list)
    fechas_distintas: list[str] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)


def cargar_casos() -> list[tuple[str, str, dict]]:
    """[(nombre, texto de la minuta, esperado)] para cada JSON de tests/evals/minuta-*.json."""
    casos = []
    for ruta in sorted(DIR_EVALS.glob("minuta-*.json")):
        esperado = json.loads(ruta.read_text(encoding="utf-8"))
        texto = (DIR_MINUTAS / f"{esperado['minuta']}.md").read_text(encoding="utf-8")
        casos.append((esperado["minuta"], texto, esperado))
    return casos


def evaluar(texto_minuta: str, esperado: dict, extraidos: list[Compromiso]) -> Resultado:
    res = Resultado(minuta=esperado["minuta"], esperados=len(esperado["compromisos"]))
    texto_norm = normalizar(texto_minuta)
    libres = list(extraidos)

    # Inventado: un responsable que no figura en la minuta.
    for c in extraidos:
        nombres = normalizar(c.responsable).split()
        if nombres and not any(n in texto_norm for n in nombres):
            res.responsables_inventados.append(f"{c.id}: '{c.responsable}' no aparece en la minuta")

    for exp in esperado["compromisos"]:
        match = next((c for c in libres if coincide(c.descripcion, exp["palabras_clave"])), None)
        if match is None:
            res.faltantes.append(exp["descripcion"])
            continue
        libres.remove(match)
        res.encontrados.append((exp["descripcion"], match.id))
        if exp["responsable"]:
            if normalizar(exp["responsable"]) not in normalizar(match.responsable):
                res.responsables_inventados.append(
                    f"{match.id}: responsable '{match.responsable}', esperado '{exp['responsable']}'"
                )
        elif match.responsable:
            # La minuta no asigna responsable: completarlo es inventarlo.
            res.responsables_inventados.append(f"{match.id}: '{match.responsable}' asignado sin estar en la minuta")
        fecha = match.fecha_limite.isoformat() if match.fecha_limite else None
        if fecha != exp["fecha_limite"]:
            res.fechas_distintas.append(f"{match.id}: {fecha}, esperada {exp['fecha_limite']}")

    res.extra = [f"{c.id}: {c.descripcion}" for c in libres]
    return res
