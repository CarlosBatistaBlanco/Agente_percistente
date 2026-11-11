"""Herramientas de J.A.R.V.I.S.:
1. Búsqueda web en vivo (DuckDuckGo)
2. Control y automatización de Windows (abrir apps, bloquear, carpetas)
3. Diagnóstico y telemetría de hardware (CPU, RAM, Batería, Disco)
"""
import os
import subprocess
import psutil

import db


# ---------------- 1. BÚSQUEDA WEB Y ACCESO A INFORMACIÓN EN TIEMPO REAL ----------------
def _buscar_wiki(consulta):
    import re
    import requests
    r = requests.get(
        "https://es.wikipedia.org/w/api.php",
        params={"action": "query", "list": "search", "srsearch": consulta,
                "srlimit": 3, "format": "json", "utf8": 1},
        headers={"User-Agent": "JarvisAgent/1.0"},
        timeout=4,
    )
    items = (r.json().get("query") or {}).get("search") or []
    out = []
    for it in items:
        snip = re.sub(r"<[^>]+>", "", it.get("snippet", "")).strip()
        titulo = it.get("title", "")
        url = "https://es.wikipedia.org/wiki/" + titulo.replace(" ", "_")
        out.append(f"• [Wikipedia] {titulo}: {snip} ({url})")
    return out


def _buscar_gnews(consulta):
    import re
    import xml.etree.ElementTree as ET
    import requests
    r = requests.get(
        "https://news.google.com/rss/search",
        params={"q": consulta, "hl": "es-419", "gl": "MX", "ceid": "MX:es-419"},
        headers={"User-Agent": "JarvisAgent/1.0"},
        timeout=4,
    )
    root = ET.fromstring(r.content)
    out = []
    for item in root.findall("./channel/item")[:4]:
        titulo = (item.findtext("title") or "").strip()
        fecha = (item.findtext("pubDate") or "")[:16]
        link = (item.findtext("link") or "").strip()
        if titulo:
            out.append(f"• [Noticia {fecha}] {re.sub(r'<[^>]+>', '', titulo)} ({link})")
    return out


def _buscar_ddg(consulta, max_resultados=4):
    try:
        from ddgs import DDGS
        with DDGS(timeout=4) as ddgs:
            res = list(ddgs.text(consulta, max_results=max_resultados))
            return [f"• {r.get('title')}: {r.get('body')} ({r.get('href')})" for r in res if r.get("title")]
    except Exception:
        return []


def buscar_web(consulta, max_resultados=6):
    """Búsqueda web paralela ultrarrápida (Wikipedia + Google News + DuckDuckGo)."""
    from concurrent.futures import ThreadPoolExecutor
    lineas = []
    with ThreadPoolExecutor(max_workers=3) as ex:
        futs = [
            ex.submit(_buscar_ddg, consulta, 4),
            ex.submit(_buscar_wiki, consulta),
            ex.submit(_buscar_gnews, consulta),
        ]
        for f in futs:
            try:
                lineas.extend(f.result(timeout=4.5))
            except Exception:
                pass
    if lineas:
        db.registrar_memoria("busqueda_web", "jarvis_tools", consulta, {"resultados": len(lineas)})
        return "\n".join(lineas[:max_resultados * 2])
    return "No se localizaron registros en vivo para esa consulta."


def leer_url(url, max_chars=4500):
    """Descarga y extrae el texto limpio de cualquier página web pública."""
    import html
    import re
    import requests
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=6)
        r.raise_for_status()
        txt = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", r.text, flags=re.S | re.I)
        txt = re.sub(r"<[^>]+>", " ", txt)
        txt = re.sub(r"\s+", " ", html.unescape(txt)).strip()
        return txt[:max_chars] or "La página no devolvió texto legible."
    except Exception as e:
        return f"No pude leer {url}: {e}"


def investigar(consulta):
    """Busca en la web en paralelo y, si viene una URL, extrae su contenido completo."""
    import re
    m_url = re.search(r"https?://\S+", consulta)
    if m_url:
        url = m_url.group(0).rstrip(".,);]")
        return f"[CONTENIDO DE {url}]\n" + leer_url(url)
    return buscar_web(consulta, max_resultados=6)


