"""Configuración del agente. Todo se lee del archivo .env"""
import os
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))


def _b(nombre, defecto="false"):
    return os.getenv(nombre, defecto).strip().lower() in ("1", "true", "si", "sí", "yes")


def _lista(nombre):
    return [x.strip().lower() for x in os.getenv(nombre, "").split(",") if x.strip()]


# --- IA (Gemini) ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODELO = os.getenv("GEMINI_MODELO", "gemini-3.5-flash-lite")

# --- Quién eres (para que el agente actúe en tu nombre correctamente) ---
TU_NOMBRE = os.getenv("TU_NOMBRE", "el usuario")
CONTEXTO_PERSONAL = os.getenv("CONTEXTO_PERSONAL", "")

# --- Calidad ---
CONFIANZA_MINIMA = int(os.getenv("CONFIANZA_MINIMA", "70"))
MAX_REINTENTOS = int(os.getenv("MAX_REINTENTOS", "2"))

# --- Correo (Gmail / Outlook por IMAP + SMTP) ---
CORREO_ACTIVO = _b("CORREO_ACTIVO")
IMAP_HOST = os.getenv("IMAP_HOST", "imap.gmail.com")
IMAP_PORT = int(os.getenv("IMAP_PORT", "993"))
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
CORREO_USUARIO = os.getenv("CORREO_USUARIO", "")
CORREO_PASSWORD = os.getenv("CORREO_PASSWORD", "")
CORREO_REMITENTES_PERMITIDOS = _lista("CORREO_REMITENTES_PERMITIDOS")
CORREO_IGNORAR_BOLETINES = _b("CORREO_IGNORAR_BOLETINES", "true")

# --- Telegram (bot) ---
TELEGRAM_ACTIVO = _b("TELEGRAM_ACTIVO")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHATS_PERMITIDOS = _lista("TELEGRAM_CHATS_PERMITIDOS")
TELEGRAM_CHAT_DUENO = os.getenv("TELEGRAM_CHAT_DUENO", "").strip()

# --- MODO J.A.R.V.I.S. ---
NOMBRE_ASISTENTE = os.getenv("NOMBRE_ASISTENTE", "Jarvis")  # Palabra de activación
VOZ_MODELO = os.getenv("VOZ_MODELO", "Fenrir")              # Fenrir (grave/británico), Puck, Charon, Kore, Aoede
VOZ_RESPUESTAS = _b("VOZ_RESPUESTAS", "true")
VOZ_ACENTO = os.getenv("VOZ_ACENTO", "com.mx")
VOZ_IDIOMA_PANEL = os.getenv("VOZ_IDIOMA_PANEL", "es-MX")

# --- WhatsApp (WhatsApp Business Cloud API de Meta) ---
WHATSAPP_ACTIVO = _b("WHATSAPP_ACTIVO")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
WHATSAPP_PHONE_ID = os.getenv("WHATSAPP_PHONE_ID", "")
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "mi_token_secreto")
WHATSAPP_NUMEROS_PERMITIDOS = _lista("WHATSAPP_NUMEROS_PERMITIDOS")

# --- Panel y ciclo ---
INTERVALO_SEGUNDOS = int(os.getenv("INTERVALO_SEGUNDOS", "60"))
PANEL_PUERTO = int(os.getenv("PORT", os.getenv("PANEL_PUERTO", "5000")))
PANEL_HOST = os.getenv("PANEL_HOST", "0.0.0.0" if os.getenv("PORT") else "127.0.0.1")
PANEL_URL = os.getenv("PANEL_URL", f"http://{PANEL_HOST}:{PANEL_PUERTO}")
PANEL_USUARIO = os.getenv("PANEL_USUARIO", "admin")
PANEL_CLAVE = os.getenv("PANEL_CLAVE", "")

SALIDAS_DIR = os.path.join(BASE_DIR, "salidas")
DB_PATH = os.path.join(BASE_DIR, "tareas.db")
os.makedirs(SALIDAS_DIR, exist_ok=True)
