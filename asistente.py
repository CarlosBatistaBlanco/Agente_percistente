"""ASISTENTE: entiende lo que TÚ le dices (voz o texto, desde Telegram o el panel)
y lo convierte en acciones: crear tarea, listar, leer, corregir, aprobar, rechazar.

Por seguridad, APROBAR y RECHAZAR nunca se ejecutan directo por voz: siempre te pide
confirmar con un botón (una transcripción equivocada no puede enviar nada)."""
import re
import time

import config
import db
import ia

AYUDA = ("Puedo ayudarte así (por voz o por texto):\n"
         "• \"¿Qué tengo pendiente?\"\n"
         "• \"Léeme la tarea 3\"\n"
         "• \"En la tarea 3 agrega una columna de descuento\"\n"
         "• \"Aprueba la tarea 3\" (te pido confirmar con un botón)\n"
         "• \"Rechaza la 2\"\n"
         "• \"Hazme un Word con un oficio para...\" (tarea nueva)\n"
         "También puedes reenviarme mensajes o notas de voz de otras personas y los trato como tareas.")

PENDIENTES = ("pendiente_revision", "necesita_aclaracion", "nueva", "analizando", "error")

_RAPIDOS = {
    "pendientes": "listar", "listar": "listar", "lista": "listar",
    "ver": "ver", "leer": "ver", "aprobar": "aprobar", "rechazar": "rechazar",
    "ayuda": "ayuda", "help": "ayuda", "start": "ayuda",
}


def _rapido(texto):
    """Comandos directos sin gastar IA: /pendientes, /ver 3, /aprobar 3, /rechazar 3."""
    m = re.match(r"^/(\w+)\s*#?(\d+)?\s*$", texto.strip().lower())
    if m and m.group(1) in _RAPIDOS:
        return {"accion": _RAPIDOS[m.group(1)],
                "tarea_id": int(m.group(2)) if m.group(2) else None, "texto": "", "respuesta": ""}
    return None


def _ficha(t, corta=False):
    a = t.get("analisis") if isinstance(t.get("analisis"), dict) else {}
    v = t.get("verificacion") if isinstance(t.get("verificacion"), dict) else {}
    linea = f"#{t['id']} · {t['remitente']} · {a.get('resumen_tarea') or t.get('asunto')} · {t['estado'].replace('_', ' ')}"
    if corta:
        return linea
    calidad = ("✅ verificada" if v.get("cumple") else "⚠️ revisar") if v else ""
    return (f"Tarea {linea}\n{calidad} {('(' + str(v.get('puntuacion')) + '/100)') if v else ''}\n\n"
            f"Respuesta propuesta:\n{t.get('respuesta') or '(aún sin respuesta)'}")


def analizar_imagen_orden(imagen_bytes, instruccion="", chat_id="", mime="image/jpeg"):
    cid = str(chat_id or "panel")
    modo = db.obtener_modo(cid)
    resp = ia.analizar_imagen(imagen_bytes, instruccion, mime, modo)
    db.agregar_turno(cid, "usuario", f"[Imagen enviada] {instruccion}".strip())
    db.agregar_turno(cid, "asistente", resp)
    return {"texto": resp}


