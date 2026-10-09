"""Repositorio SQLite del estado compartido.

Toda escritura se valida con Pydantic y registra un Evento en la misma transacción.
"""

import json
import sqlite3
import threading
from datetime import date, datetime
from pathlib import Path
from typing import Any

from pm_agents.config import settings
from pm_agents.models import Compromiso, Evento, Reporte, Riesgo, TipoEvento

ESQUEMA = """
CREATE TABLE IF NOT EXISTS compromisos (
    id TEXT PRIMARY KEY,
    descripcion TEXT NOT NULL,
    responsable TEXT NOT NULL,
    fecha_limite TEXT,
    estado TEXT NOT NULL,
    origen TEXT NOT NULL,
    creado_en TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS riesgos (
    id TEXT PRIMARY KEY,
    titulo TEXT NOT NULL,
    descripcion TEXT NOT NULL,
    probabilidad INTEGER NOT NULL,
    impacto INTEGER NOT NULL,
    severidad INTEGER NOT NULL,
    mitigacion TEXT NOT NULL,
    compromisos_relacionados TEXT NOT NULL,
    estado TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS eventos (
    id TEXT PRIMARY KEY,
    tipo TEXT NOT NULL,
    payload TEXT NOT NULL,
    agente TEXT NOT NULL,
    creado_en TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reportes (
    id TEXT PRIMARY KEY,
    tipo TEXT NOT NULL,
    periodo TEXT NOT NULL,
    contenido TEXT NOT NULL,
    creado_en TEXT NOT NULL
);
"""

CAMPOS_COMPROMISO_EDITABLES = {"descripcion", "responsable", "fecha_limite", "estado"}
CAMPOS_RIESGO_EDITABLES = {
    "titulo", "descripcion", "probabilidad", "impacto", "mitigacion",
    "compromisos_relacionados", "estado",
}


class ErrorDeDatos(ValueError):
    """Error de negocio: entidad inexistente, duplicada o cambio inválido."""


def _normalizar(texto: str) -> str:
    return " ".join(texto.lower().split())


