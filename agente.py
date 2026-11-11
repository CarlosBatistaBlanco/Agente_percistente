"""AGENTE PERSISTENTE DE TAREAS
Ciclo: DETECTA -> ANALIZA -> EJECUTA -> VERIFICA -> TE MUESTRA -> (tú apruebas) -> ENVÍA
Ejecutar:  python agente.py   y abrir http://127.0.0.1:5000
"""
import logging
import queue
import threading
import time
import traceback

import config
import db
import ejecutores
import ia
from canales import correo, telegram, whatsapp

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("agente")
cola = queue.Queue()


# ---------------------------------------------------------------- DETECTAR
def registrar(canal, id_externo, remitente, destino, asunto, mensaje, referencia=""):
    tid = db.crear(canal, id_externo, remitente, destino, asunto, mensaje, referencia)
    if tid:
        log.info("Nueva tarea #%s desde %s (%s)", tid, canal, remitente)
        cola.put(tid)
        if canal == "telegram" and destino and str(destino) != str(config.TELEGRAM_CHAT_DUENO):
            try:
                telegram.enviar(destino, f"🤖 Recibido. Estoy procesando su solicitud y la enviaré a revisión con {config.TU_NOMBRE} de inmediato.")
            except Exception:
                pass
    return tid


def bucle_correo():
    while True:
        try:
            for m in correo.revisar():
                registrar("correo", **m)
        except Exception as e:
            log.error("Correo: %s", e)
        time.sleep(config.INTERVALO_SEGUNDOS)


def comando(texto, origen="panel", chat_id=""):
    """Órdenes tuyas (voz o texto) -> asistente."""
    import asistente
    return asistente.ejecutar(texto, origen, cola, registrar, chat_id)


def _orden_telegram(m):
    chat = m["destino"]
    telegram.accion_escribiendo(chat)
    try:
        if m.get("imagen_bytes"):
            import asistente
            r = asistente.analizar_imagen_orden(m["imagen_bytes"], m.get("mensaje", ""), chat)
        else:
            r = comando(m["mensaje"].replace("[Nota de voz transcrita]\n", ""), "telegram", chat)
    except Exception as e:
        r = {"texto": f"Tuve un problema: {e}"[:500]}

    texto_resp = r.get("texto", "")
    texto_mostrar = f"🎤 «{m['transcrito']}»\n\n{texto_resp}" if m.get("transcrito") else texto_resp
    telegram.enviar(chat, texto_mostrar, r.get("archivo") or "", botones=r.get("botones"))

    # Respuesta por voz si VOZ_RESPUESTAS=true o si hablaste por audio
    if (config.VOZ_RESPUESTAS or m.get("es_voz")) and texto_resp:
        try:
            telegram.enviar_voz(chat, texto_resp)
        except Exception as e:
            log.warning("No se pudo generar voz: %s", e)


def bucle_telegram():
    while True:
        try:
            mensajes, acciones = telegram.revisar()
            for m in mensajes:
                if m.pop("es_orden", False):
                    threading.Thread(target=_orden_telegram, args=(m,), daemon=True).start()
                else:
                    m.pop("es_voz", None)
                    m.pop("transcrito", None)
                    m.pop("imagen_bytes", None)
                    registrar("telegram", **m)
            for a in acciones:
                accion, _, tid = a["data"].partition(":")
                try:
                    if accion == "auth_permitir":
                        config.TELEGRAM_CHATS_PERMITIDOS.append(tid)
                        telegram.responder_callback(a["id_callback"], "Usuario autorizado ✅")
                        telegram.enviar(a["chat_id"], f"✅ Acceso concedido al usuario (ID: {tid}).")
                        telegram.enviar(tid, f"✅ Acceso concedido por {config.TU_NOMBRE}. Ahora puede enviarme tareas o consultas.")
                    elif accion == "auth_denegar":
                        telegram.responder_callback(a["id_callback"], "Acceso denegado ❌")
                        telegram.enviar(a["chat_id"], f"❌ Solicitud rechazada para ID: {tid}.")
                        telegram.enviar(tid, "❌ Su solicitud de acceso ha sido denegada.")
                    elif accion == "aprobar":
                        enviar_tarea(int(tid))
                        telegram.responder_callback(a["id_callback"], f"Tarea #{tid} enviada ✅")
                        telegram.enviar(a["chat_id"], f"✅ Tarea #{tid} enviada.")
                    elif accion == "rechazar":
                        db.actualizar(int(tid), estado="rechazada")
                        telegram.responder_callback(a["id_callback"], f"Tarea #{tid} rechazada")
                        telegram.enviar(a["chat_id"], f"❌ Tarea #{tid} rechazada.")
                    else:
                        telegram.responder_callback(a["id_callback"], "Cancelado")
                except Exception as e:
                    telegram.responder_callback(a["id_callback"], f"Error: {e}"[:190])
                    telegram.enviar(a["chat_id"], f"⚠️ Error con la tarea #{tid}: {e}"[:500])
        except Exception as e:
            log.error("Telegram: %s", e)
            time.sleep(10)