# ---------------- 2. DIAGNÓSTICO DEL SISTEMA ----------------
def diagnostico_sistema():
    """Reporte de estado de la laptop (batería, CPU, RAM y disco)."""
    try:
        cpu = psutil.cpu_percent(interval=0.5)
        ram = psutil.virtual_memory()
        raiz = "C:\\" if os.name == "nt" else "/"
        disco = psutil.disk_usage(raiz)
        bateria = psutil.sensors_battery() if hasattr(psutil, "sensors_battery") else None

        bat_str = "No detectada (PC de escritorio o sin sensor)"
        if bateria:
            estado_bat = "conectada a la corriente" if bateria.power_plugged else "usando batería"
            bat_str = f"{bateria.percent}% ({estado_bat})"

        info = (
            f"Diagnóstico de sistemas en línea, señor:\n"
            f"• CPU en uso: {cpu}%\n"
            f"• Memoria RAM: {ram.percent}% (Libre: {ram.available // (1024**2)} MB)\n"
            f"• Disco C: {disco.percent}% ocupado (Libre: {disco.free // (1024**3)} GB)\n"
            f"• Batería: {bat_str}"
        )
        db.registrar_memoria("telemetria", "jarvis_tools", "Diagnóstico solicitado", {"cpu": cpu, "ram": ram.percent})
        return info
    except Exception as e:
        return f"Error al recopilar telemetría de los sensores: {e}"


# ---------------- 3. CONTROL DE PC (WINDOWS) ----------------
def ejecutar_comando_pc(accion, parametro=""):
    """Ejecuta acciones seguras en Windows (abrir apps, bloquear, etc.)."""
    accion = accion.lower().strip()
    try:
        if "bloquear" in accion:
            subprocess.run("rundll32.exe user32.dll,LockWorkStation", shell=True)
            return "Bloqueando la estación de trabajo de inmediato, señor."

        elif "excel" in accion:
            subprocess.Popen("start excel", shell=True)
            return "Iniciando Microsoft Excel, señor."

        elif "word" in accion:
            subprocess.Popen("start winword", shell=True)
            return "Iniciando Microsoft Word, señor."

        elif "navegador" in accion or "chrome" in accion:
            subprocess.Popen("start chrome", shell=True)
            return "Abriendo el navegador principal, señor."

        elif "calc" in accion or "calculadora" in accion:
            subprocess.Popen("calc", shell=True)
            return "Calculadora desplegada en pantalla, señor."

        elif "vscode" in accion or "codigo" in accion:
            subprocess.Popen('code "C:\\Users\\X1605ZA-MB013W\\.gemini\\antigravity\\scratch\\agente-tareas"', shell=True)
            return "Desplegando Visual Studio Code con el código del agente, señor."

        elif "papelera" in accion or "limpieza" in accion:
            subprocess.run("PowerShell.exe -NoProfile -Command Clear-RecycleBin -Force -ErrorAction SilentlyContinue", shell=True)
            return "Protocolo de saneamiento completado: Papelera de reciclaje vaciada, señor."

        elif "abrir_app" in accion and parametro:
            subprocess.Popen(f"start {parametro}", shell=True)
            return f"Ejecutando {parametro}, señor."

        return f"Acción de control '{accion}' no reconocida o fuera de protocolos seguros, señor."
    except Exception as e:
        db.registrar_memoria("error", "control_pc", str(e), {"accion": accion})
        return f"No pude completar la acción en Windows: {e}"


# ---------------- 4. CAPTURA Y VISIÓN DE PANTALLA ----------------
def capturar_pantalla():
    """Captura la pantalla actual de Windows y devuelve la ruta del archivo."""
    from PIL import ImageGrab
    import tempfile
    ruta = os.path.join(tempfile.gettempdir(), "jarvis_captura.png")
    img = ImageGrab.grab()
    img.save(ruta, "PNG")
    db.registrar_memoria("vision", "jarvis_tools", "Captura de pantalla tomada", {"ruta": ruta})
    return ruta