def ejecutar(texto, origen, cola, registrar, chat_id=""):
    """Devuelve dict: texto (para mostrar/decir), botones (Telegram), archivo, ir_a (panel)."""
    cid = str(chat_id or origen or "panel")
    patron_wake = rf"^\s*{re.escape(config.NOMBRE_ASISTENTE)}[,\s:]*\s*"
    texto_limpio = re.sub(patron_wake, "", texto.strip(), flags=re.IGNORECASE).strip() or texto.strip()

    pendientes = db.por_estado(*PENDIENTES)
    txt_lower = texto_limpio.lower()

    # 0. RESETEO RÁPIDO DE MODO
    if txt_lower in ("/normal", "modo normal", "modo jarvis", "vuelve a modo normal", "deja de ser maestro"):
        db.guardar_modo(cid, "")
        return {"texto": "Entendido, señor. Desactivando modo especialista y volviendo a modo operativo J.A.R.V.I.S."}

    # 1. COMANDOS DIRECTOS DE CONTROL Y TELEMETRÍA (sin gastar tokens)
    if any(k in txt_lower for k in ["diagnóstico", "diagnostico", "estado de la pc", "batería", "bateria", "sensores", "telemetría"]):
        import jarvis_tools
        return {"texto": jarvis_tools.diagnostico_sistema()}

    if any(k in txt_lower for k in ["bloquea la pc", "bloquear pc", "bloquear equipo", "bloquea pantalla"]):
        import jarvis_tools
        return {"texto": jarvis_tools.ejecutar_comando_pc("bloquear")}

    if "abre excel" in txt_lower or "abrir excel" in txt_lower:
        import jarvis_tools
        return {"texto": jarvis_tools.ejecutar_comando_pc("excel")}

    if "abre word" in txt_lower or "abrir word" in txt_lower:
        import jarvis_tools
        return {"texto": jarvis_tools.ejecutar_comando_pc("word")}

    if any(k in txt_lower for k in ["abre el navegador", "abrir navegador", "abre chrome"]):
        import jarvis_tools
        return {"texto": jarvis_tools.ejecutar_comando_pc("chrome")}

    if any(k in txt_lower for k in ["abre visual studio", "abre el codigo", "abre vscode", "muéstrame el código", "muestrame el codigo"]):
        import jarvis_tools
        return {"texto": jarvis_tools.ejecutar_comando_pc("vscode")}

    if any(k in txt_lower for k in ["vacía la papelera", "vacia la papelera", "limpia la papelera", "limpieza de disco"]):
        import jarvis_tools
        return {"texto": jarvis_tools.ejecutar_comando_pc("papelera")}

    if any(k in txt_lower for k in ["captura de pantalla", "toma una foto", "qué hay en mi pantalla", "captura pantalla"]):
        import jarvis_tools
        ruta = jarvis_tools.capturar_pantalla()
        return {"texto": "Captura de pantalla realizada con éxito, señor.", "archivo": ruta}

    m_temp = re.search(r"(?:recuérdame|recuerdame|avísame|avisame|alarma en|temporizador en)\s+(\d+)\s*(minutos?|segundos?|horas?)\s*(?:para|de|que)?\s*(.*)", txt_lower)
    if m_temp:
        import jarvis_tools
        cant = int(m_temp.group(1))
        unidad = m_temp.group(2)
        motivo = m_temp.group(3).strip() or "Recordatorio programado"
        segs = cant * 3600 if "hora" in unidad else (cant * 60 if "min" in unidad else cant)
        return {"texto": jarvis_tools.crear_temporizador(segs, motivo, chat_id)}

    if any(txt_lower.startswith(k) for k in ["busca en internet ", "busca en la web ", "investiga ", "noticias de ", "precio de ", "clima en "]):
        import jarvis_tools
        consulta = re.sub(r"^(busca en internet|busca en la web|investiga|noticias de|precio de|clima en)\s+", "", texto_limpio, flags=re.I).strip()
        info_web = jarvis_tools.investigar(consulta)
        resp = ia.responder_con_info(texto_limpio, info_web, db.obtener_historial(cid), db.obtener_modo(cid))
        db.agregar_turno(cid, "usuario", texto_limpio)
        db.agregar_turno(cid, "asistente", resp)
        return {"texto": resp}

    # HABILIDADES UNIFICADAS DE EL BATY.0
    if any(k in txt_lower for k in ["llama a ", "llamar a ", "contacto de ", "teléfono de ", "telefono de "]):
        import baty_skills
        nombre = re.sub(r"^(llama a|llamar a|contacto de|teléfono de|telefono de)\s+", "", texto_limpio, flags=re.I).strip()
        return {"texto": baty_skills.buscar_contacto(nombre)}

    if any(k in txt_lower for k in ["clase de inglés", "clase de ingles", "verbos en inglés", "verbos en ingles", "microcurso", "lección de inglés"]):
        import baty_skills
        return {"texto": baty_skills.leccion_ingles_rapida()}

    # 2. INTENCIÓN CON IA + MEMORIA + MODO ACTIVO
    rapido = _rapido(texto_limpio)
    modo_actual = db.obtener_modo(cid)
    historial = [] if rapido else db.obtener_historial(cid)
    cmd = rapido or ia.interpretar_comando(texto_limpio, pendientes, historial, modo_actual)
    accion, tid = cmd.get("accion"), cmd.get("tarea_id")

    if accion == "cambiar_modo":
        nuevo_modo = (cmd.get("modo") or "").strip()
        db.guardar_modo(cid, nuevo_modo)
        resp = (cmd.get("respuesta") or "").strip() or (
            f"Modo activado: {nuevo_modo}. Empecemos de inmediato, señor." if nuevo_modo
            else "Modo normal J.A.R.V.I.S. restaurado, señor."
        )
        db.agregar_turno(cid, "usuario", texto_limpio)
        db.agregar_turno(cid, "asistente", resp)
        return {"texto": resp}

    if accion == "buscar_info":
        import jarvis_tools
        consulta = (cmd.get("consulta") or texto_limpio).strip()
        info_web = jarvis_tools.investigar(consulta)
        resp = ia.responder_con_info(texto_limpio, info_web, historial, modo_actual)
        db.agregar_turno(cid, "usuario", texto_limpio)
        db.agregar_turno(cid, "asistente", resp)
        return {"texto": resp}

    # Si no dijo el número pero solo hay una tarea en revisión, se asume esa.
    revisables = [t for t in pendientes if t["estado"] in ("pendiente_revision", "necesita_aclaracion")]
    if accion in ("ver", "aprobar", "rechazar", "corregir") and not tid and len(revisables) == 1:
        tid = revisables[0]["id"]
    t = db.obtener(int(tid)) if tid else None
    if accion in ("ver", "aprobar", "rechazar", "corregir") and not t:
        return {"texto": "¿De qué número de tarea hablas? Estas son las pendientes:\n" +
                         ("\n".join(_ficha(x, True) for x in pendientes) or "No hay pendientes.")}

    if accion == "listar":
        if not pendientes:
            return {"texto": "Bandeja impecable, señor. No tiene tareas pendientes."}
        return {"texto": f"Tiene {len(pendientes)} tarea(s) en curso o pendientes de revisión:\n" +
                         "\n".join(_ficha(x, True) for x in pendientes)}

    if accion == "ver":
        botones = None
        if t["estado"] in ("pendiente_revision", "necesita_aclaracion"):
            botones = [[{"text": "✅ Aprobar y enviar", "callback_data": f"aprobar:{t['id']}"},
                        {"text": "❌ Rechazar", "callback_data": f"rechazar:{t['id']}"}]]
        return {"texto": f"A su disposición, señor. Desplegando tarea #{t['id']}:\n\n" + _ficha(t),
                "botones": botones, "archivo": t.get("archivo") or "",
                "ir_a": f"/tarea/{t['id']}"}

    if accion == "aprobar":
        if t["estado"] not in ("pendiente_revision", "necesita_aclaracion"):
            return {"texto": f"La tarea #{t['id']} se encuentra en estado '{t['estado']}', señor. No requiere envío."}
        return {"texto": f"¿Confirma la autorización de salida para la tarea #{t['id']} a {t['remitente']} por {t['canal']}?\n\n"
                         f"{t.get('respuesta') or ''}",
                "botones": [[{"text": "✅ Sí, enviar", "callback_data": f"aprobar:{t['id']}"},
                             {"text": "Cancelar", "callback_data": "cancelar:0"}]],
                "ir_a": f"/tarea/{t['id']}"}

    if accion == "rechazar":
        return {"texto": f"¿Desea descartar definitivamente la tarea #{t['id']}, señor?",
                "botones": [[{"text": "❌ Sí, rechazar", "callback_data": f"rechazar:{t['id']}"},
                             {"text": "Cancelar", "callback_data": "cancelar:0"}]],
                "ir_a": f"/tarea/{t['id']}"}

    if accion == "corregir":
        indic = (cmd.get("texto") or texto).strip()
        extra = "\n".join(filter(None, [t.get("instrucciones_extra"), indic]))
        db.actualizar(t["id"], instrucciones_extra=extra, estado="nueva")
        cola.put(t["id"])
        return {"texto": f"Enseguida, señor. Procedo a recalibrar la tarea #{t['id']} considerando: \"{indic}\". Le notificaré en cuanto esté lista.",
                "ir_a": f"/tarea/{t['id']}"}

    if accion == "nueva_tarea":
        contenido = (cmd.get("texto") or texto).strip()
        canal, destino = ("telegram", chat_id) if origen == "telegram" else ("manual", "")
        nid = registrar(canal, f"dictado-{time.time()}", f"{config.TU_NOMBRE} (dictado)", destino,
                        "Tarea dictada", contenido)
        return {"texto": f"A la orden, señor. Registré la tarea #{nid}: \"{contenido[:200]}\". "
                         "Iniciando análisis, resolución y verificación de calidad.",
                "ir_a": f"/tarea/{nid}"}

    if accion == "ayuda":
        return {"texto": AYUDA}

    resp = (cmd.get("respuesta") or "").strip() or AYUDA
    db.agregar_turno(cid, "usuario", texto_limpio)
    db.agregar_turno(cid, "asistente", resp)
    return {"texto": resp}
