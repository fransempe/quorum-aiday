import pytest
from pydantic import ValidationError

from pm_agents.models import Compromiso, Evento, Reporte, Riesgo


def test_compromiso_valores_por_defecto():
    c = Compromiso(id="C-001", descripcion="Enviar el plan", responsable="Ana", origen="manual")
    assert c.estado == "pendiente"
    assert c.fecha_limite is None


def test_compromiso_fecha_vacia_es_none():
    c = Compromiso(id="C-001", descripcion="Enviar el plan", responsable="", fecha_limite="", origen="manual")
    assert c.fecha_limite is None


@pytest.mark.parametrize(
    "cambios",
    [{"descripcion": "Hola"}, {"estado": "terminado"}, {"fecha_limite": "mañana"}],
)
def test_compromiso_invalido(cambios):
    datos = {"id": "C-001", "descripcion": "Enviar el plan", "responsable": "Ana", "origen": "manual"}
    with pytest.raises(ValidationError):
        Compromiso(**{**datos, **cambios})


def test_riesgo_severidad_es_producto():
    r = Riesgo(id="R-001", titulo="Atraso", descripcion="x", probabilidad=4, impacto=3, mitigacion="y")
    assert r.severidad == 12
    assert r.model_dump()["severidad"] == 12


@pytest.mark.parametrize("campo,valor", [("probabilidad", 0), ("impacto", 6), ("estado", "pendiente")])
def test_riesgo_invalido(campo, valor):
    datos = {"id": "R-001", "titulo": "Atraso", "descripcion": "x", "probabilidad": 3, "impacto": 3, "mitigacion": "y"}
    with pytest.raises(ValidationError):
        Riesgo(**{**datos, campo: valor})


def test_evento_y_reporte_validan_tipo():
    with pytest.raises(ValidationError):
        Evento(id="E-001", tipo="compromiso.borrado", payload={}, agente="x")
    with pytest.raises(ValidationError):
        Reporte(id="REP-001", tipo="mensual", periodo="oct", contenido="# x")
