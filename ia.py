"""Cerebro del agente: 3 pasos con Gemini -> ANALIZAR, RESOLVER, VERIFICAR.
La verificación independiente es lo que evita que haga "cualquier cosa"."""
import json
import re

import requests

import config

URL = "https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent"

SISTEMA = f"""Eres el asistente ejecutivo personal de {config.TU_NOMBRE}.
Contexto sobre {config.TU_NOMBRE}: {config.CONTEXTO_PERSONAL or "(sin contexto adicional)"}

Recibes mensajes que llegan por correo, WhatsApp o Telegram. Tu trabajo es entender EXACTAMENTE
qué se pide y hacerlo bien a la primera.

REGLAS INQUEBRANTABLES:
1. Haz solo lo que se pide, ni más ni menos. No cambies el alcance ni agregues cosas no solicitadas.
2. NUNCA inventes datos, cifras, nombres, fechas, precios ni hechos. Si falta un dato, escribe
   [PENDIENTE: descripción del dato] y repórtalo.
3. Respeta formatos, cantidades, columnas, fechas límite, idioma y tono del mensaje original.
4. Si algo es ambiguo, dilo explícitamente; no adivines.
5. Nunca comprometas a {config.TU_NOMBRE} (pagos, reuniones, precios, promesas) si no está indicado.
6. Responde SIEMPRE en JSON válido con exactamente la estructura que se te pide, sin texto extra.
"""

SISTEMA_CHAT = (
    f"Eres J.A.R.V.I.S., asistente personal inteligente de {config.TU_NOMBRE}. "
    "Responde con precisión, rapidez y claridad en JSON válido sin texto extra."
)

_SESION = requests.Session()
_MODELO_CACHE = {"nombre": "", "expira": 0.0}


def _json(texto):
    try:
        return json.loads(texto)
    except Exception:
        m = re.search(r"\{.*\}", texto, re.S)
        if not m:
            raise ValueError("La IA no devolvió JSON: " + texto[:500])
        return json.loads(m.group(0))


MODELOS_RESPALDO = [
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-3-flash-preview",
    "gemini-flash-lite-latest",
]


def _llamar(prompt, temperatura=0.2, extra_partes=None, modelos_extra=None,
            sistema=None, timeout=12):
    import time
    if not config.GEMINI_API_KEY:
        raise RuntimeError("Falta GEMINI_API_KEY en el archivo .env")
    ahora = time.time()
    preferido = _MODELO_CACHE["nombre"] if ahora < _MODELO_CACHE["expira"] else ""
    candidatos = []
    for m in [preferido, config.GEMINI_MODELO, *(modelos_extra or []), *MODELOS_RESPALDO]:
        if m and m not in candidatos:
            candidatos.append(m)

    ultimo_error = "Sin respuesta de Gemini"
    payload = {
        "systemInstruction": {"parts": [{"text": sistema or SISTEMA}]},
        "contents": [{"role": "user", "parts": (extra_partes or []) + [{"text": prompt}]}],
        "generationConfig": {"temperature": temperatura, "responseMimeType": "application/json"},
    }
    for m in candidatos:
        try:
            r = _SESION.post(
                URL.format(m=m),
                params={"key": config.GEMINI_API_KEY},
                json=payload,
                timeout=timeout,
            )
            if r.status_code == 200:
                _MODELO_CACHE["nombre"] = m
                _MODELO_CACHE["expira"] = time.time() + 180
                partes = r.json()["candidates"][0]["content"]["parts"]
                return _json("".join(p.get("text", "") for p in partes))
            ultimo_error = f"Error Gemini {r.status_code} ({m}): {r.text[:300]}"
            if r.status_code in (400, 401, 403):
                raise RuntimeError(ultimo_error)
            # 404 / 429 / 503 -> saltar de inmediato al siguiente modelo
        except requests.RequestException as e:
            ultimo_error = f"Error red ({m}): {e}"
    raise RuntimeError(ultimo_error)


