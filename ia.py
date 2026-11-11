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
    "gemini-flash-latest",
]


def _llamar(prompt, temperatura=0.2, extra_partes=None, modelos_extra=None):
    import time
    if not config.GEMINI_API_KEY:
        raise RuntimeError("Falta GEMINI_API_KEY en el archivo .env")
    candidatos = []
    for m in [config.GEMINI_MODELO, *(modelos_extra or []), *MODELOS_RESPALDO]:
        if m and m not in candidatos:
            candidatos.append(m)

    ultimo_error = "Sin respuesta de Gemini"
    payload = {
        "systemInstruction": {"parts": [{"text": SISTEMA}]},
        "contents": [{"role": "user", "parts": (extra_partes or []) + [{"text": prompt}]}],
        "generationConfig": {"temperature": temperatura, "responseMimeType": "application/json"},
    }
    for m in candidatos:
        for intento in range(2):
            try:
                r = requests.post(
                    URL.format(m=m),
                    params={"key": config.GEMINI_API_KEY},
                    json=payload,
                    timeout=45,
                )
                if r.status_code == 200:
                    partes = r.json()["candidates"][0]["content"]["parts"]
                    return _json("".join(p.get("text", "") for p in partes))
                ultimo_error = f"Error Gemini {r.status_code} ({m}): {r.text[:300]}"
                if r.status_code in (400, 401, 403):
                    raise RuntimeError(ultimo_error)
                if r.status_code == 404:
                    break  # modelo no disponible para esta clave -> pasar al siguiente
                # 429 / 500 / 502 / 503 / 504 -> breve espera y reintento o fallback
                time.sleep(1.5 * (intento + 1))
            except requests.RequestException as e:
                ultimo_error = f"Error red ({m}): {e}"
                time.sleep(1)
    raise RuntimeError(ultimo_error)


# ---------------------------------------------------------------- VOZ
def transcribir(audio: bytes, mime="audio/ogg"):
    """Convierte una nota de voz en texto (Gemini entiende audio directamente)."""
    import base64
    r = _llamar('Transcribe LITERALMENTE este audio, en su idioma original, corrigiendo solo '
                'la puntuación. Devuelve JSON: {"texto": "..."}', 0.0,
                [{"inline_data": {"mime_type": mime,
                                  "data": base64.b64encode(audio).decode()}}])
    return (r.get("texto") or "").strip()


def sintetizar_voz(texto, voz=None):
    """Genera audio con tono J.A.R.V.I.S. (Gemini TTS: Fenrir). Devuelve bytes WAV."""
    import base64
    import io
    import wave
    voz = voz or config.VOZ_MODELO
    limpio = re.sub(r"[#•✅❌⚠️🎉📌]", "", texto)[:800].strip()
    if not limpio:
        return b""
    r = requests.post(
        URL.format(m="gemini-2.5-flash-preview-tts"),
        params={"key": config.GEMINI_API_KEY},
        json={
            "contents": [{"parts": [{"text": limpio}]}],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voz}}}
            }
        },
        timeout=60,
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


def interpretar_comando(texto, pendientes):
    """Entiende lo que TÚ le dices (por voz o texto) y lo convierte en una acción."""
    lista = "\n".join(f"#{t['id']} | {t['canal']} | {t['remitente']} | "
                      f"{(t.get('analisis') or {}).get('resumen_tarea', t.get('asunto', ''))} | {t['estado']}"
                      for t in pendientes) or "(no hay tareas pendientes)"
    prompt = f"""{config.TU_NOMBRE} (tu jefe) te dice:
<<<
{texto}
>>>

TAREAS PENDIENTES DE REVISIÓN:
{lista}

Decide qué quiere y devuelve JSON:
{{
  "accion": "nueva_tarea | listar | ver | aprobar | rechazar | corregir | ayuda | conversar",
  "tarea_id": null,
  "texto": "",
  "respuesta": ""
}}
- nueva_tarea: te pide que hagas algo nuevo (redactar, hacer un Excel, un Word...). "texto" = la tarea completa tal cual la pidió.
- listar: quiere saber qué hay pendiente.
- ver: quiere que le leas/muestres una tarea.
- aprobar: quiere enviar una tarea. rechazar: descartarla.
- corregir: quiere cambios en una tarea; "texto" = las indicaciones exactas de corrección.
- ayuda: pregunta qué puedes hacer. conversar: cualquier otra cosa; "respuesta" = tu respuesta breve.
- "tarea_id": número de la tarea a la que se refiere (si dice "la última", "la de Laura", etc., dedúcelo de la lista; si no se puede saber, null).
No inventes números de tarea que no estén en la lista."""
    return _llamar(prompt, 0.0)


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
