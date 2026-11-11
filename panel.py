"""Panel web de revisión: aquí VES lo que hizo el agente y decides Aprobar / Corregir / Rechazar."""
import os
import time

from flask import (Flask, Response, abort, jsonify, redirect, render_template_string, request,
                   send_file)

import config
import db

BASE = """<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Agente de tareas</title>
<style>
body{font-family:Segoe UI,Arial,sans-serif;background:#f3f5f9;margin:0;color:#1d2433}
header{background:#1f4e78;color:#fff;padding:14px 24px;display:flex;justify-content:space-between;align-items:center}
header a{color:#fff;text-decoration:none;font-weight:600}
main{max-width:1100px;margin:20px auto;padding:0 16px}
.card{background:#fff;border-radius:10px;padding:18px;margin-bottom:16px;box-shadow:0 1px 4px #0001}
table{width:100%;border-collapse:collapse}td,th{padding:8px;border-bottom:1px solid #eee;text-align:left;font-size:14px}
.b{padding:3px 9px;border-radius:12px;font-size:12px;font-weight:600;white-space:nowrap}
.pendiente_revision{background:#fff3cd}.necesita_aclaracion{background:#e2d9f3}.enviada{background:#d1e7dd}
.rechazada,.ignorada{background:#e9ecef}.error{background:#f8d7da}.nueva,.analizando{background:#cfe2ff}
pre{white-space:pre-wrap;background:#f7f7f9;padding:12px;border-radius:8px;font-size:13px;max-height:380px;overflow:auto}
textarea{width:100%;box-sizing:border-box;font-family:inherit;font-size:14px;padding:10px;border-radius:8px;border:1px solid #ccc}
button{border:0;border-radius:8px;padding:10px 16px;font-weight:600;cursor:pointer;margin:6px 6px 0 0}
.ok{background:#198754;color:#fff}.no{background:#dc3545;color:#fff}.re{background:#0d6efd;color:#fff}
.ck{margin:4px 0}.si{color:#198754}.nn{color:#dc3545}.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media(max-width:800px){.grid{grid-template-columns:1fr}}
#mic{position:fixed;right:24px;bottom:24px;width:68px;height:68px;border-radius:50%;font-size:30px;
background:#1f4e78;color:#fff;box-shadow:0 4px 14px #0004;margin:0}
#mic.rec{background:#dc3545;animation:pulso 1s infinite}
@keyframes pulso{50%{transform:scale(1.1)}}
#vozEstado{position:fixed;right:104px;bottom:30px;max-width:420px;background:#fff;padding:12px 16px;
border-radius:12px;box-shadow:0 4px 14px #0003;font-size:14px;white-space:pre-wrap;display:none}
.mini{padding:4px 10px;background:#e9ecef;font-size:16px}
</style></head><body><header><a href="/">🤖 Agente de tareas</a><span>{{ ahora }}</span></header><main>
{% block c %}{% endblock %}</main>
<button id="mic" title="Activar escucha continua (Wake word: Jarvis)" onclick="alternarVoz()">🎤</button>
<script>
const NOMBRE_ASISTENTE = "{{ nombre_asistente }}";
const IDIOMA = "{{ idioma }}";
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
window.ocupado = false;
function estado(t){const e=document.getElementById('vozEstado');e.style.display=t?'block':'none';e.textContent=t;}
function hablar(t){
  if(!window.speechSynthesis) return null;
  speechSynthesis.cancel();
  const u=new SpeechSynthesisUtterance(t.replace(/#/g,'número ').replace(/[•✅❌⚠️🎉📌]/g,''));
  u.lang=IDIOMA; u.rate=1.05;
  const v=speechSynthesis.getVoices().find(x=>x.lang&&x.lang.startsWith(IDIOMA.slice(0,2)));
  if(v) u.voice=v;
  speechSynthesis.speak(u); return u;
}
function escuchar(cb){
  if(!SR){alert('Tu navegador no soporta reconocimiento de voz. Usa Google Chrome o Microsoft Edge.');return;}
  const r=new SR(); r.lang=IDIOMA; r.interimResults=false; r.maxAlternatives=1;
  const b=document.getElementById('mic'); b.classList.add('rec'); window.ocupado=true;
  r.onresult=e=>cb(e.results[0][0].transcript);
  r.onerror=e=>{window.ocupado=false;estado('No te escuché ('+e.error+'). Revisa el permiso del micrófono.');};
  r.onend=()=>b.classList.remove('rec');
  r.start();
}
function dictar(id){escuchar(t=>{const el=document.getElementById(id);el.value=(el.value?el.value+' ':'')+t;window.ocupado=false;});}
let reconocimientoActivo = null;
let escuchandoContinuo = false;

function iniciarEscuchaContinua(){
  if(!SR) return;
  if(reconocimientoActivo){try{reconocimientoActivo.stop()}catch(e){}}
  const r = new SR();
  r.lang = IDIOMA;
  r.continuous = true;
  r.interimResults = false;
  r.onresult = async e => {
    const ultimo = e.results[e.results.length - 1][0].transcript.trim();
    const patron = new RegExp('^'+NOMBRE_ASISTENTE+'[\\\\s,:]*(.*)$', 'i');
    const m = ultimo.match(patron);
    if(m){
      const comando = m[1].trim() || 'hola';
      estado('🎙️ Activado por: "' + ultimo + '"\\n⏳ Procesando...');
      try{
        const resp = await fetch('/voz', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({texto: comando})
        });
        const d = await resp.json();
        estado(d.texto);
        const u = hablar(d.texto);
        if(d.ir_a && location.pathname !== d.ir_a){
          const ir = () => { location = d.ir_a; };
          if(u){ u.onend = ir; } else { setTimeout(ir, 2500); }
        }
      }catch(err){ estado('Error: ' + err); }
    }
  };
  r.onerror = e => { if(e.error!=='no-speech') console.log('Escucha continua:', e.error); };
  r.onend = () => { if(escuchandoContinuo) try{r.start();}catch(e){} };
  try{ r.start(); escuchandoContinuo = true; reconocimientoActivo = r; }catch(e){}
}

function alternarVoz(){
  const b = document.getElementById('mic');
  if(escuchandoContinuo){
    escuchandoContinuo = false;
    if(reconocimientoActivo){try{reconocimientoActivo.stop();}catch(e){}}
    b.classList.remove('rec');
    estado('');
  } else {
    b.classList.add('rec');
    estado('🟢 Modo ' + NOMBRE_ASISTENTE + ' ACTIVO.\\nDiga "' + NOMBRE_ASISTENTE + ', [su orden]..." en cualquier momento.');
    iniciarEscuchaContinua();
  }
}
</script></body></html>"""

