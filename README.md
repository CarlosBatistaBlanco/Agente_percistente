# 🤖 Agente persistente de tareas

**Detecta → Analiza → Ejecuta → Verifica → Te muestra → (tú apruebas) → Envía**

Vigila tu **correo**, **Telegram** y **WhatsApp**. Cuando llega una tarea, la entiende, la resuelve
(respuesta, **Excel** o **Word**), la revisa con un segundo paso de control de calidad y te la muestra.
**Nada se envía sin tu aprobación.**

## Cómo evita equivocarse
1. **Analiza primero**: saca la lista de requisitos exactos y su nivel de confianza.
2. **No inventa**: si faltan datos, pone `[PENDIENTE]` o te prepara una pregunta para el remitente.
3. **Verificador independiente**: otra pasada de la IA revisa requisito por requisito, sumas y fórmulas;
   si falla, lo corrige solo (hasta `MAX_REINTENTOS`).
4. **Tú decides**: panel con checklist ✔/✘, puedes editar el texto, reemplazar el archivo,
   pedir que lo regenere con indicaciones, o rechazar.

## Instalación (Windows)
1. Instala Python 3.10+ (marca "Add to PATH").
2. Doble clic en `iniciar.bat` (crea el entorno, instala todo y copia `.env.example` → `.env`).
3. Edita `.env`: como mínimo `GEMINI_API_KEY` (gratis en https://aistudio.google.com/apikey) y `TU_NOMBRE`.
4. Vuelve a abrir `iniciar.bat`. El panel abre en http://127.0.0.1:5000
5. Prueba pegando un mensaje en "Probar / crear tarea manual".

Para que arranque solo al prender la PC: `Win+R` → `shell:startup` → pega ahí un acceso directo a `iniciar.bat`.

## Conectar canales
| Canal | Qué necesitas | Nota |
|---|---|---|
| **Gmail** | Verificación en 2 pasos + [Contraseña de aplicación](https://myaccount.google.com/apppasswords) | Lee no leídos sin marcarlos |
| **Outlook** | IMAP habilitado (algunas cuentas de empresa lo bloquean) | Cambia hosts en `.env` |
| **Telegram** | Bot de @BotFather → token. Escríbele `/start` para saber tu `chat_id` | El bot recibe lo que le escriben **a él** (o lo que tú le reenvías). Te avisa con botones ✅/❌ para aprobar desde el celular |
| **WhatsApp** | WhatsApp Business **Cloud API** de Meta (número de empresa) + URL pública (ej. `ngrok http 5000`) | Webhook: `https://TU-URL/webhook/whatsapp`. WhatsApp personal no tiene API oficial |

> ⚠️ Si expones el panel con ngrok, pon `PANEL_CLAVE` en `.env`.

## Archivos
- `agente.py` – orquestador persistente (hilos de vigilancia + cola + envío)
- `ia.py` – los 3 pasos con Gemini: analizar, resolver, verificar
- `ejecutores.py` – crea Excel/Word y lee adjuntos (.xlsx, .docx, .txt, .csv)
- `panel.py` – panel web de revisión
- `canales/` – correo, telegram, whatsapp
- `GEMA_instrucciones.md` – texto para crear la Gema en gemini.google.com
- `tareas.db` – historial (memoria) · `salidas/` – archivos generados