class Store:
    def __init__(self, db_path: str | Path):
        if str(db_path) != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        # Los nodos del grafo pueden correr en otros hilos: una conexión compartida con lock.
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock, self._conn:
            self._conn.executescript(ESQUEMA)

    def cerrar(self) -> None:
        self._conn.close()

    # ---------- internos ----------

    def _siguiente_id(self, tabla: str, prefijo: str) -> str:
        fila = self._conn.execute(
            f"SELECT COALESCE(MAX(CAST(SUBSTR(id, ?) AS INTEGER)), 0) FROM {tabla}",
            (len(prefijo) + 1,),
        ).fetchone()
        return f"{prefijo}{fila[0] + 1:03d}"

    def _registrar_evento(self, tipo: TipoEvento, payload: dict[str, Any], agente: str) -> Evento:
        evento = Evento(
            id=self._siguiente_id("eventos", "E-"), tipo=tipo, payload=payload, agente=agente
        )
        self._conn.execute(
            "INSERT INTO eventos VALUES (?, ?, ?, ?, ?)",
            (
                evento.id,
                evento.tipo,
                json.dumps(evento.payload, ensure_ascii=False),
                evento.agente,
                evento.creado_en.isoformat(),
            ),
        )
        return evento

    @staticmethod
    def _diff(antes: dict[str, Any], despues: dict[str, Any], campos: set[str]) -> dict[str, Any]:
        return {
            c: {"antes": antes[c], "despues": despues[c]}
            for c in sorted(campos)
            if antes[c] != despues[c]
        }

    # ---------- compromisos ----------

    def _guardar_compromiso(self, c: Compromiso, insertar: bool) -> None:
        valores = (
            c.descripcion,
            c.responsable,
            c.fecha_limite.isoformat() if c.fecha_limite else None,
            c.estado,
            c.origen,
            c.creado_en.isoformat(),
        )
        if insertar:
            self._conn.execute("INSERT INTO compromisos VALUES (?, ?, ?, ?, ?, ?, ?)", (c.id, *valores))
        else:
            self._conn.execute(
                "UPDATE compromisos SET descripcion=?, responsable=?, fecha_limite=?, estado=?,"
                " origen=?, creado_en=? WHERE id=?",
                (*valores, c.id),
            )

    def crear_compromiso(
        self,
        descripcion: str,
        responsable: str,
        origen: str,
        fecha_limite: date | str | None = None,
        agente: str = "manual",
    ) -> Compromiso:
        with self._lock, self._conn:
            nuevo = Compromiso(
                id=self._siguiente_id("compromisos", "C-"),
                descripcion=descripcion,
                responsable=responsable,
                fecha_limite=fecha_limite,
                origen=origen,
            )
            for existente in self._listar_compromisos():
                if (
                    existente.estado != "cancelado"
                    and _normalizar(existente.descripcion) == _normalizar(nuevo.descripcion)
                    and _normalizar(existente.responsable) == _normalizar(nuevo.responsable)
                ):
                    raise ErrorDeDatos(f"Ya existe el compromiso {existente.id} con esa descripción y responsable.")
            self._guardar_compromiso(nuevo, insertar=True)
            self._registrar_evento("compromiso.creado", nuevo.model_dump(mode="json"), agente)
            return nuevo

    def _listar_compromisos(self, estado: str | None = None, responsable: str | None = None) -> list[Compromiso]:
        sql, params = "SELECT * FROM compromisos WHERE 1=1", []
        if estado:
            sql += " AND estado = ?"
            params.append(estado)
        if responsable is not None:
            sql += " AND lower(responsable) = lower(?)"
            params.append(responsable.strip())
        sql += " ORDER BY rowid"
        return [Compromiso.model_validate(dict(f)) for f in self._conn.execute(sql, params)]

    def listar_compromisos(self, estado: str | None = None, responsable: str | None = None) -> list[Compromiso]:
        with self._lock:
            return self._listar_compromisos(estado, responsable)

    def obtener_compromiso(self, id: str) -> Compromiso:
        with self._lock:
            return self._obtener_compromiso(id)

    def _obtener_compromiso(self, id: str) -> Compromiso:
        fila = self._conn.execute("SELECT * FROM compromisos WHERE id = ?", (id.strip(),)).fetchone()
        if fila is None:
            raise ErrorDeDatos(f"No existe el compromiso {id}.")
        return Compromiso.model_validate(dict(fila))

    def actualizar_compromiso(self, id: str, cambios: dict[str, Any], agente: str = "manual") -> Compromiso:
        invalidos = set(cambios) - CAMPOS_COMPROMISO_EDITABLES
        if invalidos:
            raise ErrorDeDatos(f"Campos no editables: {', '.join(sorted(invalidos))}.")
        with self._lock, self._conn:
            actual = self._obtener_compromiso(id)
            nuevo = Compromiso.model_validate({**actual.model_dump(), **cambios})
            diff = self._diff(actual.model_dump(mode="json"), nuevo.model_dump(mode="json"), CAMPOS_COMPROMISO_EDITABLES)
            if not diff:
                raise ErrorDeDatos(f"El compromiso {id} no tiene cambios.")
            self._guardar_compromiso(nuevo, insertar=False)
            self._registrar_evento("compromiso.actualizado", {"id": nuevo.id, "cambios": diff}, agente)
            return nuevo

    def marcar_vencidos(self, hoy: date | None = None, agente: str = "manual") -> list[Compromiso]:
        """Pasa a 'vencido' los compromisos pendientes con fecha límite anterior a hoy."""
        hoy = hoy or date.today()
        vencidos = []
        with self._lock, self._conn:
            for c in self._listar_compromisos(estado="pendiente"):
                if c.fecha_limite and c.fecha_limite < hoy:
                    c.estado = "vencido"
                    self._guardar_compromiso(c, insertar=False)
                    self._registrar_evento(
                        "compromiso.vencido",
                        {"id": c.id, "fecha_limite": c.fecha_limite.isoformat(), "responsable": c.responsable},
                        agente,
                    )
                    vencidos.append(c)
        return vencidos

    # ---------- riesgos ----------

    def _guardar_riesgo(self, r: Riesgo, insertar: bool) -> None:
        valores = (
            r.titulo,
            r.descripcion,
            r.probabilidad,
            r.impacto,
            r.severidad,
            r.mitigacion,
            json.dumps(r.compromisos_relacionados),
            r.estado,
        )
        if insertar:
            self._conn.execute("INSERT INTO riesgos VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (r.id, *valores))
        else:
            self._conn.execute(
                "UPDATE riesgos SET titulo=?, descripcion=?, probabilidad=?, impacto=?, severidad=?,"
                " mitigacion=?, compromisos_relacionados=?, estado=? WHERE id=?",
                (*valores, r.id),
            )

    @staticmethod
    def _fila_a_riesgo(fila: sqlite3.Row) -> Riesgo:
        datos = dict(fila)
        datos["compromisos_relacionados"] = json.loads(datos["compromisos_relacionados"])
        return Riesgo.model_validate(datos)

    def _validar_relacionados(self, ids: list[str]) -> None:
        for cid in ids:
            self._obtener_compromiso(cid)

    def registrar_riesgo(
        self,
        titulo: str,
        descripcion: str,
        probabilidad: int,
        impacto: int,
        mitigacion: str,
        compromisos_relacionados: list[str] | None = None,
        agente: str = "manual",
    ) -> Riesgo:
        with self._lock, self._conn:
            nuevo = Riesgo(
                id=self._siguiente_id("riesgos", "R-"),
                titulo=titulo,
                descripcion=descripcion,
                probabilidad=probabilidad,
                impacto=impacto,
                mitigacion=mitigacion,
                compromisos_relacionados=compromisos_relacionados or [],
            )
            for existente in self._listar_riesgos(estado="abierto"):
                if _normalizar(existente.titulo) == _normalizar(nuevo.titulo):
                    raise ErrorDeDatos(
                        f"Ya existe el riesgo abierto {existente.id} con ese título: actualizalo en lugar de duplicarlo."
                    )
            self._validar_relacionados(nuevo.compromisos_relacionados)
            self._guardar_riesgo(nuevo, insertar=True)
            self._registrar_evento("riesgo.creado", nuevo.model_dump(mode="json"), agente)
            return nuevo

    def _listar_riesgos(self, estado: str | None = None, severidad_minima: int | None = None) -> list[Riesgo]:
        sql, params = "SELECT * FROM riesgos WHERE 1=1", []
        if estado:
            sql += " AND estado = ?"
            params.append(estado)
        if severidad_minima is not None:
            sql += " AND severidad >= ?"
            params.append(severidad_minima)
        sql += " ORDER BY severidad DESC, rowid"
        return [self._fila_a_riesgo(f) for f in self._conn.execute(sql, params)]

    def listar_riesgos(self, estado: str | None = None, severidad_minima: int | None = None) -> list[Riesgo]:
        with self._lock:
            return self._listar_riesgos(estado, severidad_minima)

    def _obtener_riesgo(self, id: str) -> Riesgo:
        fila = self._conn.execute("SELECT * FROM riesgos WHERE id = ?", (id.strip(),)).fetchone()
        if fila is None:
            raise ErrorDeDatos(f"No existe el riesgo {id}.")
        return self._fila_a_riesgo(fila)

    def obtener_riesgo(self, id: str) -> Riesgo:
        with self._lock:
            return self._obtener_riesgo(id)

    def actualizar_riesgo(self, id: str, cambios: dict[str, Any], agente: str = "manual") -> Riesgo:
        invalidos = set(cambios) - CAMPOS_RIESGO_EDITABLES
        if invalidos:
            raise ErrorDeDatos(f"Campos no editables: {', '.join(sorted(invalidos))}.")
        with self._lock, self._conn:
            actual = self._obtener_riesgo(id)
            nuevo = Riesgo.model_validate({**actual.model_dump(exclude={"severidad"}), **cambios})
            if "compromisos_relacionados" in cambios:
                self._validar_relacionados(nuevo.compromisos_relacionados)
            campos = CAMPOS_RIESGO_EDITABLES | {"severidad"}
            diff = self._diff(actual.model_dump(mode="json"), nuevo.model_dump(mode="json"), campos)
            if not diff:
                raise ErrorDeDatos(f"El riesgo {id} no tiene cambios.")
            self._guardar_riesgo(nuevo, insertar=False)
            self._registrar_evento("riesgo.actualizado", {"id": nuevo.id, "cambios": diff}, agente)
            return nuevo

    # ---------- reportes ----------

    def guardar_reporte(self, tipo: str, periodo: str, contenido: str, agente: str = "manual") -> Reporte:
        with self._lock, self._conn:
            reporte = Reporte(
                id=self._siguiente_id("reportes", "REP-"), tipo=tipo, periodo=periodo, contenido=contenido
            )
            self._conn.execute(
                "INSERT INTO reportes VALUES (?, ?, ?, ?, ?)",
                (reporte.id, reporte.tipo, reporte.periodo, reporte.contenido, reporte.creado_en.isoformat()),
            )
            self._registrar_evento(
                "reporte.generado", {"id": reporte.id, "tipo": reporte.tipo, "periodo": reporte.periodo}, agente
            )
            return reporte

    def listar_reportes(self, tipo: str | None = None) -> list[Reporte]:
        sql, params = "SELECT * FROM reportes", []
        if tipo:
            sql += " WHERE tipo = ?"
            params.append(tipo)
        sql += " ORDER BY rowid"
        with self._lock:
            return [Reporte.model_validate(dict(f)) for f in self._conn.execute(sql, params)]

    # ---------- eventos ----------

    def listar_eventos(
        self, tipo: str | None = None, desde: datetime | None = None, limite: int = 50
    ) -> list[Evento]:
        """Eventos más recientes primero."""
        sql, params = "SELECT * FROM eventos WHERE 1=1", []
        if tipo:
            sql += " AND tipo = ?"
            params.append(tipo)
        if desde:
            sql += " AND creado_en >= ?"
            params.append(desde.isoformat())
        sql += " ORDER BY rowid DESC LIMIT ?"
        params.append(limite)
        with self._lock:
            filas = self._conn.execute(sql, params).fetchall()
        return [self._fila_a_evento(f) for f in filas]

    def ultimo_evento_id(self) -> str | None:
        with self._lock:
            fila = self._conn.execute("SELECT id FROM eventos ORDER BY rowid DESC LIMIT 1").fetchone()
        return fila["id"] if fila else None

    def eventos_posteriores(self, id_evento: str | None) -> list[Evento]:
        """Eventos registrados después de `id_evento` (todos si es None), en orden cronológico."""
        sql = "SELECT * FROM eventos"
        params: list[Any] = []
        if id_evento:
            sql += " WHERE rowid > (SELECT rowid FROM eventos WHERE id = ?)"
            params.append(id_evento)
        sql += " ORDER BY rowid"
        with self._lock:
            filas = self._conn.execute(sql, params).fetchall()
        return [self._fila_a_evento(f) for f in filas]

    @staticmethod
    def _fila_a_evento(fila: sqlite3.Row) -> Evento:
        return Evento.model_validate({**dict(fila), "payload": json.loads(fila["payload"])})


# Instancia compartida por las tools. Los tests la reemplazan con set_store().
_store: Store | None = None


def get_store() -> Store:
    global _store
    if _store is None:
        _store = Store(settings.db_path)
    return _store


def set_store(store: Store | None) -> None:
    global _store
    _store = store
