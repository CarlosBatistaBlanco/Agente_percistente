"""Base de datos SQLite: guarda cada tarea y su estado (memoria persistente del agente)."""
import datetime
import json
import sqlite3
import threading

from config import DB_PATH

_lock = threading.Lock()
CAMPOS_JSON = {"analisis", "resultado", "verificacion"}

# Estados: nueva -> analizando -> pendiente_revision | necesita_aclaracion | ignorada | error
#          pendiente_revision -> enviada | rechazada


def _con():
    c = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
    c.row_factory = sqlite3.Row
    return c


def ahora():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def init():
    with _lock, _con() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS tareas(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                canal TEXT, id_externo TEXT, remitente TEXT, destino TEXT,
                asunto TEXT, mensaje TEXT, referencia TEXT,
                estado TEXT, analisis TEXT, resultado TEXT, verificacion TEXT,
                respuesta TEXT, archivo TEXT, error TEXT, instrucciones_extra TEXT,
                creado TEXT, actualizado TEXT,
                UNIQUE(canal, id_externo)
            );
            CREATE TABLE IF NOT EXISTS bitacora_memoria(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tipo TEXT,
                origen TEXT,
                detalle TEXT,
                datos_extra TEXT,
                fecha TEXT
            );
            CREATE TABLE IF NOT EXISTS conversacion(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT,
                rol TEXT,
                texto TEXT,
                fecha TEXT
            );
            CREATE TABLE IF NOT EXISTS estado_chat(
                chat_id TEXT PRIMARY KEY,
                modo TEXT,
                actualizado TEXT
            );
            """
        )


def _dict(row):
    if row is None:
        return None
    d = dict(row)
    for k in CAMPOS_JSON:
        if d.get(k):
            try:
                d[k] = json.loads(d[k])
            except Exception:
                pass
    return d


def crear(canal, id_externo, remitente, destino, asunto, mensaje, referencia=""):
    """Devuelve el id de la tarea nueva, o None si ya existía (evita duplicados)."""
    with _lock, _con() as c:
        try:
            cur = c.execute(
                "INSERT INTO tareas(canal,id_externo,remitente,destino,asunto,mensaje,referencia,"
                "estado,creado,actualizado) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (canal, id_externo, remitente, destino, asunto, mensaje, referencia,
                 "nueva", ahora(), ahora()),
            )
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return None


def obtener(tid):
    with _lock, _con() as c:
        return _dict(c.execute("SELECT * FROM tareas WHERE id=?", (tid,)).fetchone())


def listar(limite=300):
    with _lock, _con() as c:
        return [_dict(r) for r in c.execute(
            "SELECT * FROM tareas ORDER BY id DESC LIMIT ?", (limite,)).fetchall()]


def por_estado(*estados):
    q = ",".join("?" * len(estados))
    with _lock, _con() as c:
        return [_dict(r) for r in c.execute(
            f"SELECT * FROM tareas WHERE estado IN ({q}) ORDER BY id", estados).fetchall()]


def actualizar(tid, **campos):
    campos["actualizado"] = ahora()
    vals = []
    for k, v in campos.items():
        if k in CAMPOS_JSON and not isinstance(v, str) and v is not None:
            v = json.dumps(v, ensure_ascii=False)
        vals.append(v)
    sets = ",".join(f"{k}=?" for k in campos)
    with _lock, _con() as c:
        c.execute(f"UPDATE tareas SET {sets} WHERE id=?", (*vals, tid))


def registrar_memoria(tipo, origen, detalle, datos_extra=None):
    """Guarda eventos, errores, aprendizajes y decisiones en la memoria permanente."""
    extra = json.dumps(datos_extra, ensure_ascii=False) if datos_extra and not isinstance(datos_extra, str) else (datos_extra or "")
    with _lock, _con() as c:
        c.execute("INSERT INTO bitacora_memoria(tipo, origen, detalle, datos_extra, fecha) VALUES(?,?,?,?,?)",
                  (tipo, origen, str(detalle), extra, ahora()))


def obtener_memoria(limite=50, tipo=None):
    with _lock, _con() as c:
        if tipo:
            res = c.execute("SELECT * FROM bitacora_memoria WHERE tipo=? ORDER BY id DESC LIMIT ?", (tipo, limite)).fetchall()
        else:
            res = c.execute("SELECT * FROM bitacora_memoria ORDER BY id DESC LIMIT ?", (limite,)).fetchall()
        return [dict(r) for r in res]


def agregar_turno(chat_id, rol, texto):
    """Guarda un turno de conversación reciente por chat (máx. 24 turnos)."""
    cid = str(chat_id or "panel")
    with _lock, _con() as c:
        c.execute("INSERT INTO conversacion(chat_id, rol, texto, fecha) VALUES(?,?,?,?)",
                  (cid, rol, str(texto)[:3000], ahora()))
        c.execute(
            "DELETE FROM conversacion WHERE chat_id=? AND id NOT IN "
            "(SELECT id FROM conversacion WHERE chat_id=? ORDER BY id DESC LIMIT 24)",
            (cid, cid),
        )


def obtener_historial(chat_id, limite=10):
    cid = str(chat_id or "panel")
    with _lock, _con() as c:
        rows = c.execute(
            "SELECT rol, texto, fecha FROM conversacion WHERE chat_id=? ORDER BY id DESC LIMIT ?",
            (cid, limite),
        ).fetchall()
        return [dict(r) for r in reversed(rows)]


def guardar_modo(chat_id, modo):
    cid = str(chat_id or "panel")
    with _lock, _con() as c:
        c.execute(
            "INSERT INTO estado_chat(chat_id, modo, actualizado) VALUES(?,?,?) "
            "ON CONFLICT(chat_id) DO UPDATE SET modo=excluded.modo, actualizado=excluded.actualizado",
            (cid, (modo or "").strip(), ahora()),
        )


def obtener_modo(chat_id):
    cid = str(chat_id or "panel")
    with _lock, _con() as c:
        r = c.execute("SELECT modo FROM estado_chat WHERE chat_id=?", (cid,)).fetchone()
        return (r["modo"] if r else "") or ""
