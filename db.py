"""Base de datos dual: PostgreSQL en la nube (si existe DATABASE_URL) o SQLite local.
Guarda tareas, bitácora, historial de chat, modo Maestro, recordatorios y estado del briefing."""
from contextlib import contextmanager
import datetime
import json
import sqlite3
import threading

import config

DB_PATH = config.DB_PATH
_ORIGINAL_DB_PATH = config.DB_PATH
_lock = threading.Lock()
CAMPOS_JSON = {"analisis", "resultado", "verificacion"}


def _usa_pg():
    return bool(config.DATABASE_URL) and DB_PATH == _ORIGINAL_DB_PATH


def _dsn():
    dsn = config.DATABASE_URL
    return "postgresql://" + dsn[len("postgres://"):] if dsn.startswith("postgres://") else dsn


def _con():
    """Conexión SQLite directa (mantiene compatibilidad con pruebas locales)."""
    c = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
    c.row_factory = sqlite3.Row
    return c


@contextmanager
def _tx():
    if _usa_pg():
        import psycopg2
        from psycopg2.extras import RealDictCursor
        conn = psycopg2.connect(_dsn(), cursor_factory=RealDictCursor, connect_timeout=10)
        try:
            yield conn, True
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    else:
        conn = _con()
        try:
            yield conn, False
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def _q(sql, pg):
    return sql.replace("?", "%s") if pg else sql


def ahora_dt():
    tz = datetime.timezone(datetime.timedelta(hours=config.ZONA_HORARIA_OFFSET))
    return datetime.datetime.now(tz)


def ahora():
    return ahora_dt().strftime("%Y-%m-%d %H:%M:%S")


def init():
    pk = "SERIAL PRIMARY KEY" if _usa_pg() else "INTEGER PRIMARY KEY AUTOINCREMENT"
    tablas = [
        f"""CREATE TABLE IF NOT EXISTS tareas(
            id {pk},
            canal TEXT, id_externo TEXT, remitente TEXT, destino TEXT,
            asunto TEXT, mensaje TEXT, referencia TEXT,
            estado TEXT, analisis TEXT, resultado TEXT, verificacion TEXT,
            respuesta TEXT, archivo TEXT, error TEXT, instrucciones_extra TEXT,
            creado TEXT, actualizado TEXT,
            UNIQUE(canal, id_externo)
        )""",
        f"""CREATE TABLE IF NOT EXISTS bitacora_memoria(
            id {pk},
            tipo TEXT, origen TEXT, detalle TEXT, datos_extra TEXT, fecha TEXT
        )""",
        f"""CREATE TABLE IF NOT EXISTS conversacion(
            id {pk},
            chat_id TEXT, rol TEXT, texto TEXT, fecha TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS estado_chat(
            chat_id TEXT PRIMARY KEY,
            modo TEXT,
            actualizado TEXT
        )""",
        f"""CREATE TABLE IF NOT EXISTS recordatorios(
            id {pk},
            chat_id TEXT,
            mensaje TEXT,
            vence_en TEXT,
            estado TEXT,
            creado TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS config_kv(
            clave TEXT PRIMARY KEY,
            valor TEXT
        )""",
    ]
    with _lock, _tx() as (c, pg):
        cur = c.cursor()
        for ddl in tablas:
            cur.execute(ddl)


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
    with _lock, _tx() as (c, pg):
        cur = c.cursor()
        ts = ahora()
        vals = (canal, id_externo, remitente, destino, asunto, mensaje, referencia, "nueva", ts, ts)
        if pg:
            cur.execute(
                "INSERT INTO tareas(canal,id_externo,remitente,destino,asunto,mensaje,referencia,"
                "estado,creado,actualizado) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT(canal,id_externo) DO NOTHING RETURNING id",
                vals,
            )
            row = cur.fetchone()
            return row["id"] if row else None
        try:
            cur.execute(
                "INSERT INTO tareas(canal,id_externo,remitente,destino,asunto,mensaje,referencia,"
                "estado,creado,actualizado) VALUES(?,?,?,?,?,?,?,?,?,?)",
                vals,
            )
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return None


def obtener(tid):
    with _lock, _tx() as (c, pg):
        cur = c.cursor()
        cur.execute(_q("SELECT * FROM tareas WHERE id=?", pg), (tid,))
        return _dict(cur.fetchone())


def listar(limite=300):
    with _lock, _tx() as (c, pg):
        cur = c.cursor()
        cur.execute(_q("SELECT * FROM tareas ORDER BY id DESC LIMIT ?", pg), (limite,))
        return [_dict(r) for r in cur.fetchall()]


def por_estado(*estados):
    q = ",".join("?" * len(estados))
    with _lock, _tx() as (c, pg):
        cur = c.cursor()
        cur.execute(_q(f"SELECT * FROM tareas WHERE estado IN ({q}) ORDER BY id", pg), estados)
        return [_dict(r) for r in cur.fetchall()]


def actualizar(tid, **campos):
    campos["actualizado"] = ahora()
    vals = []
    for k, v in campos.items():
        if k in CAMPOS_JSON and not isinstance(v, str) and v is not None:
            v = json.dumps(v, ensure_ascii=False)
        vals.append(v)
    sets = ",".join(f"{k}=?" for k in campos)
    with _lock, _tx() as (c, pg):
        cur = c.cursor()
        cur.execute(_q(f"UPDATE tareas SET {sets} WHERE id=?", pg), (*vals, tid))