# ---------------- 5. RECORDATORIOS PERSISTENTES Y BRIEFING DIARIO ----------------
def crear_temporizador(segundos, mensaje, chat_id=None):
    """Guarda un recordatorio persistente en BD (sobreviendo reinicios de Render)."""
    import datetime
    import config
    cid = str(chat_id or config.TELEGRAM_CHAT_DUENO or "panel")
    vence_dt = db.ahora_dt() + datetime.timedelta(seconds=int(segundos))
    vence_str = vence_dt.strftime("%Y-%m-%d %H:%M:%S")
    rid = db.crear_recordatorio(cid, mensaje, vence_str)
    unidad = "minutos" if segundos >= 60 else "segundos"
    cant = segundos // 60 if segundos >= 60 else segundos
    return f"⏰ Recordatorio #{rid} guardado para las {vence_dt.strftime('%H:%M')} (en {cant} {unidad}), señor: «{mensaje}»."


def crear_recordatorio_hora(hora, minuto, mensaje, manana=False, chat_id=None):
    """Programa un recordatorio persistente a una hora exacta HH:MM (hoy o mañana)."""
    import datetime
    import config
    cid = str(chat_id or config.TELEGRAM_CHAT_DUENO or "panel")
    ahora = db.ahora_dt()
    objetivo = ahora.replace(hour=hora, minute=minuto, second=0, microsecond=0)
    if manana or objetivo <= ahora:
        objetivo += datetime.timedelta(days=1)
    vence_str = objetivo.strftime("%Y-%m-%d %H:%M:%S")
    rid = db.crear_recordatorio(cid, mensaje, vence_str)
    dia = "mañana" if objetivo.date() > ahora.date() else "hoy"
    return f"⏰ Recordatorio #{rid} programado para {dia} a las {objetivo.strftime('%H:%M')}, señor: «{mensaje}»."


def listar_recordatorios(chat_id=None):
    recs = db.listar_recordatorios(chat_id)
    if not recs:
        return "No tiene recordatorios pendientes en agenda, señor."
    lineas = [f"• #{r['id']} [{r['vence_en'][:16]}] — {r['mensaje']}" for r in recs]
    return "Recordatorios activos, señor:\n" + "\n".join(lineas)


def cancelar_recordatorio(rid):
    db.marcar_recordatorio(rid, "cancelado")
    return f"Recordatorio #{rid} cancelado, señor."


def generar_briefing(chat_id=None):
    """Genera el resumen ejecutivo diario (pendientes, recordatorios, clima y noticias)."""
    import config
    cid = str(chat_id or config.TELEGRAM_CHAT_DUENO or "panel")
    ahora = db.ahora_dt()
    pendientes = db.por_estado("pendiente_revision", "necesita_aclaracion", "error")
    recs = db.listar_recordatorios(cid)
    modo = db.obtener_modo(cid)

    partes = [f"☀️ Buenos días, {config.TU_NOMBRE}. Briefing J.A.R.V.I.S. ({ahora.strftime('%d/%m/%Y %H:%M')}):"]
    partes.append(f"\n📌 Tareas pendientes de revisión: {len(pendientes)}")
    for t in pendientes[:5]:
        res = (t.get("analisis") or {}).get("resumen_tarea") or t.get("asunto") or ""
        partes.append(f"  • #{t['id']} ({t['canal']}): {res[:70]}")

    partes.append(f"\n⏰ Recordatorios activos: {len(recs)}")
    for r in recs[:5]:
        partes.append(f"  • #{r['id']} [{r['vence_en'][11:16]}]: {r['mensaje']}")

    if modo:
        partes.append(f"\n🎓 Modo Maestro activo: {modo} (escríbeme «dame mi clase de hoy» para continuar).")

    if config.BRIEFING_CIUDAD:
        try:
            import requests
            w = requests.get(f"https://wttr.in/{config.BRIEFING_CIUDAD}?format=3&lang=es", timeout=4)
            if w.ok and w.text.strip():
                partes.append(f"\n🌤️ Clima: {w.text.strip()}")
        except Exception:
            pass

    try:
        noticias = _buscar_gnews("tecnologia inteligencia artificial mundo")[:3]
        if noticias:
            partes.append("\n📰 Titulares del día:")
            partes.extend("  " + n for n in noticias)
    except Exception:
        pass

    return "\n".join(partes)
