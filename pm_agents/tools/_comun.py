"""Utilidades compartidas por las tools."""

import json
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ValidationError


def a_json(datos: Any) -> str:
    """Serializa modelos o listas de modelos a JSON compacto para el LLM."""
    if isinstance(datos, BaseModel):
        datos = datos.model_dump(mode="json")
    elif isinstance(datos, list):
        datos = [d.model_dump(mode="json") if isinstance(d, BaseModel) else d for d in datos]
    return json.dumps(datos, ensure_ascii=False)


def ejecutar(operacion: Callable[[], Any]) -> str:
    """Corre una operación del store y devuelve JSON o un mensaje de error legible."""
    try:
        return a_json(operacion())
    except ValidationError as e:
        detalles = "; ".join(f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors())
        return f"Error de validación: {detalles}"
    except ValueError as e:
        return f"Error: {e}"


def sin_vacios(**campos: Any) -> dict[str, Any]:
    """Descarta los parámetros que el agente no pasó (None)."""
    return {k: v for k, v in campos.items() if v is not None}
