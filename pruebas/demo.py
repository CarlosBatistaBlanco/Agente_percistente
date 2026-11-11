"""Crea una tarea de ejemplo (ya procesada) para ver cómo luce el panel sin usar la IA."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db, ejecutores  # noqa: E401,E402

db.init()
mensaje = ("Hola, buenas tardes. ¿Me puedes mandar hoy un presupuesto en Excel para la oficina? "
           "Necesito 5 sillas a $1,200 cada una, 2 escritorios a $3,500 y 1 impresora a $4,800. "
           "Agrega el IVA del 16% y el total. Gracias. - Laura (Compras)")
tid = db.crear("correo", "demo-1", "laura.compras@empresa.com", "laura.compras@empresa.com",
               "Presupuesto mobiliario oficina", mensaje, "")
if not tid:
    print("La tarea de ejemplo ya existe")
    sys.exit()
plan = {"es_tarea": True, "resumen_tarea": "Presupuesto en Excel de mobiliario con IVA 16% y total",
        "requisitos": ["Formato Excel", "5 sillas a $1,200", "2 escritorios a $3,500",
                       "1 impresora a $4,800", "Calcular IVA 16%", "Calcular total", "Entregar hoy"],
        "tipo_entregable": "excel", "nombre_archivo": "presupuesto_mobiliario",
        "datos_faltantes": [], "confianza": 96}
resultado = {
    "mensaje_respuesta": "Hola Laura, buenas tardes.\n\nTe envío adjunto el presupuesto del mobiliario "
                         "solicitado (5 sillas, 2 escritorios y 1 impresora) con el IVA del 16% y el total.\n\n"
                         "Quedo atento a cualquier ajuste.\n\nSaludos.",
    "hojas": [{"nombre": "Presupuesto", "encabezados": ["Concepto", "Cantidad", "Precio unitario", "Importe"],
               "filas": [["Silla", 5, 1200, "=B2*C2"], ["Escritorio", 2, 3500, "=B3*C3"],
                         ["Impresora", 1, 4800, "=B4*C4"], ["", "", "Subtotal", "=SUM(D2:D4)"],
                         ["", "", "IVA 16%", "=D5*0.16"], ["", "", "TOTAL", "=D5+D6"]],
               "anchos": [18, 12, 18, 14]}]}
ver = {"cumple": True, "puntuacion": 97, "requisitos": [
    {"requisito": r, "cumplido": True, "nota": n} for r, n in [
        ("Formato Excel", "archivo .xlsx"), ("5 sillas a $1,200", "= $6,000"),
        ("2 escritorios a $3,500", "= $7,000"), ("1 impresora a $4,800", "= $4,800"),
        ("Calcular IVA 16%", "$17,800 × 16% = $2,848"), ("Calcular total", "$20,648"),
        ("Entregar hoy", "listo para enviar")]],
    "problemas": [], "datos_inventados": [], "pendientes": []}
archivo = ejecutores.ejecutar(plan, resultado, tid)
db.actualizar(tid, analisis=plan, resultado=resultado, verificacion=ver, archivo=archivo,
              respuesta=resultado["mensaje_respuesta"], estado="pendiente_revision")
print("Tarea de ejemplo creada: #", tid)
