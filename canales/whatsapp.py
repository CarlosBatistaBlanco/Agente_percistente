"""Canal WhatsApp vía WhatsApp Business Cloud API (Meta).
Recibe mensajes por webhook (/webhook/whatsapp) y responde con texto y documentos."""
import mimetypes
import os

import requests
from flask import Blueprint, request

import config
from ejecutores import extraer_texto

GRAPH = "https://graph.facebook.com/v20.0"


def _h():
    return {"Authorization": f"Bearer {config.WHATSAPP_TOKEN}"}


def _descargar(media_id):
    info = requests.get(f"{GRAPH}/{media_id}", headers=_h(), timeout=30).json()
    return requests.get(info["url"], headers=_h(), timeout=60).content


def crear_blueprint(registrar):
    bp = Blueprint("whatsapp", __name__)

    @bp.get("/webhook/whatsapp")
    def verificar():
        if request.args.get("hub.verify_token") == config.WHATSAPP_VERIFY_TOKEN:
            return request.args.get("hub.challenge", "")
        return "token inválido", 403

    @bp.post("/webhook/whatsapp")
    def recibir():
        data = request.get_json(silent=True) or {}
        for entry in data.get("entry", []):
            for ch in entry.get("changes", []):
                valor = ch.get("value", {})
                nombres = {c.get("wa_id"): c.get("profile", {}).get("name", "")
                           for c in valor.get("contacts", [])}
                for m in valor.get("messages", []):
                    numero = m.get("from", "")
                    permitidos = config.WHATSAPP_NUMEROS_PERMITIDOS
                    if permitidos and numero not in permitidos:
                        continue
                    tipo, texto = m.get("type"), ""
                    if tipo == "text":
                        texto = m["text"]["body"]
                    elif tipo == "document":
                        d = m["document"]
                        texto = d.get("caption", "")
                        try:
                            texto += "\n\n" + extraer_texto(d.get("filename", "archivo"),
                                                            _descargar(d["id"]))
                        except Exception as e:
                            texto += f"\n[No se pudo descargar el adjunto: {e}]"
                    if not texto.strip():
                        continue
                    registrar("whatsapp", m["id"],
                              f"{nombres.get(numero, '')} (WhatsApp +{numero})", numero,
                              "Mensaje de WhatsApp", texto, m["id"])
        return "ok", 200

    return bp


def enviar(numero, texto, archivo="", referencia=""):
    url = f"{GRAPH}/{config.WHATSAPP_PHONE_ID}/messages"
    cuerpo = {"messaging_product": "whatsapp", "to": numero, "type": "text",
              "text": {"body": texto[:4096]}}
    if referencia:
        cuerpo["context"] = {"message_id": referencia}
    r = requests.post(url, headers=_h(), json=cuerpo, timeout=30)
    if not r.ok:
        raise RuntimeError(f"WhatsApp: {r.text}")
    if archivo and os.path.exists(archivo):
        mime = mimetypes.guess_type(archivo)[0] or "application/octet-stream"
        nombre = os.path.basename(archivo).split("_", 1)[-1]
        with open(archivo, "rb") as f:
            up = requests.post(f"{GRAPH}/{config.WHATSAPP_PHONE_ID}/media", headers=_h(),
                               data={"messaging_product": "whatsapp", "type": mime},
                               files={"file": (nombre, f, mime)}, timeout=120)
        if not up.ok:
            raise RuntimeError(f"WhatsApp media: {up.text}")
        r = requests.post(url, headers=_h(), timeout=30, json={
            "messaging_product": "whatsapp", "to": numero, "type": "document",
            "document": {"id": up.json()["id"], "filename": nombre}})
        if not r.ok:
            raise RuntimeError(f"WhatsApp: {r.text}")
