"""Tests de llm.py sin red: se reemplaza OpenAIModel.stream por un stream falso."""

import json

import httpx
import openai
import pytest
from strands import Agent
from strands.models.openai import OpenAIModel
from strands.types.exceptions import ModelThrottledException

from pm_agents import llm
from pm_agents.config import settings
from pm_agents.llm import CupoExcedido, ErrorDeConfiguracion, ErrorModelo, ModeloOpenRouter
from pm_agents.tools import crear_compromiso, listar_compromisos

PRIMARIO, RESPALDO = "proveedor/primario:free", "proveedor/respaldo"


def texto(t: str) -> list[dict]:
    return [
        {"messageStart": {"role": "assistant"}},
        {"contentBlockStart": {"start": {}}},
        {"contentBlockDelta": {"delta": {"text": t}}},
        {"contentBlockStop": {}},
        {"messageStop": {"stopReason": "end_turn"}},
    ]


def llamada_tool(nombre: str, entrada: dict) -> list[dict]:
    return [
        {"messageStart": {"role": "assistant"}},
        {"contentBlockStart": {"start": {"toolUse": {"toolUseId": "t1", "name": nombre}}}},
        {"contentBlockDelta": {"delta": {"toolUse": {"input": json.dumps(entrada)}}}},
        {"contentBlockStop": {}},
        {"messageStop": {"stopReason": "tool_use"}},
    ]


def error_conexion() -> Exception:
    return openai.APIConnectionError(request=httpx.Request("POST", llm.OPENROUTER_URL))


@pytest.fixture
def falso(monkeypatch):
    """Guion por model_id: cada llamada consume el siguiente elemento (excepción o lista de eventos)."""
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-test")
    monkeypatch.setattr(settings, "model_fallback", RESPALDO)
    guion: dict[str, list] = {PRIMARIO: [], RESPALDO: []}
    llamadas: list[str] = []

    async def stream(self, *args, **kwargs):
        model_id = self.config["model_id"]
        llamadas.append(model_id)
        paso = guion[model_id].pop(0)
        if isinstance(paso, Exception):
            raise paso
        for evento in paso:
            yield evento

    monkeypatch.setattr(OpenAIModel, "stream", stream)
    llm.iniciar_ejecucion(maximo=15)
    return guion, llamadas


def modelo() -> ModeloOpenRouter:
    return ModeloOpenRouter(PRIMARIO, RESPALDO, backoff_base=0)


def agente(tools=None) -> Agent:
    return Agent(model=modelo(), tools=tools or [], callback_handler=None)


def test_respuesta_normal_usa_una_solicitud(falso):
    guion, llamadas = falso
    guion[PRIMARIO] = [texto("hola")]
    assert "hola" in str(agente()("decí hola"))
    assert llamadas == [PRIMARIO]
    assert llm.ejecucion_actual().usadas == 1


def test_reintenta_una_vez_ante_429(falso):
    guion, llamadas = falso
    guion[PRIMARIO] = [ModelThrottledException("429"), texto("ok")]
    assert "ok" in str(agente()("hola"))
    assert llamadas == [PRIMARIO, PRIMARIO]
    assert llm.ejecucion_actual().modelos_caidos == set()


def test_cambia_al_respaldo_y_lo_recuerda(falso):
    guion, llamadas = falso
    guion[PRIMARIO] = [ModelThrottledException("429"), error_conexion()]
    guion[RESPALDO] = [texto("respaldo"), texto("otra vez")]
    assert "respaldo" in str(agente()("hola"))
    assert llamadas == [PRIMARIO, PRIMARIO, RESPALDO]
    # Un agente nuevo en la misma ejecución va directo al respaldo.
    assert "otra vez" in str(agente()("hola"))
    assert llamadas[3:] == [RESPALDO]
    assert llm.ejecucion_actual().usadas == 4


def test_no_reintenta_en_bucle(falso):
    guion, llamadas = falso
    guion[PRIMARIO] = [ModelThrottledException("429")] * 10
    guion[RESPALDO] = [ModelThrottledException("429")] * 10
    with pytest.raises(ErrorModelo):
        agente()("hola")
    # Ni Strands ni el cliente de OpenAI agregan reintentos propios.
    assert llamadas == [PRIMARIO, PRIMARIO, RESPALDO]


def test_tope_de_solicitudes_corta_el_flujo(falso):
    guion, llamadas = falso
    llm.iniciar_ejecucion(maximo=2)
    guion[PRIMARIO] = [ModelThrottledException("429")] * 5
    guion[RESPALDO] = [texto("no llega")]
    with pytest.raises(CupoExcedido):
        agente()("hola")
    assert llamadas == [PRIMARIO, PRIMARIO]


def test_agente_llama_a_una_tool(falso, store):
    guion, llamadas = falso
    crear_compromiso("Enviar el plan de pruebas", "Ana")
    guion[PRIMARIO] = [llamada_tool("listar_compromisos", {}), texto("Hay 1 compromiso.")]
    a = agente([listar_compromisos])
    assert "1 compromiso" in str(a("¿cuántos compromisos hay?"))
    resultado = a.messages[2]["content"][0]["toolResult"]
    assert resultado["status"] == "success"
    assert "Enviar el plan de pruebas" in resultado["content"][0]["text"]
    assert llm.ejecucion_actual().usadas == 2


def test_cliente_sin_reintentos_propios(falso):
    m = modelo()
    assert m.client_args["max_retries"] == 0
    assert m.client_args["base_url"] == "https://openrouter.ai/api/v1"
    assert m.get_config()["params"] == {"temperature": 0.2, "max_tokens": 2000}


def test_crear_modelo_valida_configuracion(monkeypatch):
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-test")
    with pytest.raises(ErrorDeConfiguracion, match="MODEL_"):
        llm.crear_modelo("")
    monkeypatch.setattr(settings, "openrouter_api_key", "")
    with pytest.raises(ErrorDeConfiguracion, match="OPENROUTER_API_KEY"):
        llm.crear_modelo("x/y:free")
