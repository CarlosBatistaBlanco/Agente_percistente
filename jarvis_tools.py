"""Herramientas de J.A.R.V.I.S.:
1. Búsqueda web en vivo (DuckDuckGo)
2. Control y automatización de Windows (abrir apps, bloquear, carpetas)
3. Diagnóstico y telemetría de hardware (CPU, RAM, Batería, Disco)
"""
import os
import subprocess
import psutil
from duckduckgo_search import DDGS

import db


# ---------------- 1. BÚSQUEDA WEB EN TIEMPO REAL ----------------
def buscar_web(consulta, max_resultados=4):
    """Realiza una búsqueda web rápida en tiempo real."""
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            resultados = list(ddgs.text(consulta, max_results=max_resultados))
            if resultados:
                lineas = [f"• {r.get('title')}: {r.get('body')} ({r.get('href')})" for r in resultados]
                res_str = "\n".join(lineas)
                db.registrar_memoria("busqueda_web", "jarvis_tools", consulta, {"resultados": len(resultados)})
                return res_str
    except Exception:
        pass

    # Respaldo rápido con duckduckgo html
    try:
        import requests
        import re
        r = requests.get("https://html.duckduckgo.com/html/", params={"q": consulta}, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        snippets = re.findall(r'<a class="result__snippet[^>]*>(.*?)</a>', r.text, re.DOTALL)
        if snippets:
            limpios = [re.sub(r'<[^>]+>', '', s).strip() for s in snippets[:max_resultados]]
            return "\n".join(f"• {s}" for s in limpios)
    except Exception as e:
        return f"Interferencia al conectar con los satélites de información: {e}"

    return "No se localizaron registros recientes en la red para esa consulta, señor."


# ---------------- 2. DIAGNÓSTICO DEL SISTEMA ----------------
def diagnostico_sistema():
    """Reporte de estado de la laptop (batería, CPU, RAM y disco)."""
    try:
        cpu = psutil.cpu_percent(interval=0.5)
        ram = psutil.virtual_memory()
        disco = psutil.disk_usage("C:\\")
        bateria = psutil.sensors_battery()

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


# ---------------- 5. TEMPORIZADORES / ALARMAS ----------------
def crear_temporizador(segundos, mensaje, chat_id=None):
    """Programa una alarma en segundo plano para avisar en Telegram o Windows."""
    import threading
    import time
    from canales import telegram

    def _hilo():
        time.sleep(segundos)
        minutos = segundos // 60
        txt = f"⏰ ALERTA TEMPORIZADA, señor:\n{mensaje} (Transcurrieron {minutos if minutos else segundos} {'minutos' if minutos else 'segundos'})."
        if chat_id:
            try:
                telegram.enviar(chat_id, txt)
                telegram.enviar_voz(chat_id, f"Señor, recordatorio: {mensaje}")
            except Exception:
                pass
        # Notificación sonora en Windows
        try:
            import winsound
            winsound.Beep(1000, 800)
        except Exception:
            pass

    threading.Thread(target=_hilo, daemon=True).start()
    return f"Temporizador sincronizado para dentro de {segundos//60 if segundos>=60 else segundos} {'minutos' if segundos>=60 else 'segundos'}, señor: '{mensaje}'."