# ------------------------------------------------- ANALIZAR / EJECUTAR / VERIFICAR
def procesar(tid):
    t = db.obtener(tid)
    db.actualizar(tid, estado="analizando", error=None)
    try:
        plan = ia.analizar(t)
        db.actualizar(tid, analisis=plan)
        if not plan.get("es_tarea"):
            db.actualizar(tid, estado="ignorada")
            log.info("#%s ignorada: %s", tid, plan.get("motivo"))
            return

        # Si faltan datos imprescindibles o no entendió bien -> NO inventa: prepara pregunta.
        if plan.get("datos_faltantes") and plan.get("mensaje_aclaracion") and \
                int(plan.get("confianza", 0)) < config.CONFIANZA_MINIMA:
            db.actualizar(tid, estado="necesita_aclaracion",
                          respuesta=plan["mensaje_aclaracion"], archivo="")
            _avisar(tid)
            return

        resultado = ia.resolver(t, plan)
        ver = ia.verificar(t, plan, resultado)
        intento = 1
        while not ver.get("cumple") and intento <= config.MAX_REINTENTOS:
            log.info("#%s no pasó verificación (intento %s), corrigiendo...", tid, intento)
            retro = "; ".join((ver.get("problemas") or []) + (ver.get("datos_inventados") or []))
            resultado = ia.resolver(t, plan, retro)
            ver = ia.verificar(t, plan, resultado)
            intento += 1

        archivo = ejecutores.ejecutar(plan, resultado, tid)
        db.actualizar(tid, resultado=resultado, verificacion=ver, archivo=archivo,
                      respuesta=resultado.get("mensaje_respuesta", ""),
                      estado="pendiente_revision")
        log.info("#%s lista para revisión (cumple=%s)", tid, ver.get("cumple"))
        _avisar(tid)
    except Exception as e:
        log.error("#%s error: %s", tid, e)
        db.actualizar(tid, estado="error", error=traceback.format_exc())


def _avisar(tid):
    try:
        telegram.notificar_dueno(db.obtener(tid))
    except Exception as e:
        log.warning("No se pudo notificar por Telegram: %s", e)


def trabajador():
    while True:
        tid = cola.get()
        procesar(tid)


# ---------------------------------------------------------------- ENVIAR
def enviar_tarea(tid, texto=None):
    """Solo se llama cuando TÚ apruebas (panel o botón de Telegram)."""
    t = db.obtener(tid)
    if t["estado"] not in ("pendiente_revision", "necesita_aclaracion"):
        raise RuntimeError(f"La tarea #{tid} está en estado '{t['estado']}', no se puede enviar")
    texto = texto if texto is not None else (t.get("respuesta") or "")
    archivo = "" if t["estado"] == "necesita_aclaracion" else (t.get("archivo") or "")
    canal = t["canal"]
    if canal == "correo":
        correo.enviar(t["destino"], t["asunto"], texto, archivo, t.get("referencia"))
    elif canal == "telegram":
        telegram.enviar(t["destino"], texto, archivo, t.get("referencia"))
    elif canal == "whatsapp":
        whatsapp.enviar(t["destino"], texto, archivo, t.get("referencia"))
    elif canal != "manual":
        raise RuntimeError(f"Canal desconocido: {canal}")
    db.actualizar(tid, estado="enviada", respuesta=texto)
    log.info("#%s ENVIADA por %s a %s", tid, canal, t["destino"])


