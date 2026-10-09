"""Las tools se llaman directo (sin LLM): @tool conserva la firma original."""

import json

from pm_agents.tools import (
    actualizar_compromiso,
    actualizar_riesgo,
    crear_compromiso,
    guardar_reporte,
    listar_compromisos,
    listar_eventos,
    listar_riesgos,
    marcar_vencidos,
    registrar_riesgo,
)


def test_ciclo_compromisos(store):
    creado = json.loads(crear_compromiso("Enviar el plan de pruebas", "Ana", "2026-10-15", "minuta-01"))
    assert creado["id"] == "C-001"
    assert json.loads(listar_compromisos())[0]["responsable"] == "Ana"

    actualizado = json.loads(actualizar_compromiso("C-001", estado="cumplido"))
    assert actualizado["estado"] == "cumplido"
    assert actualizado["fecha_limite"] == "2026-10-15"  # los campos no indicados no cambian
    assert json.loads(listar_compromisos(estado="cumplido"))[0]["id"] == "C-001"


def test_crear_compromiso_sin_responsable_ni_fecha(store):
    creado = json.loads(crear_compromiso("Revisar presupuesto"))
    assert creado["responsable"] == ""
    assert creado["fecha_limite"] is None
    assert creado["origen"] == "manual"


def test_errores_se_devuelven_como_texto(store):
    assert crear_compromiso("Hola").startswith("Error de validación: descripcion")
    assert crear_compromiso("Tarea con fecha mala", fecha_limite="mañana").startswith("Error de validación")
    assert actualizar_compromiso("C-404", estado="cumplido") == "Error: No existe el compromiso C-404."
    assert registrar_riesgo("Atraso", "x", 9, 3, "y").startswith("Error de validación: probabilidad")
    assert listar_eventos(desde="ayer").startswith("Error")


def test_marcar_vencidos(store):
    crear_compromiso("Tarea del pasado", "Ana", "2020-01-01")
    crear_compromiso("Tarea del futuro", "Ana", "2099-01-01")
    vencidos = json.loads(marcar_vencidos())
    assert [c["id"] for c in vencidos] == ["C-001"]


def test_ciclo_riesgos(store):
    crear_compromiso("Tarea del pasado", "Ana", "2020-01-01")
    creado = json.loads(registrar_riesgo("Atraso en pruebas", "C-001 vencido", 4, 3, "Reasignar", ["C-001"]))
    assert creado["severidad"] == 12

    duplicado = registrar_riesgo("Atraso en pruebas", "otra vez", 2, 2, "z")
    assert duplicado.startswith("Error: Ya existe el riesgo abierto R-001")

    actualizado = json.loads(actualizar_riesgo("R-001", impacto=5))
    assert actualizado["severidad"] == 20
    assert actualizado["mitigacion"] == "Reasignar"
    assert json.loads(listar_riesgos(severidad_minima=20))[0]["id"] == "R-001"
    assert json.loads(listar_riesgos(estado="cerrado")) == []


def test_reporte_y_eventos_con_agente(store):
    crear_compromiso("Enviar el plan de pruebas", "Ana")
    registrar_riesgo("Atraso en pruebas", "x", 3, 3, "y")
    assert json.loads(guardar_reporte("semanal", "semana 41", "# Estado"))["id"] == "REP-001"

    eventos = json.loads(listar_eventos())
    assert [(e["tipo"], e["agente"]) for e in eventos] == [
        ("reporte.generado", "reportes"),
        ("riesgo.creado", "riesgos"),
        ("compromiso.creado", "compromisos"),
    ]
    assert len(json.loads(listar_eventos(tipo="riesgo.creado"))) == 1
    assert len(json.loads(listar_eventos(desde="2000-01-01", limite=2))) == 2


def test_tools_exponen_esquema_para_el_llm():
    spec = registrar_riesgo.tool_spec
    assert spec["name"] == "registrar_riesgo"
    props = spec["inputSchema"]["json"]["properties"]
    assert set(props) >= {"titulo", "probabilidad", "impacto", "mitigacion"}
    estados = actualizar_compromiso.tool_spec["inputSchema"]["json"]["properties"]["estado"]
    assert "cumplido" in json.dumps(estados)