# ---------------------------------------------------------------- VOZ Y VISIÓN
def transcribir(audio: bytes, mime="audio/ogg"):
    """Convierte una nota de voz en texto (Gemini entiende audio directamente)."""
    import base64
    r = _llamar('Transcribe LITERALMENTE este audio, en su idioma original, corrigiendo solo '
                'la puntuación. Devuelve JSON: {"texto": "..."}', 0.0,
                [{"inline_data": {"mime_type": mime,
                                  "data": base64.b64encode(audio).decode()}}],
                sistema=SISTEMA_CHAT, timeout=15)
    return (r.get("texto") or "").strip()


def _resumir_para_voz(texto, max_chars=480):
    limpio = re.sub(r"[#*`•✅❌⚠️🎉📌🎤⚙️🔎✉️📝🤖]", "", texto or "")
    limpio = re.sub(r"https?://\S+", "el enlace", limpio)
    limpio = re.sub(r"\s+", " ", limpio).strip()
    if len(limpio) <= max_chars:
        return limpio
    corte = limpio[:max_chars]
    for sep in (". ", "! ", "? "):
        idx = corte.rfind(sep)
        if idx > 150:
            return corte[:idx + 1]
    return corte


def sintetizar_voz(texto, voz=None):
    """Genera audio con tono J.A.R.V.I.S. (Gemini TTS: Fenrir). Devuelve bytes WAV."""
    import base64
    import io
    import wave
    voz = voz or config.VOZ_MODELO
    limpio = _resumir_para_voz(texto)
    if not limpio:
        return b""
    r = _SESION.post(
        URL.format(m="gemini-2.5-flash-preview-tts"),
        params={"key": config.GEMINI_API_KEY},
        json={
            "contents": [{"parts": [{"text": limpio}]}],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voz}}}
            }
        },
        timeout=15,
    )
    if r.status_code != 200:
        raise RuntimeError(f"Error TTS Gemini: {r.text[:300]}")
    pcm = base64.b64decode(r.json()["candidates"][0]["content"]["parts"][0]["inlineData"]["data"])
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(pcm)
    return buf.getvalue()


def _texto_historial(historial):
    if not historial:
        return "(inicio de conversación)"
    return "\n".join(f"{'Carlos' if h['rol']=='usuario' else 'Jarvis'}: {h['texto'][:400]}"
                     for h in historial[-6:])


def _bloque_persona(modo):
    if modo:
        return (f"MODO ACTIVO: {modo}. Actúa 100% como ese rol/maestro de élite para {config.TU_NOMBRE}: "
                "enseña con claridad, ejemplos prácticos, ejercicios cortos y adapta el nivel a sus respuestas, "
                "manteniendo la precisión y elegancia de J.A.R.V.I.S.")
    return (f"PERSONALIDAD: Eres J.A.R.V.I.S., el asistente personal inteligente de {config.TU_NOMBRE}. "
            "Responde directo, claro, con seguridad técnica y trato cercano ('señor' o 'Carlos' cuando quede natural). "
            "Si te piden convertirte en maestro/profesor/entrenador o adoptar un rol, acéptalo de inmediato.")


