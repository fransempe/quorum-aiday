"""Fase 3 sin LLM: evaluador, especialista de compromisos y comando `minuta`."""

import pytest
from typer.testing import CliRunner

from pm_agents import cli, flows
from pm_agents.agents import especialistas
from pm_agents.config import settings
from pm_agents.llm import CupoExcedido
from pm_agents.models import Compromiso
from tests.evals.evaluacion import DIR_MINUTAS, cargar_casos, coincide, evaluar

runner = CliRunner()


def comp(id, descripcion, responsable="", fecha=None):
    return Compromiso(id=id, descripcion=descripcion, responsable=responsable, fecha_limite=fecha, origen="t")


# ---------- evaluador ----------

def test_casos_de_eval_son_consistentes():
    casos = cargar_casos()
    assert [n for n, _, _ in casos] == ["minuta-01", "minuta-02", "minuta-03"]
    for _, texto, esperado in casos:
        for exp in esperado["compromisos"]:
            # Las palabras clave matchean la descripción de referencia...
            assert coincide(exp["descripcion"], exp["palabras_clave"]), exp
            # ...y el responsable esperado figura en la minuta.
            assert exp["responsable"] in texto


def test_coincide_ignora_tildes_y_acepta_alternativas():
    assert coincide("Adaptar diseño para MÓVILES", ["celular|movil"])
    assert not coincide("Adaptar diseño", ["celular|movil"])


def test_evaluar_detecta_faltantes_e_inventados():
    texto = "Ana enviará el cronograma. Falta pedir el listado de salas, sin responsable."
    esperado = {
        "minuta": "m",
        "compromisos": [
            {"descripcion": "Enviar cronograma", "palabras_clave": ["cronograma"], "responsable": "Ana", "fecha_limite": None},
            {"descripcion": "Pedir listado", "palabras_clave": ["list"], "responsable": "", "fecha_limite": None},
            {"descripcion": "Otra cosa", "palabras_clave": ["inexistente"], "responsable": "", "fecha_limite": None},
        ],
    }
    extraidos = [
        comp("C-001", "Enviar el cronograma", "Ana Gómez"),
        comp("C-002", "Pedir el listado de salas", "Ana"),  # inventado: la minuta no asigna
        comp("C-003", "Llamar al proveedor", "Zoe"),  # extra e inventado
    ]
    res = evaluar(texto, esperado, extraidos)
    assert [i for _, i in res.encontrados] == ["C-001", "C-002"]
    assert res.faltantes == ["Otra cosa"]
    assert len(res.responsables_inventados) == 2
    assert res.extra == ["C-003: Llamar al proveedor"]


# ---------- especialista ----------

def test_agente_compromisos_tiene_sus_tools_y_prompt(monkeypatch):
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-test")
    monkeypatch.setattr(settings, "model_specialist", "x/especialista:free")
    agente = especialistas.crear_agente_compromisos()
    assert sorted(agente.tool_names) == [
        "actualizar_compromiso", "crear_compromiso", "listar_compromisos", "marcar_vencidos",
    ]
    assert "Fecha de hoy: " in agente.system_prompt
    assert agente.model.config["model_id"] == "x/especialista:free"


def test_hoy_legible():
    from datetime import date
    assert especialistas.hoy_legible(date(2026, 10, 9)) == "viernes 2026-10-09"


# ---------- comando minuta ----------

def test_minuta_muestra_cambios(store, monkeypatch):
    recibido = {}

    def falso(texto, origen):
        recibido.update(texto=texto, origen=origen)
        store.crear_compromiso("Entregar la maqueta", "Carla", origen, "2026-10-12", agente="compromisos")
        store.crear_compromiso("Pedir el listado de salas", "", origen, agente="compromisos")
        return "Creé 2 compromisos."

    monkeypatch.setattr(flows, "procesar_minuta", falso)
    resultado = runner.invoke(cli.app, ["minuta", str(DIR_MINUTAS / "minuta-01.md")])
    assert resultado.exit_code == 0, resultado.output
    assert recibido["origen"] == "minuta-01"
    assert "Carla se comprometió" in recibido["texto"]
    assert "Creé 2 compromisos." in resultado.output
    assert "Cambios registrados (2):" in resultado.output
    assert "+ C-001 Entregar la maqueta (Carla, 2026-10-12)" in resultado.output
    assert "+ C-002 Pedir el listado de salas (sin responsable, sin fecha)" in resultado.output
    assert "Solicitudes al modelo: 0/" in resultado.output


def test_minuta_corte_por_cupo_muestra_lo_ya_guardado(store, monkeypatch):
    def falso(texto, origen):
        store.crear_compromiso("Entregar la maqueta", "Carla", origen)
        raise CupoExcedido("Se alcanzó el tope de 15 solicitudes")

    monkeypatch.setattr(flows, "procesar_minuta", falso)
    resultado = runner.invoke(cli.app, ["minuta", "-", "--origen", "m-stdin"], input="Carla entrega la maqueta.")
    assert resultado.exit_code == 1
    assert "El flujo se cortó" in resultado.output
    assert "+ C-001 Entregar la maqueta" in resultado.output


@pytest.mark.parametrize("args,mensaje", [(["minuta", "no-existe.md"], "No existe"), (["minuta", "-"], "vacía")])
def test_minuta_entrada_invalida(store, args, mensaje):
    resultado = runner.invoke(cli.app, args, input="")
    assert resultado.exit_code == 2
    assert mensaje in resultado.output


def test_eventos_posteriores(store):
    assert store.ultimo_evento_id() is None
    store.crear_compromiso("Primera tarea", "Ana", "m")
    marca = store.ultimo_evento_id()
    store.crear_compromiso("Segunda tarea", "Ana", "m")
    assert [e.payload["id"] for e in store.eventos_posteriores(marca)] == ["C-002"]
    assert len(store.eventos_posteriores(None)) == 2
