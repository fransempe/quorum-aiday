"""Conexión a OpenRouter vía OpenAIModel, con tope de solicitudes, reintento y modelo de respaldo.

Política ante 429 o error del modelo (cada intento consume cupo):
  1. intento con el modelo pedido;
  2. un reintento con backoff exponencial;
  3. cambio a MODEL_FALLBACK.
Si un modelo agota sus intentos, queda marcado como caído durante la ejecución y las
siguientes llamadas van directo al respaldo. El error final no es ModelThrottledException,
así Strands no reintenta por su cuenta.
"""

import asyncio
import logging
import threading
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any

import openai
from strands.models.openai import OpenAIModel
from strands.types.exceptions import ModelThrottledException

from pm_agents.config import settings

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1"
BACKOFF_BASE_S = 2.0
ERRORES_REINTENTABLES = (ModelThrottledException, openai.APIError)


class ErrorDeConfiguracion(RuntimeError):
    """Falta una variable de entorno necesaria."""


class CupoExcedido(RuntimeError):
    """Se alcanzó MAX_REQUESTS_PER_RUN en esta ejecución."""


class ErrorModelo(RuntimeError):
    """El modelo y su respaldo fallaron."""


@dataclass
class Ejecucion:
    """Estado de una ejecución (un comando de la CLI): cupo usado y modelos caídos."""

    maximo: int
    usadas: int = 0
    modelos_caidos: set[str] = field(default_factory=set)
    solicitudes: list[str] = field(default_factory=list)  # model_id de cada solicitud, en orden
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def consumir(self, model_id: str) -> None:
        with self._lock:
            if self.usadas >= self.maximo:
                raise CupoExcedido(
                    f"Se alcanzó el tope de {self.maximo} solicitudes por ejecución (MAX_REQUESTS_PER_RUN)."
                )
            self.usadas += 1
            self.solicitudes.append(model_id)


_ejecucion: Ejecucion | None = None


def iniciar_ejecucion(maximo: int | None = None) -> Ejecucion:
    """Reinicia el contador. Llamar al comienzo de cada comando."""
    global _ejecucion
    _ejecucion = Ejecucion(maximo=maximo if maximo is not None else settings.max_requests_per_run)
    return _ejecucion


def ejecucion_actual() -> Ejecucion:
    return _ejecucion or iniciar_ejecucion()


def _client_args() -> dict[str, Any]:
    if not settings.openrouter_api_key:
        raise ErrorDeConfiguracion("Falta OPENROUTER_API_KEY en el entorno o en .env.")
    # max_retries=0: el cliente de OpenAI no reintenta por su cuenta (cada reintento gasta cupo).
    return {"api_key": settings.openrouter_api_key, "base_url": OPENROUTER_URL, "max_retries": 0}


PARAMS = {"temperature": 0.2, "max_tokens": 2000}


class ModeloOpenRouter(OpenAIModel):
    """OpenAIModel que cuenta solicitudes, reintenta una vez y cae al modelo de respaldo."""

    def __init__(self, model_id: str, respaldo_id: str = "", backoff_base: float = BACKOFF_BASE_S):
        super().__init__(client_args=_client_args(), model_id=model_id, params=dict(PARAMS))
        self.respaldo_id = respaldo_id
        self.backoff_base = backoff_base
        self._respaldo = (
            OpenAIModel(client_args=_client_args(), model_id=respaldo_id, params=dict(PARAMS))
            if respaldo_id and respaldo_id != model_id
            else None
        )

    def _plan(self, ejecucion: Ejecucion) -> list[str]:
        primario = self.config["model_id"]
        plan = [] if primario in ejecucion.modelos_caidos else [primario, primario]
        if self._respaldo:
            plan.append(self.respaldo_id)
        return plan or [primario]  # sin respaldo y caído: un último intento

    def _stream_de(self, model_id: str, *args: Any, **kwargs: Any) -> AsyncGenerator[Any, None]:
        if self._respaldo and model_id == self.respaldo_id:
            return self._respaldo.stream(*args, **kwargs)
        return OpenAIModel.stream(self, *args, **kwargs)

    async def stream(self, *args: Any, **kwargs: Any) -> AsyncGenerator[Any, None]:  # type: ignore[override]
        ejecucion = ejecucion_actual()
        plan = self._plan(ejecucion)
        ultimo_error: Exception | None = None

        for intento, model_id in enumerate(plan):
            if intento > 0 and plan[intento - 1] == model_id:
                espera = self.backoff_base * 2 ** (intento - 1)
                logger.warning("Reintentando %s en %.0f s...", model_id, espera)
                await asyncio.sleep(espera)
            elif intento > 0:
                logger.warning("Cambiando al modelo de respaldo %s.", model_id)

            ejecucion.consumir(model_id)
            emitio = False
            try:
                async for evento in self._stream_de(model_id, *args, **kwargs):
                    emitio = True
                    yield evento
                return
            except ERRORES_REINTENTABLES as e:
                if emitio:
                    # La respuesta ya empezó a salir: no se puede reintentar sin duplicar contenido.
                    raise ErrorModelo(f"El modelo {model_id} falló a mitad de la respuesta: {e}") from e
                logger.warning("Falló %s: %s", model_id, e)
                ultimo_error = e
                siguiente = plan[intento + 1] if intento + 1 < len(plan) else None
                if siguiente != model_id:
                    ejecucion.modelos_caidos.add(model_id)

        raise ErrorModelo(f"Fallaron el modelo y su respaldo. Último error: {ultimo_error}") from ultimo_error


def crear_modelo(model_id: str) -> OpenAIModel:
    """Crea un modelo de OpenRouter con MODEL_FALLBACK como respaldo."""
    if not model_id:
        raise ErrorDeConfiguracion(
            "Falta el id de modelo: definí MODEL_ORCHESTRATOR, MODEL_SPECIALIST y MODEL_FALLBACK en .env."
        )
    return ModeloOpenRouter(model_id=model_id, respaldo_id=settings.model_fallback)
