"""Canal Telegram (bot).
- Mensajes/notas de voz de otras personas  -> se vuelven TAREAS.
- Mensajes/notas de voz TUYOS (el dueño)    -> son ÓRDENES para el asistente.
- Mensajes que tú REENVÍAS al bot           -> se vuelven TAREAS.
- Te avisa con botones Aprobar/Rechazar y te puede contestar con voz."""
import os
import tempfile

import requests

import config
import ia
from ejecutores import extraer_texto

_offset = 0
SOLICITUDES_PENDIENTES = set()


def _api(metodo):
    return f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/{metodo}"


def _descargar(file_id):
    r = requests.get(_api("getFile"), params={"file_id": file_id}, timeout=30).json()
    ruta = r["result"]["file_path"]
    url = f"https://api.telegram.org/file/bot{config.TELEGRAM_BOT_TOKEN}/{ruta}"
    return requests.get(url, timeout=60).content


def accion_escribiendo(chat_id, accion="typing"):
    try:
        requests.post(_api("sendChatAction"), json={"chat_id": chat_id, "action": accion}, timeout=10)
    except Exception:
        pass


def revisar():
    """Devuelve (mensajes_nuevos, acciones_de_botones)."""
    global _offset
    try:
        r = requests.get(_api("getUpdates"), params={"offset": _offset, "timeout": 15},
                         timeout=25).json()
    except requests.exceptions.Timeout:
        return [], []
    mensajes, acciones = [], []
    for u in r.get("result", []):
        _offset = u["update_id"] + 1
        if "callback_query" in u:
            cq = u["callback_query"]
            if str(cq["from"]["id"]) == config.TELEGRAM_CHAT_DUENO:
                acciones.append({"id_callback": cq["id"], "data": cq.get("data", ""),
                                 "chat_id": str(cq["message"]["chat"]["id"])})
            continue
        m = u.get("message")
        if not m:
            continue
        chat_id = str(m["chat"]["id"])
        usuario = (m.get("from", {}).get("username") or "").lower()
        es_dueno = chat_id == config.TELEGRAM_CHAT_DUENO
        reenviado = bool(m.get("forward_origin") or m.get("forward_from") or m.get("forward_sender_name"))
        nombre_remitente = " ".join(filter(None, [m.get("from", {}).get("first_name"),
                                                  m.get("from", {}).get("last_name")])) or usuario or chat_id

        texto = m.get("text") or m.get("caption") or ""

        # Notas de voz / audios -> texto
        es_voz = False
        transcrito = ""
        audio = m.get("voice") or m.get("audio") or m.get("video_note")
        if audio:
            es_voz = True
            accion_escribiendo(chat_id)
            try:
                mime = audio.get("mime_type") or ("video/mp4" if "video_note" in m else "audio/ogg")
                transcrito = ia.transcribir(_descargar(audio["file_id"]), mime)
                texto = (texto + "\n" if texto else "") + transcrito
            except Exception as e:
                enviar(chat_id, f"No pude entender el audio: {e}"[:300])
                continue

        imagen_bytes = b""
        if "photo" in m and es_dueno and not reenviado:
            accion_escribiendo(chat_id)
            try:
                imagen_bytes = _descargar(m["photo"][-1]["file_id"])
            except Exception as e:
                enviar(chat_id, f"No pude descargar la imagen: {e}"[:300])
                continue

        if "document" in m:
            doc = m["document"]
            try:
                texto += "\n\n" + extraer_texto(doc.get("file_name", "archivo"),
                                                _descargar(doc["file_id"]))
            except Exception as e:
                texto += f"\n[No se pudo descargar el adjunto: {e}]"
        if not texto.strip() and not imagen_bytes:
            continue

        if reenviado:
            origen = m.get("forward_origin", {})
            quien = (origen.get("sender_user", {}).get("first_name") or origen.get("sender_user_name")
                     or m.get("forward_sender_name") or "contacto reenviado")
            remitente = f"{quien} (reenviado por {config.TU_NOMBRE})"
        else:
            nombre = " ".join(filter(None, [m.get("from", {}).get("first_name"),
                                            m.get("from", {}).get("last_name")])) or usuario or chat_id
            remitente = f"{nombre} (Telegram {chat_id})"
        mensajes.append({
            "id_externo": f"{chat_id}:{m['message_id']}",
            "remitente": remitente,
            "destino": chat_id,
            "asunto": "Imagen de Telegram" if imagen_bytes else ("Nota de voz de Telegram" if es_voz else "Mensaje de Telegram"),
            "mensaje": ("[Nota de voz transcrita]\n" if es_voz else "") + texto,
            "referencia": str(m["message_id"]),
            "es_orden": es_dueno and not reenviado,   # tú dándole instrucciones al asistente
            "es_voz": es_voz,
            "transcrito": transcrito,
            "imagen_bytes": imagen_bytes,
        })
    return mensajes, acciones


