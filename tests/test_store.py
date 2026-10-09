from datetime import date

import pytest
from pydantic import ValidationError

from pm_agents.store import ErrorDeDatos, Store


def test_crear_y_listar_compromisos(store):
    c1 = store.crear_compromiso("Enviar el plan de pruebas", "Ana", "minuta-01", "2026-10-15")
    c2 = store.crear_compromiso("Revisar presupuesto", "", "manual")
    assert (c1.id, c2.id) == ("C-001", "C-002")
    assert c1.fecha_limite == date(2026, 10, 15)
    assert [c.id for c in store.listar_compromisos()] == ["C-001", "C-002"]
    assert [c.id for c in store.listar_compromisos(responsable="ana")] == ["C-001"]
    assert store.listar_compromisos(estado="cumplido") == []


def test_crear_compromiso_registra_evento(store):
    c = store.crear_compromiso("Enviar el plan de pruebas", "Ana", "minuta-01")
    eventos = store.listar_eventos()
    assert len(eventos) == 1
    assert eventos[0].tipo == "compromiso.creado"
    assert eventos[0].payload["id"] == c.id


def test_crear_compromiso_duplicado_falla(store):
    store.crear_compromiso("Enviar el plan de pruebas", "Ana", "minuta-01")
    with pytest.raises(ErrorDeDatos, match="C-001"):
        store.crear_compromiso("  enviar el plan  de pruebas ", "ana", "minuta-02")
    assert len(store.listar_compromisos()) == 1
    assert len(store.listar_eventos()) == 1


def test_escritura_invalida_no_deja_rastros(store):
    with pytest.raises(ValidationError):
        store.crear_compromiso("Hola", "Ana", "manual")
    assert store.listar_compromisos() == []
    assert store.listar_eventos() == []


def test_actualizar_compromiso(store):
    store.crear_compromiso("Enviar el plan de pruebas", "Ana", "manual")
    c = store.actualizar_compromiso("C-001", {"estado": "cumplido", "responsable": "Beto"}, agente="compromisos")
    assert c.estado == "cumplido"
    assert store.obtener_compromiso("C-001").responsable == "Beto"
    evento = store.listar_eventos()[0]
    assert evento.tipo == "compromiso.actualizado"
    assert evento.agente == "compromisos"
    assert evento.payload["cambios"]["estado"] == {"antes": "pendiente", "despues": "cumplido"}


@pytest.mark.parametrize(
    "id,cambios,error",
    [
        ("C-999", {"estado": "cumplido"}, ErrorDeDatos),
        ("C-001", {"origen": "otro"}, ErrorDeDatos),
        ("C-001", {"estado": "pendiente"}, ErrorDeDatos),  # sin cambios
        ("C-001", {"estado": "terminado"}, ValidationError),
    ],
)
def test_actualizar_compromiso_invalido(store, id, cambios, error):
    store.crear_compromiso("Enviar el plan de pruebas", "Ana", "manual")
    with pytest.raises(error):
        store.actualizar_compromiso(id, cambios)
    assert len(store.listar_eventos()) == 1


def test_marcar_vencidos(store):
    store.crear_compromiso("Tarea vencida", "Ana", "manual", "2026-10-01")
    store.crear_compromiso("Tarea a tiempo", "Ana", "manual", "2026-10-20")
    store.crear_compromiso("Tarea sin fecha", "Ana", "manual")
    store.crear_compromiso("Tarea cumplida", "Ana", "manual", "2026-10-01")
    store.actualizar_compromiso("C-004", {"estado": "cumplido"})

    vencidos = store.marcar_vencidos(hoy=date(2026, 10, 9))
    assert [c.id for c in vencidos] == ["C-001"]
    assert store.obtener_compromiso("C-001").estado == "vencido"
    assert store.listar_eventos(tipo="compromiso.vencido")[0].payload["id"] == "C-001"
    # Idempotente: una segunda pasada no vuelve a marcar.
    assert store.marcar_vencidos(hoy=date(2026, 10, 9)) == []