LISTA = BASE.replace("{% block c %}{% endblock %}", """
<div class="card"><h3>Probar / crear tarea manual <button type="button" class="mini" onclick="dictar('msgNueva')" title="Dictar">🎤</button></h3>
<p><small>Escribe, dicta con 🎤, o presiona el botón azul de abajo a la derecha para <b>hablar con el agente</b>
(ej. "¿qué tengo pendiente?", "léeme la tarea 1", "hazme un Excel con...").</small></p>
<form method="post" action="/nueva">
<textarea id="msgNueva" name="mensaje" rows="4" placeholder="Pega aquí un mensaje o tarea para probar el agente..."></textarea>
<button class="re">Procesar</button></form></div>
<div class="card"><h3>Tareas</h3><table>
<tr><th>#</th><th>Canal</th><th>De</th><th>Qué se pide</th><th>Estado</th><th>Fecha</th></tr>
{% for t in tareas %}<tr onclick="location='/tarea/{{t.id}}'" style="cursor:pointer">
<td>{{t.id}}</td><td>{{t.canal}}</td><td>{{t.remitente[:40]}}</td>
<td>{{ (t.analisis or {}).get('resumen_tarea', t.asunto or '')[:80] if t.analisis is mapping else (t.asunto or '') }}</td>
<td><span class="b {{t.estado}}">{{t.estado.replace('_',' ')}}</span></td><td>{{t.creado}}</td></tr>
{% else %}<tr><td colspan="6">Aún no hay tareas.</td></tr>{% endfor %}
</table></div><script>setInterval(()=>{if(!window.ocupado && !document.getElementById('msgNueva').value && !speechSynthesis.speaking) location.reload()},20000)</script>""")