def enviar(chat_id, texto, archivo="", referencia="", botones=None):
    for i in range(0, max(len(texto), 1), 4000):
        datos = {"chat_id": chat_id, "text": texto[i:i + 4000] or "-"}
        if referencia and i == 0:
            datos["reply_to_message_id"] = referencia
            datos["allow_sending_without_reply"] = True
        if botones and i + 4000 >= len(texto):
            datos["reply_markup"] = {"inline_keyboard": botones}
        r = requests.post(_api("sendMessage"), json=datos, timeout=30)
        if not r.ok:
            raise RuntimeError(f"Telegram: {r.text}")
    if archivo and os.path.exists(archivo):
        with open(archivo, "rb") as f:
            nombre = os.path.basename(archivo).split("_", 1)[-1]
            r = requests.post(_api("sendDocument"), data={"chat_id": chat_id},
                              files={"document": (nombre, f)}, timeout=120)
            if not r.ok:
                raise RuntimeError(f"Telegram: {r.text}")


def enviar_voz(chat_id, texto):
    """Envía respuesta con voz J.A.R.V.I.S. (Gemini TTS: Fenrir). Respaldo en gTTS si falla."""
    accion_escribiendo(chat_id, "record_voice")
    try:
        wav = ia.sintetizar_voz(texto)
        if wav:
            ruta = os.path.join(tempfile.gettempdir(), f"voz_{chat_id}.wav")
            with open(ruta, "wb") as f:
                f.write(wav)
            with open(ruta, "rb") as f:
                r = requests.post(_api("sendVoice"), data={"chat_id": chat_id},
                                  files={"voice": ("jarvis.wav", f, "audio/wav")}, timeout=60)
            if r.ok:
                return
    except Exception:
        pass

    # Respaldo rápido con gTTS
    try:
        from gtts import gTTS
        limpio = texto.replace("#", "número ").replace("•", "").replace("✅", "").replace("⚠️", "")
        ruta = os.path.join(tempfile.gettempdir(), f"voz_{chat_id}.mp3")
        gTTS(limpio[:1500], lang="es", tld=config.VOZ_ACENTO).save(ruta)
        with open(ruta, "rb") as f:
            requests.post(_api("sendVoice"), data={"chat_id": chat_id},
                          files={"voice": ("respuesta.mp3", f, "audio/mpeg")}, timeout=60)
    except Exception:
        pass


def responder_callback(id_callback, texto):
    requests.post(_api("answerCallbackQuery"),
                  json={"callback_query_id": id_callback, "text": texto}, timeout=15)


def notificar_dueno(t):
    """Te manda el resultado al Telegram para que apruebes desde el celular."""
    if not (config.TELEGRAM_ACTIVO and config.TELEGRAM_CHAT_DUENO):
        return
    ver = t.get("verificacion") or {}
    estado = "✅ Verificada" if ver.get("cumple") else "⚠️ Revisar con cuidado"
    if t["estado"] == "necesita_aclaracion":
        estado = "❓ Faltan datos: borrador de pregunta al remitente"
    resumen = (t.get("analisis") or {}).get("resumen_tarea", "")
    texto = (f"📌 Tarea #{t['id']} ({t['canal']}) de {t['remitente']}\n"
             f"{estado} · puntuación {ver.get('puntuacion', '-')}\n\n"
             f"📝 Se pidió: {resumen}\n\n"
             f"✉️ Respuesta propuesta:\n{t.get('respuesta') or ''}\n\n"
             f"🔎 Panel: {config.PANEL_URL}/tarea/{t['id']}\n"
             f"🎤 Puedes responderme con voz: \"aprueba la {t['id']}\" o \"en la {t['id']} cambia...\"")
    botones = [[{"text": "✅ Aprobar y enviar", "callback_data": f"aprobar:{t['id']}"},
                {"text": "❌ Rechazar", "callback_data": f"rechazar:{t['id']}"}]]
    enviar(config.TELEGRAM_CHAT_DUENO, texto, t.get("archivo") or "", botones=botones)
    if config.VOZ_RESPUESTAS:
        try:
            enviar_voz(config.TELEGRAM_CHAT_DUENO,
                       f"Tarea {t['id']} lista para revisar. {resumen}. {estado}.")
        except Exception:
            pass
