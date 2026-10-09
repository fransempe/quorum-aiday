"""Eval de la Fase 3 contra OpenRouter real (~8 solicitudes por minuta).

Correr con: pytest -m llm -s tests/evals/test_eval_compromisos.py
"""

import pytest

from pm_agents import llm
from pm_agents.agents.especialistas import agente_compromisos
from pm_agents.agents.prompts import PEDIDO_MINUTA
from pm_agents.store import Store, set_store
from tests.evals.evaluacion import cargar_casos, evaluar

UMBRAL = 0.8


@pytest.mark.llm
def test_extraccion_de_compromisos(tmp_path):
    resultados = []
    for nombre, texto, esperado in cargar_casos():
        store = Store(tmp_path / f"{nombre}.db")
        set_store(store)
        ejecucion = llm.iniciar_ejecucion()
        try:
            agente_compromisos(PEDIDO_MINUTA.format(origen=nombre, texto=texto.strip()))
        except (llm.CupoExcedido, llm.ErrorModelo) as e:
            print(f"\n{nombre}: el flujo se cortó ({e})")
        res = evaluar(texto, esperado, store.listar_compromisos())
        resultados.append(res)
        set_store(None)
        store.cerrar()

        print(f"\n== {nombre}: {len(res.encontrados)}/{res.esperados} encontrados, {ejecucion.usadas} solicitudes")
        for etiqueta, items in [
            ("Faltantes", res.faltantes),
            ("Responsables inventados", res.responsables_inventados),
            ("Fechas distintas", res.fechas_distintas),
            ("Extra (no esperados)", res.extra),
        ]:
            for item in items:
                print(f"   {etiqueta}: {item}")

    encontrados = sum(len(r.encontrados) for r in resultados)
    esperados = sum(r.esperados for r in resultados)
    inventados = [i for r in resultados for i in r.responsables_inventados]
    print(f"\nTOTAL: {encontrados}/{esperados} = {encontrados / esperados:.0%}")

    assert encontrados / esperados >= UMBRAL
    assert inventados == []