def interpretar_comando(texto, pendientes, historial=None, modo=""):
    """Entiende órdenes, conversación continua, cambios de rol (Maestro) o búsqueda en vivo."""
    lista = "\n".join(f"#{t['id']} | {t['canal']} | {t['remitente']} | "
                      f"{(t.get('analisis') or {}).get('resumen_tarea', t.get('asunto', ''))} | {t['estado']}"
                      for t in pendientes) or "(no hay tareas pendientes)"
    prompt = f"""{_bloque_persona(modo)}

HISTORIAL RECIENTE:
{_texto_historial(historial)}

MENSAJE ACTUAL DE {config.TU_NOMBRE}:
<<<
{texto}
>>>

TAREAS PENDIENTES DE REVISIÓN:
{lista}

Decide qué acción tomar y devuelve JSON válido:
{{
  "accion": "nueva_tarea | listar | ver | aprobar | rechazar | corregir | ayuda | cambiar_modo | buscar_info | conversar",
  "tarea_id": null,
  "modo": "",
  "consulta": "",
  "texto": "",
  "respuesta": ""
}}
REGLAS:
- cambiar_modo: cuando te pide que te conviertas en su maestro/profesor/tutor/coach o cambies de rol (ej. "conviértete en mi maestro de inglés"), O cuando pide volver a modo normal ("vuelve a modo jarvis/normal" -> "modo": ""). En "modo" pon la especialidad exacta (o "" para modo normal) y en "respuesta" inicia de inmediato asumiendo ese rol (ej. primer paso/pregunta de nivel o primera micro-lección).
- buscar_info: cuando pide datos actuales en vivo (noticias de hoy, precios/cotizaciones de hoy, clima, URLs) o investigación profunda en internet. Pon en "consulta" palabras clave cortas en español o inglés (o la URL). Para conocimiento general o preguntas directas que ya sabes con certeza, responde directo con "conversar".
- nueva_tarea: cuando te pide crear un archivo (Word, Excel) o redactar un correo/mensaje formal para alguien. "texto" = la tarea completa.
- listar / ver / aprobar / rechazar / corregir: sobre las TAREAS PENDIENTES. Nunca inventes tarea_id.
- conversar: diálogo general, explicaciones, clases del modo activo, preguntas de conocimiento, lluvia de ideas. En "respuesta" contesta de forma completa, clara y directa (sin rodeos)."""
    return _llamar(prompt, 0.25, sistema=SISTEMA_CHAT, timeout=14)


def responder_con_info(pregunta, info_web, historial=None, modo=""):
    """Sintetiza información en vivo de internet en una respuesta precisa de J.A.R.V.I.S."""
    prompt = f"""{_bloque_persona(modo)}

HISTORIAL RECIENTE:
{_texto_historial(historial)}

PREGUNTA DE {config.TU_NOMBRE}:
{pregunta}

RESULTADOS EN VIVO DE INTERNET:
<<<
{info_web[:6000]}
>>>

Responde en JSON: {{"respuesta": "..."}}
Reglas: usa la información verificada anterior (y tu conocimiento sólido si los resultados fueron parciales), sé claro, directo y concreto; incluye enlaces si aportan valor y nunca escribas marcadores [PENDIENTE]."""
    return (_llamar(prompt, 0.2, sistema=SISTEMA_CHAT, timeout=14).get("respuesta") or "").strip()


def analizar_imagen(imagen: bytes, instruccion="", mime="image/jpeg", modo=""):
    """Analiza fotos, capturas, diagramas o problemas enviados por el usuario."""
    import base64
    prompt = f"""{_bloque_persona(modo)}
Analiza esta imagen para {config.TU_NOMBRE}.
Instrucción del usuario: {instruccion or "Describe lo que ves y ayuda con lo más útil (si es un problema, resuélvelo paso a paso)."}
Devuelve JSON: {{"respuesta": "..."}}"""
    r = _llamar(prompt, 0.2, [{"inline_data": {"mime_type": mime,
                                                 "data": base64.b64encode(imagen).decode()}}],
                sistema=SISTEMA_CHAT, timeout=18)
    return (r.get("respuesta") or "").strip()


def _bloque(t):
    return f"""CANAL: {t['canal']}
DE: {t['remitente']}
ASUNTO: {t.get('asunto') or '(sin asunto)'}
MENSAJE ORIGINAL (incluye texto de adjuntos si los hay):
<<<
{(t.get('mensaje') or '')[:30000]}
>>>"""