def registrar_memoria(tipo, origen, detalle, datos_extra=None):
    """Guarda eventos, errores, aprendizajes y decisiones en la memoria permanente."""
    extra = json.dumps(datos_extra, ensure_ascii=False) if datos_extra and not isinstance(datos_extra, str) else (datos_extra or "")
    with _lock, _tx() as (c, pg):
        cur = c.cursor()
        cur.execute(_q("INSERT INTO bitacora_memoria(tipo, origen, detalle, datos_extra, fecha) VALUES(?,?,?,?,?)", pg),
                    (tipo, origen, str(detalle), extra, ahora()))


def obtener_memoria(limite=50, tipo=None):
    with _lock, _tx() as (c, pg):
        cur = c.cursor()
        if tipo:
            cur.execute(_q("SELECT * FROM bitacora_memoria WHERE tipo=? ORDER BY id DESC LIMIT ?", pg), (tipo, limite))
        else:
            cur.execute(_q("SELECT * FROM bitacora_memoria ORDER BY id DESC LIMIT ?", pg), (limite,))
        return [dict(r) for r in cur.fetchall()]


def agregar_turno(chat_id, rol, texto):
    """Guarda un turno de conversación reciente por chat (máx. 24 turnos)."""
    cid = str(chat_id or "panel")
    with _lock, _tx() as (c, pg):
        cur = c.cursor()
        cur.execute(_q("INSERT INTO conversacion(chat_id, rol, texto, fecha) VALUES(?,?,?,?)", pg),
                    (cid, rol, str(texto)[:3000], ahora()))
        cur.execute(
            _q("DELETE FROM conversacion WHERE chat_id=? AND id NOT IN "
               "(SELECT id FROM conversacion WHERE chat_id=? ORDER BY id DESC LIMIT 24)", pg),
            (cid, cid),
        )


def obtener_historial(chat_id, limite=10):
    cid = str(chat_id or "panel")
    with _lock, _tx() as (c, pg):
        cur = c.cursor()
        cur.execute(_q("SELECT rol, texto, fecha FROM conversacion WHERE chat_id=? ORDER BY id DESC LIMIT ?", pg),
                    (cid, limite))
        return [dict(r) for r in reversed(cur.fetchall())]


def guardar_modo(chat_id, modo):
    cid = str(chat_id or "panel")
    with _lock, _tx() as (c, pg):
        cur = c.cursor()
        cur.execute(
            _q("INSERT INTO estado_chat(chat_id, modo, actualizado) VALUES(?,?,?) "
               "ON CONFLICT(chat_id) DO UPDATE SET modo=excluded.modo, actualizado=excluded.actualizado", pg),
            (cid, (modo or "").strip(), ahora()),
        )


def obtener_modo(chat_id):
    cid = str(chat_id or "panel")
    with _lock, _tx() as (c, pg):
        cur = c.cursor()
        cur.execute(_q("SELECT modo FROM estado_chat WHERE chat_id=?", pg), (cid,))
        r = cur.fetchone()
        return (r["modo"] if r else "") or ""


# ---------------- RECORDATORIOS PERSISTENTES Y CLAVE-VALOR ----------------
def crear_recordatorio(chat_id, mensaje, vence_en):
    cid = str(chat_id or config.TELEGRAM_CHAT_DUENO or "panel")
    with _lock, _tx() as (c, pg):
        cur = c.cursor()
        vals = (cid, mensaje, vence_en, "pendiente", ahora())
        if pg:
            cur.execute(
                "INSERT INTO recordatorios(chat_id,mensaje,vence_en,estado,creado) "
                "VALUES(%s,%s,%s,%s,%s) RETURNING id",
                vals,
            )
            return cur.fetchone()["id"]
        cur.execute("INSERT INTO recordatorios(chat_id,mensaje,vence_en,estado,creado) VALUES(?,?,?,?,?)", vals)
        return cur.lastrowid


def recordatorios_vencidos(ahora_str=None):
    ref = ahora_str or ahora()
    with _lock, _tx() as (c, pg):
        cur = c.cursor()
        cur.execute(
            _q("SELECT * FROM recordatorios WHERE estado='pendiente' AND vence_en<=? ORDER BY vence_en", pg),
            (ref,),
        )
        return [dict(r) for r in cur.fetchall()]


def listar_recordatorios(chat_id=None):
    with _lock, _tx() as (c, pg):
        cur = c.cursor()
        if chat_id:
            cur.execute(
                _q("SELECT * FROM recordatorios WHERE estado='pendiente' AND chat_id=? ORDER BY vence_en", pg),
                (str(chat_id),),
            )
        else:
            cur.execute("SELECT * FROM recordatorios WHERE estado='pendiente' ORDER BY vence_en")
        return [dict(r) for r in cur.fetchall()]


def marcar_recordatorio(rid, estado="enviado"):
    with _lock, _tx() as (c, pg):
        cur = c.cursor()
        cur.execute(_q("UPDATE recordatorios SET estado=? WHERE id=?", pg), (estado, int(rid)))


def obtener_kv(clave, defecto=""):
    with _lock, _tx() as (c, pg):
        cur = c.cursor()
        cur.execute(_q("SELECT valor FROM config_kv WHERE clave=?", pg), (clave,))
        r = cur.fetchone()
        return r["valor"] if r else defecto


def guardar_kv(clave, valor):
    with _lock, _tx() as (c, pg):
        cur = c.cursor()
        cur.execute(
            _q("INSERT INTO config_kv(clave, valor) VALUES(?,?) "
               "ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor", pg),
            (clave, str(valor)),
        )
