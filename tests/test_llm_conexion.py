"""Fase 2 contra OpenRouter real. Consume cupo: correr con `pytest -m llm -s`."""

import pytest
from strands import Agent

from pm_agents import llm
from pm_agents.config import settings
from pm_agents.tools import crear_compromiso, listar_compromisos

pytestmark = pytest.mark.llm


def usos_de_tool(agente: Agent) -> list[str]:
    return [
        bloque["toolUse"]["name"]
        for mensaje in agente.messages
        for bloque in mensaje["content"]
        if "toolUse" in bloque
    ]


def test_agente_free_llama_a_una_tool(store):
    """Criterio: un agente con modelo :free llama a una tool y responde."""
    crear_compromiso("Enviar el plan de pruebas", "Ana", "2026-10-15")
    crear_compromiso("Revisar el presupuesto del trimestre", "Beto")
    ejecucion = llm.iniciar_ejecucion()

    agente = Agent(
        model=llm.crear_modelo(settings.model_specialist),
        system_prompt="Respondés en español, breve. Usá las tools para consultar datos.",
        tools=[listar_compromisos],
        callback_handler=None,
    )
    respuesta = str(agente("¿Quién es responsable de enviar el plan de pruebas?"))
    print(f"\nRespuesta: {respuesta}\nSolicitudes: {ejecucion.solicitudes}")

    assert "listar_compromisos" in usos_de_tool(agente)
    assert "Ana" in respuesta
    assert ejecucion.usadas <= 4


def test_fallback_se_activa_al_forzar_error():
    """Criterio: con un modelo primario inexistente, el pedido lo responde MODEL_FALLBACK."""
    ejecucion = llm.iniciar_ejecucion()
    modelo = llm.crear_modelo("pm-agents/modelo-inexistente:free")
    agente = Agent(model=modelo, callback_handler=None)

    respuesta = str(agente("Respondé solo con la palabra: listo"))
    print(f"\nRespuesta: {respuesta}\nSolicitudes: {ejecucion.solicitudes}")

    assert ejecucion.solicitudes == [
        "pm-agents/modelo-inexistente:free",
        "pm-agents/modelo-inexistente:free",
        settings.model_fallback,
    ]
    assert "listo" in respuesta.lower()