def bucle_programado():
    """Vigila recordatorios persistentes en BD y envía el briefing diario a la hora configurada."""
    import jarvis_tools
    while True:
        try:
            ahora_dt = db.ahora_dt()
            ahora_str = ahora_dt.strftime("%Y-%m-%d %H:%M:%S")
            for rec in db.recordatorios_vencidos(ahora_str):
                db.marcar_recordatorio(rec["id"], "enviado")
                cid = rec.get("chat_id") or config.TELEGRAM_CHAT_DUENO
                txt = f"⏰ RECORDATORIO #{rec['id']}, señor:\n{rec['mensaje']}"
                if config.TELEGRAM_ACTIVO and cid and cid != "panel":
                    try:
                        telegram.enviar(cid, txt)
                        if config.VOZ_RESPUESTAS:
                            telegram.enviar_voz(cid, f"Señor, recordatorio: {rec['mensaje']}")
                    except Exception as e:
                        log.warning("Error enviando recordatorio #%s: %s", rec["id"], e)
                try:
                    import winsound
                    winsound.Beep(1000, 700)
                except Exception:
                    pass

            if config.BRIEFING_ACTIVO and config.TELEGRAM_ACTIVO and config.TELEGRAM_CHAT_DUENO:
                hoy = ahora_dt.strftime("%Y-%m-%d")
                hh_mm = ahora_dt.strftime("%H:%M")
                if hh_mm >= config.BRIEFING_HORA and db.obtener_kv("briefing_fecha") != hoy:
                    db.guardar_kv("briefing_fecha", hoy)
                    resumen = jarvis_tools.generar_briefing(config.TELEGRAM_CHAT_DUENO)
                    try:
                        telegram.enviar(config.TELEGRAM_CHAT_DUENO, resumen)
                        if config.VOZ_RESPUESTAS:
                            telegram.enviar_voz(config.TELEGRAM_CHAT_DUENO, resumen)
                    except Exception as e:
                        log.warning("Error enviando briefing diario: %s", e)
        except Exception as e:
            log.error("Programado: %s", e)
        time.sleep(20)


# ---------------------------------------------------------------- INICIO
def main():
    db.init()
    for t in db.por_estado("nueva", "analizando"):  # retoma lo pendiente tras reinicio
        cola.put(t["id"])
    threading.Thread(target=trabajador, daemon=True).start()
    threading.Thread(target=bucle_programado, daemon=True).start()
    if config.CORREO_ACTIVO:
        threading.Thread(target=bucle_correo, daemon=True).start()
        log.info("Vigilando correo %s", config.CORREO_USUARIO)
    if config.TELEGRAM_ACTIVO:
        threading.Thread(target=bucle_telegram, daemon=True).start()
        log.info("Vigilando Telegram")
        if config.TELEGRAM_CHAT_DUENO:
            try:
                telegram.enviar(config.TELEGRAM_CHAT_DUENO,
                                "🤖 Agente encendido. Háblame con una nota de voz o escríbeme. "
                                "Di \"¿qué puedes hacer?\" para ver opciones.")
            except Exception as e:
                log.warning("No pude saludar por Telegram: %s", e)

    from panel import crear_app
    app = crear_app(cola, enviar_tarea, registrar, comando)
    if config.WHATSAPP_ACTIVO:
        app.register_blueprint(whatsapp.crear_blueprint(registrar))
        log.info("Webhook WhatsApp en /webhook/whatsapp")
    log.info("Panel de revisión: %s", config.PANEL_URL)
    app.run(host=config.PANEL_HOST, port=config.PANEL_PUERTO, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
