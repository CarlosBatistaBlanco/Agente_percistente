"""ASISTENTE DE CONFIGURACIÓN
Te guía paso a paso para conectar Gemini y Telegram, y guarda todo en el archivo .env.
Ejecutar con:  configurar.bat
"""
import os
import shutil
import time

import requests

BASE = os.path.dirname(os.path.abspath(__file__))
ENV = os.path.join(BASE, ".env")


def leer_env():
    if not os.path.exists(ENV):
        shutil.copy(os.path.join(BASE, ".env.example"), ENV)
    datos = {}
    for linea in open(ENV, encoding="utf-8"):
        if "=" in linea and not linea.strip().startswith("#"):
            k, v = linea.split("=", 1)
            datos[k.strip()] = v.strip()
    return datos


def guardar_env(cambios):
    lineas = open(ENV, encoding="utf-8").read().splitlines()
    pendientes = dict(cambios)
    for i, linea in enumerate(lineas):
        k = linea.split("=", 1)[0].strip()
        if "=" in linea and not linea.strip().startswith("#") and k in pendientes:
            lineas[i] = f"{k}={pendientes.pop(k)}"
    lineas += [f"{k}={v}" for k, v in pendientes.items()]
    open(ENV, "w", encoding="utf-8").write("\n".join(lineas) + "\n")


def titulo(t):
    print("\n" + "=" * 60 + f"\n  {t}\n" + "=" * 60)


def paso_gemini(env):
    titulo("PASO 1 de 3 · Cerebro del agente (Gemini)")
    if env.get("GEMINI_API_KEY"):
        print("✔ Ya tienes una clave de Gemini guardada.")
        if input("¿Quieres cambiarla? (s/N): ").strip().lower() != "s":
            return
    print("1. Abre https://aistudio.google.com/apikey (inicia sesión con tu cuenta de Google)")
    print("2. Presiona 'Create API key' y cópiala.")
    while True:
        clave = input("\nPega aquí tu clave de Gemini: ").strip()
        if not clave:
            print("(omitido)")
            return
        r = requests.get("https://generativelanguage.googleapis.com/v1beta/models",
                         params={"key": clave}, timeout=30)
        if r.ok:
            guardar_env({"GEMINI_API_KEY": clave})
            print("✔ Clave válida y guardada.")
            return
        print(f"✘ La clave no funcionó ({r.status_code}). Revisa que la copiaste completa.")


def paso_datos(env):
    titulo("PASO 2 de 3 · ¿Quién eres?")
    nombre = input(f"Tu nombre (como firmará el agente) [{env.get('TU_NOMBRE', '')}]: ").strip()
    contexto = input("Describe tu trabajo en una línea (puesto, empresa, tono, moneda)\n> ").strip()
    cambios = {}
    if nombre:
        cambios["TU_NOMBRE"] = nombre
    if contexto:
        cambios["CONTEXTO_PERSONAL"] = contexto
    if cambios:
        guardar_env(cambios)
        print("✔ Guardado.")


def paso_telegram(env):
    titulo("PASO 3 de 3 · Conectar Telegram")
    print("""1. Abre Telegram (celular o PC) y busca:  @BotFather   (tiene palomita azul ✔)
2. Escríbele:  /newbot
3. Te pide un NOMBRE (ej. "Mi Asistente")  y luego un USUARIO que termine en 'bot'
   (ej. "mi_asistente_juan_bot").
4. BotFather te responde con un TOKEN parecido a:
   123456789:AAH4k...xYz   <- cópialo completo""")
    while True:
        token = input("\nPega aquí el TOKEN de tu bot: ").strip()
        if not token:
            print("(omitido)")
            return
        r = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=30).json()
        if r.get("ok"):
            break
        print("✘ Ese token no funciona. Cópialo de nuevo desde BotFather.")
    bot = r["result"]["username"]
    print(f"✔ Bot encontrado: @{bot}")
    print(f"\n5. Ahora abre este enlace y presiona INICIAR (o escribe /start):\n   https://t.me/{bot}")
    print("\nEsperando tu mensaje (hasta 3 minutos)...")

    requests.get(f"https://api.telegram.org/bot{token}/deleteWebhook", timeout=30)
    offset, fin, chat_id, nombre = 0, time.time() + 180, None, ""
    while time.time() < fin and not chat_id:
        u = requests.get(f"https://api.telegram.org/bot{token}/getUpdates",
                         params={"offset": offset, "timeout": 20}, timeout=30).json()
        for x in u.get("result", []):
            offset = x["update_id"] + 1
            m = x.get("message")
            if m:
                chat_id = str(m["chat"]["id"])
                nombre = m["from"].get("first_name", "")
    # Confirma los mensajes leídos para que el agente no los procese como tareas
    requests.get(f"https://api.telegram.org/bot{token}/getUpdates", params={"offset": offset}, timeout=30)
    if not chat_id:
        print("✘ No recibí tu mensaje. Vuelve a ejecutar configurar.bat e inténtalo de nuevo.")
        guardar_env({"TELEGRAM_BOT_TOKEN": token})
        return
    guardar_env({"TELEGRAM_ACTIVO": "true", "TELEGRAM_BOT_TOKEN": token,
                 "TELEGRAM_CHAT_DUENO": chat_id})
    requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={
        "chat_id": chat_id,
        "text": f"✅ ¡Listo {nombre}! Quedé conectado como tu asistente.\n"
                "Cuando inicies el agente podrás hablarme con notas de voz 🎤 o escribirme."}, timeout=30)
    requests.post(f"https://api.telegram.org/bot{token}/setMyCommands", json={"commands": [
        {"command": "pendientes", "description": "Ver tareas pendientes"},
        {"command": "ver", "description": "Ver una tarea: /ver 3"},
        {"command": "aprobar", "description": "Aprobar una tarea: /aprobar 3"},
        {"command": "rechazar", "description": "Rechazar una tarea: /rechazar 3"},
        {"command": "ayuda", "description": "Qué puedo hacer"}]}, timeout=30)
    print(f"✔ Telegram conectado. Tu chat_id es {chat_id} (eres el DUEÑO del bot).")


if __name__ == "__main__":
    print("🤖 Configuración del Agente de Tareas")
    env = leer_env()
    paso_gemini(env)
    paso_datos(leer_env())
    paso_telegram(leer_env())
    titulo("¡Terminado!")
    print("Ahora abre  iniciar.bat  para encender el agente.\n"
          "En Telegram mándale una nota de voz como: \"¿qué puedes hacer?\"")
    input("\nPresiona Enter para salir...")