def test_registrar_y_listar_riesgos(store):
    store.crear_compromiso("Tarea vencida", "Ana", "manual", "2026-10-01")
    r1 = store.registrar_riesgo("Atraso en pruebas", "C-001 vencido", 4, 4, "Reasignar", ["C-001"])
    r2 = store.registrar_riesgo("Proveedor lento", "Sin respuesta", 2, 3, "Escalar")
    assert (r1.id, r1.severidad) == ("R-001", 16)
    assert [r.id for r in store.listar_riesgos()] == ["R-001", "R-002"]
    assert [r.id for r in store.listar_riesgos(severidad_minima=12)] == ["R-001"]
    assert store.obtener_riesgo("R-001").compromisos_relacionados == ["C-001"]
    assert store.listar_eventos(tipo="riesgo.creado")[0].payload["severidad"] == 6


def test_riesgo_con_compromiso_inexistente_falla(store):
    with pytest.raises(ErrorDeDatos, match="C-404"):
        store.registrar_riesgo("Atraso", "x", 3, 3, "y", ["C-404"])
    assert store.listar_riesgos() == []


def test_no_duplica_riesgo_abierto(store):
    store.registrar_riesgo("Atraso en pruebas", "x", 3, 3, "y")
    with pytest.raises(ErrorDeDatos, match="R-001"):
        store.registrar_riesgo("ATRASO en  pruebas", "otro", 4, 4, "z")
    # Cerrado el anterior, se puede volver a registrar.
    store.actualizar_riesgo("R-001", {"estado": "cerrado"})
    assert store.registrar_riesgo("Atraso en pruebas", "x", 3, 3, "y").id == "R-002"


def test_actualizar_riesgo_recalcula_severidad(store):
    store.registrar_riesgo("Atraso en pruebas", "x", 2, 3, "y")
    r = store.actualizar_riesgo("R-001", {"probabilidad": 5}, agente="riesgos")
    assert r.severidad == 15
    assert store.listar_riesgos(severidad_minima=15)[0].id == "R-001"
    cambios = store.listar_eventos(tipo="riesgo.actualizado")[0].payload["cambios"]
    assert cambios["severidad"] == {"antes": 6, "despues": 15}


def test_guardar_reporte(store):
    rep = store.guardar_reporte("semanal", "2026-10-05 a 2026-10-11", "# Estado")
    assert rep.id == "REP-001"
    assert store.listar_reportes(tipo="semanal")[0].contenido == "# Estado"
    evento = store.listar_eventos()[0]
    assert evento.tipo == "reporte.generado"
    assert evento.payload == {"id": "REP-001", "tipo": "semanal", "periodo": "2026-10-05 a 2026-10-11"}


def test_cada_escritura_genera_un_evento(store):
    store.crear_compromiso("Tarea vencida", "Ana", "manual", "2020-01-01")
    store.actualizar_compromiso("C-001", {"responsable": "Beto"})
    store.marcar_vencidos(hoy=date(2026, 10, 9))
    store.registrar_riesgo("Atraso", "x", 3, 3, "y", ["C-001"])
    store.actualizar_riesgo("R-001", {"estado": "mitigado"})
    store.guardar_reporte("alerta", "2026-10-09", "Alerta")
    tipos = [e.tipo for e in reversed(store.listar_eventos())]
    assert tipos == [
        "compromiso.creado",
        "compromiso.actualizado",
        "compromiso.vencido",
        "riesgo.creado",
        "riesgo.actualizado",
        "reporte.generado",
    ]


def test_persistencia_entre_conexiones(tmp_path):
    ruta = tmp_path / "p.db"
    s1 = Store(ruta)
    s1.crear_compromiso("Enviar el plan de pruebas", "Ana", "manual")
    s1.cerrar()
    s2 = Store(ruta)
    assert s2.listar_compromisos()[0].descripcion == "Enviar el plan de pruebas"
    assert s2.crear_compromiso("Otra tarea más", "Ana", "manual").id == "C-002"
    s2.cerrar()
