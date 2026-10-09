"""Flujos de entrada fija.

Fase 3: procesar_minuta solo usa el especialista de compromisos.
En la Fase 4 pasa a ser el grafo compromisos → riesgos → reportes.
"""

from pm_agents.agents.especialistas import agente_compromisos
from pm_agents.agents.prompts import PEDIDO_MINUTA


def procesar_minuta(texto: str, origen: str) -> str:
    """Extrae los compromisos de una minuta y devuelve la respuesta del agente."""
    return agente_compromisos(PEDIDO_MINUTA.format(origen=origen, texto=texto.strip()))