def analizar(t):
    extra = t.get("instrucciones_extra") or ""
    prompt = f"""PASO 1 - ANALIZAR. Decide si este mensaje contiene una tarea o solicitud que
{config.TU_NOMBRE} deba atender, y entiende exactamente qué se pide.

{_bloque(t)}
{"INDICACIONES ADICIONALES DE " + config.TU_NOMBRE + ": " + extra if extra else ""}

Devuelve este JSON:
{{
  "es_tarea": true,
  "motivo": "por qué es o no es una tarea",
  "resumen_tarea": "una frase clara de lo que se pide",
  "requisitos": ["cada cosa concreta y verificable que se pide (cantidades, columnas, formato, fecha, tono...)"],
  "tipo_entregable": "respuesta_texto | excel | word",
  "nombre_archivo": "nombre_corto_sin_extension",
  "datos_disponibles": ["datos del mensaje que se usarán"],
  "datos_faltantes": ["datos IMPRESCINDIBLES que no están y que no se pueden deducir"],
  "confianza": 0,
  "mensaje_aclaracion": "si faltan datos imprescindibles: borrador cortés pidiendo exactamente esos datos; si no, cadena vacía"
}}
- "es_tarea" = false para publicidad, spam, notificaciones automáticas o mensajes sin solicitud.
- "excel" si piden tabla, hoja de cálculo, lista con cifras, presupuesto, inventario, cálculos.
- "word" si piden documento, carta, informe, oficio, acta, contrato, reporte formal.
- Si no, "respuesta_texto".
- "confianza" (0-100) = qué tan seguro estás de haber entendido EXACTAMENTE lo que se pide."""
    return _llamar(prompt, 0.1)


def resolver(t, plan, retro=""):
    extra = t.get("instrucciones_extra") or ""
    prompt = f"""PASO 2 - RESOLVER la tarea cumpliendo TODOS los requisitos.

{_bloque(t)}

ANÁLISIS PREVIO:
{json.dumps(plan, ensure_ascii=False, indent=1)}
{"INDICACIONES ADICIONALES DE " + config.TU_NOMBRE + " (obligatorias): " + extra if extra else ""}
{"CORRIGE ESTOS PROBLEMAS DETECTADOS POR EL REVISOR: " + retro if retro else ""}

Devuelve JSON según el tipo de entregable "{plan.get('tipo_entregable')}":

- respuesta_texto:
  {{"mensaje_respuesta": "respuesta completa lista para enviar"}}

- excel:
  {{"mensaje_respuesta": "texto breve para acompañar el archivo",
    "hojas": [{{"nombre": "máx 31 caracteres",
               "encabezados": ["Col A", "Col B"],
               "filas": [["valor", 10], ["valor", 20]],
               "anchos": [20, 12]}}]}}
  Los encabezados van en la fila 1 y los datos empiezan en la fila 2. Puedes usar fórmulas de
  Excel en INGLÉS que empiecen con "=" (ej. "=SUM(B2:B10)"). Los números van como números.

- word:
  {{"mensaje_respuesta": "texto breve para acompañar el archivo",
    "titulo": "Título del documento",
    "secciones": [{{"titulo": "", "parrafos": [""], "vinetas": [""],
                   "tabla": {{"encabezados": [], "filas": [[]]}}}}]}}

El "mensaje_respuesta" se enviará a {t['remitente']} en nombre de {config.TU_NOMBRE}:
usa el mismo idioma y un tono adecuado al mensaje original. Firma como {config.TU_NOMBRE}."""
    return _llamar(prompt, 0.3)


def verificar(t, plan, resultado):
    prompt = f"""PASO 3 - VERIFICAR. Eres un revisor de calidad ESTRICTO e independiente.
Compara la solicitud original con el resultado propuesto y revisa requisito por requisito.

{_bloque(t)}

REQUISITOS DETECTADOS:
{json.dumps(plan.get('requisitos', []), ensure_ascii=False, indent=1)}

RESULTADO PROPUESTO:
{json.dumps(resultado, ensure_ascii=False, indent=1)[:30000]}

Devuelve JSON:
{{
  "cumple": true,
  "puntuacion": 0,
  "requisitos": [{{"requisito": "", "cumplido": true, "nota": ""}}],
  "problemas": ["errores, omisiones, cálculos incorrectos, cosas que NO se pidieron"],
  "datos_inventados": ["datos que no venían en el mensaje y fueron inventados"],
  "pendientes": ["marcadores [PENDIENTE] que {config.TU_NOMBRE} debe completar"]
}}
"cumple" = true SOLO si todos los requisitos están cumplidos, no hay errores y no hay datos inventados.
Revisa también que las fórmulas y sumas sean correctas."""
    return _llamar(prompt, 0.0)