DETALLE = BASE.replace("{% block c %}{% endblock %}", """
{% set a = t.analisis if t.analisis is mapping else {} %}{% set v = t.verificacion if t.verificacion is mapping else {} %}
<div class="card"><h2>Tarea #{{t.id}} <span class="b {{t.estado}}">{{t.estado.replace('_',' ')}}</span></h2>
<b>Canal:</b> {{t.canal}} · <b>De:</b> {{t.remitente}} · <b>Asunto:</b> {{t.asunto}} · {{t.creado}}</div>
<div class="grid">
<div class="card"><h3>📥 Mensaje original</h3><pre>{{t.mensaje}}</pre></div>
<div class="card"><h3>🧠 Lo que entendió</h3>
<p><b>{{a.get('resumen_tarea','')}}</b></p>
<p>Entregable: <b>{{a.get('tipo_entregable','')}}</b> · Confianza: <b>{{a.get('confianza','-')}}%</b></p>
{% if a.get('datos_faltantes') %}<p class="nn"><b>Datos faltantes:</b> {{ a.datos_faltantes|join(', ') }}</p>{% endif %}
<b>Requisitos detectados:</b><ul>{% for r in a.get('requisitos',[]) %}<li>{{r}}</li>{% endfor %}</ul></div>
</div>
{% if v %}<div class="card"><h3>🔎 Verificación de calidad: {% if v.get('cumple') %}<span class="si">CUMPLE</span>{% else %}<span class="nn">REVISAR</span>{% endif %} ({{v.get('puntuacion','-')}}/100)</h3>
{% for r in v.get('requisitos',[]) %}<div class="ck">{% if r.cumplido %}<span class="si">✔</span>{% else %}<span class="nn">✘</span>{% endif %} {{r.requisito}} <small>{{r.nota}}</small></div>{% endfor %}
{% for p in v.get('problemas',[]) %}<div class="ck nn">⚠ {{p}}</div>{% endfor %}
{% for p in v.get('datos_inventados',[]) %}<div class="ck nn">🚫 Dato inventado: {{p}}</div>{% endfor %}
{% for p in v.get('pendientes',[]) %}<div class="ck">📝 Completar: {{p}}</div>{% endfor %}</div>{% endif %}
{% if t.error %}<div class="card"><h3 class="nn">Error</h3><pre>{{t.error}}</pre></div>{% endif %}
{% if t.archivo %}<div class="card"><h3>📎 Archivo generado</h3>
<a href="/tarea/{{t.id}}/archivo">⬇ Descargar {{ t.archivo.split('\\\\')[-1].split('/')[-1] }}</a>
<p><small>Ábrelo, revísalo y si lo corriges puedes subir tu versión abajo antes de aprobar.</small></p></div>{% endif %}
{% if t.estado in ('pendiente_revision','necesita_aclaracion') %}
<div class="card"><h3>{% if t.estado=='necesita_aclaracion' %}❓ Pregunta al remitente (faltan datos){% else %}✉️ Respuesta que se enviará{% endif %}
<button type="button" class="mini" onclick="leerTarea()" title="Escuchar">🔊</button>
<button type="button" class="mini" onclick="dictar('txtResp')" title="Dictar">🎤</button></h3>
<form method="post" action="/tarea/{{t.id}}/aprobar" enctype="multipart/form-data">
<textarea id="txtResp" name="respuesta" rows="10">{{t.respuesta or ''}}</textarea>
{% if t.archivo %}<p>Reemplazar archivo (opcional): <input type="file" name="archivo"></p>{% endif %}
<button class="ok" onclick="return confirm('¿Enviar a {{t.destino}} por {{t.canal}}?')">✅ Aprobar y enviar</button></form>
<form method="post" action="/tarea/{{t.id}}/rechazar" style="display:inline"><button class="no">❌ Rechazar</button></form></div>
{% endif %}
{% if t.estado not in ('enviada',) %}<div class="card"><h3>🔁 Corregir y regenerar
<button type="button" class="mini" onclick="dictar('txtCorr')" title="Dictar corrección">🎤</button></h3>
<form method="post" action="/tarea/{{t.id}}/regenerar">
<textarea id="txtCorr" name="instrucciones" rows="3" placeholder="Ej: la tabla debe tener columna de IVA; el tono más formal; usa los precios del adjunto..."></textarea>
<button class="re">Regenerar con estas indicaciones</button></form></div>{% endif %}
<script>
function leerTarea(){
  const v = {{ v|tojson }};
  let t = "Tarea {{t.id}}, de {{t.remitente|e}}. Se pidió: {{ a.get('resumen_tarea','')|e }}. ";
  if (v && v.requisitos) t += v.cumple ? "La verificación dice que cumple todo. " : "Ojo, la verificación encontró problemas. ";
  const r = document.getElementById('txtResp'); if (r) t += "La respuesta propuesta es: " + r.value;
  hablar(t);
}
</script>
{% if t.estado in ('nueva','analizando') %}<script>setTimeout(()=>{if(!window.ocupado)location.reload()},5000)</script>{% endif %}""")


