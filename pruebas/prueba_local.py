"""Prueba sin IA ni canales: genera Excel/Word, lee adjuntos y renderiza el panel."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
config.DB_PATH = os.path.join(config.BASE_DIR, "prueba.db")
import db, ejecutores  # noqa: E402,E401
from panel import crear_app  # noqa: E402

db.DB_PATH = config.DB_PATH
db.init()
xl = ejecutores.crear_excel({"hojas": [{"nombre": "Presupuesto", "encabezados": ["Concepto", "Monto"],
                                        "filas": [["A", "100"], ["B", 50.5], ["Total", "=SUM(B2:B3)"]]}]},
                            "presupuesto prueba", 0)
wd = ejecutores.crear_word({"titulo": "Informe", "secciones": [{"titulo": "Intro", "parrafos": ["Hola"],
                           "vinetas": ["uno"], "tabla": {"encabezados": ["a", "b"], "filas": [[1, 2]]}}]},
                           "informe", 0)
print(ejecutores.extraer_texto("x.xlsx", open(xl, "rb").read())[:120])
print(ejecutores.extraer_texto("x.docx", open(wd, "rb").read())[:120])

tid = db.crear("manual", "t_smoke", "Yo", "", "Prueba", "Hazme un presupuesto")
if not tid:
    row = db._con().execute("SELECT id FROM tareas WHERE canal='manual' AND id_externo='t_smoke'").fetchone()
    tid = row["id"]
db.actualizar(tid, estado="pendiente_revision", respuesta="Listo", archivo=xl,
              analisis={"resumen_tarea": "Presupuesto", "requisitos": ["2 conceptos"], "confianza": 90},
              verificacion={"cumple": True, "puntuacion": 95,
                            "requisitos": [{"requisito": "2 conceptos", "cumplido": True, "nota": ""}]})
import queue  # noqa: E402
import asistente  # noqa: E402
cola = queue.Queue()
comando = lambda texto, origen="panel", chat_id="": asistente.ejecutar(  # noqa: E731
    texto, origen, cola, lambda *a, **k: 1, chat_id)
c = crear_app(cola, lambda *a: None, lambda *a, **k: 1, comando).test_client()
for url in ["/", f"/tarea/{tid}", f"/tarea/{tid}/archivo"]:
    r = c.get(url)
    print(url, r.status_code)
    assert r.status_code == 200
assert b'id="mic"' in c.get("/").data
for orden in ["/pendientes", f"/ver {tid}", f"/aprobar {tid}", f"/rechazar {tid}"]:
    r = c.post("/voz", json={"texto": orden}).get_json()
    print(orden, "->", r["texto"][:70].replace("\n", " "))
assert db.obtener(tid)["estado"] == "pendiente_revision"   # aprobar/rechazar solo piden confirmación
from gtts import gTTS  # noqa: E402
gTTS("Prueba de voz del agente", lang="es", tld="com.mx").save(os.path.join(config.BASE_DIR, "voz_prueba.mp3"))
print("voz mp3:", os.path.getsize(os.path.join(config.BASE_DIR, "voz_prueba.mp3")), "bytes")
os.remove(os.path.join(config.BASE_DIR, "voz_prueba.mp3"))
for f in (xl, wd, config.DB_PATH):
    try:
        os.remove(f)
    except OSError:
        pass
print("TODO OK")