def crear_app(cola, enviar_tarea, registrar, comando=None):
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024

    @app.before_request
    def autenticar():
        if request.path.startswith("/webhook") or request.path == "/health" or not config.PANEL_CLAVE:
            return None
        a = request.authorization
        if not a or a.username != config.PANEL_USUARIO or a.password != config.PANEL_CLAVE:
            return Response("Acceso restringido", 401, {"WWW-Authenticate": 'Basic realm="Agente"'})
        return None

    @app.context_processor
    def globales():
        return {"idioma": config.VOZ_IDIOMA_PANEL,
                "nombre_asistente": config.NOMBRE_ASISTENTE}

    def ahora():
        return db.ahora()

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"}), 200

    @app.get("/")
    def inicio():
        return render_template_string(LISTA, tareas=db.listar(), ahora=ahora())

    @app.get("/tarea/<int:tid>")
    def detalle(tid):
        t = db.obtener(tid) or abort(404)
        return render_template_string(DETALLE, t=t, ahora=ahora())

    @app.get("/tarea/<int:tid>/archivo")
    def archivo(tid):
        t = db.obtener(tid) or abort(404)
        if not t.get("archivo") or not os.path.exists(t["archivo"]):
            abort(404)
        return send_file(t["archivo"], as_attachment=True,
                         download_name=os.path.basename(t["archivo"]).split("_", 1)[-1])

    @app.post("/tarea/<int:tid>/aprobar")
    def aprobar(tid):
        t = db.obtener(tid) or abort(404)
        f = request.files.get("archivo")
        if f and f.filename and t.get("archivo"):
            ext = os.path.splitext(t["archivo"])[1]
            nueva = os.path.splitext(t["archivo"])[0] + "_revisado" + ext
            f.save(nueva)
            db.actualizar(tid, archivo=nueva)
        try:
            enviar_tarea(tid, request.form.get("respuesta"))
        except Exception as e:
            db.actualizar(tid, error=f"Error al enviar: {e}")
        return redirect(f"/tarea/{tid}")

    @app.post("/tarea/<int:tid>/rechazar")
    def rechazar(tid):
        db.actualizar(tid, estado="rechazada")
        return redirect("/")

    @app.post("/tarea/<int:tid>/regenerar")
    def regenerar(tid):
        t = db.obtener(tid) or abort(404)
        nuevas = request.form.get("instrucciones", "").strip()
        extra = "\n".join(filter(None, [t.get("instrucciones_extra"), nuevas]))
        db.actualizar(tid, instrucciones_extra=extra, estado="nueva")
        cola.put(tid)
        return redirect(f"/tarea/{tid}")

    @app.post("/nueva")
    def nueva():
        msg = request.form.get("mensaje", "").strip()
        if msg:
            tid = registrar("manual", f"manual-{time.time()}", "Yo (prueba manual)", "",
                            "Tarea manual", msg)
            return redirect(f"/tarea/{tid}")
        return redirect("/")

    @app.post("/voz")
    def voz():
        texto = ((request.get_json(silent=True) or {}).get("texto") or "").strip()
        if not texto:
            return jsonify({"texto": "No escuché nada, intenta de nuevo."})
        if not comando:
            return jsonify({"texto": "El asistente de voz no está disponible."})
        try:
            r = comando(texto, "panel")
        except Exception as e:
            r = {"texto": f"Tuve un problema: {e}"}
        return jsonify({"texto": r.get("texto", ""), "ir_a": r.get("ir_a")})

    return app
