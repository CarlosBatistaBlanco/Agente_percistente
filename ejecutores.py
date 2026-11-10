"""Ejecutores: convierten el resultado de la IA en archivos reales (Excel / Word)
y extraen texto de archivos adjuntos recibidos."""
import io
import os
import re

from docx import Document
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill

import config


def _nombre(base, tid, ext):
    base = re.sub(r"[^\w\-]+", "_", base or "documento").strip("_")[:60] or "documento"
    return os.path.join(config.SALIDAS_DIR, f"{tid}_{base}.{ext}")


def _valor(v):
    if isinstance(v, str):
        s = v.strip()
        if s.startswith("="):
            return s
        try:
            if re.fullmatch(r"-?\d+", s):
                return int(s)
            if re.fullmatch(r"-?\d+\.\d+", s):
                return float(s)
        except ValueError:
            pass
    return v


def crear_excel(resultado, nombre, tid):
    wb = Workbook()
    wb.remove(wb.active)
    for i, hoja in enumerate(resultado.get("hojas") or [{}]):
        ws = wb.create_sheet((hoja.get("nombre") or f"Hoja{i + 1}")[:31])
        enc = hoja.get("encabezados") or []
        if enc:
            ws.append(enc)
            for c in ws[1]:
                c.font = Font(bold=True, color="FFFFFF")
                c.fill = PatternFill("solid", fgColor="1F4E78")
                c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            ws.freeze_panes = "A2"
        for fila in hoja.get("filas") or []:
            ws.append([_valor(v) for v in fila])
        anchos = hoja.get("anchos") or []
        for col in ws.columns:
            idx = col[0].column - 1
            letra = col[0].column_letter
            if idx < len(anchos) and anchos[idx]:
                ws.column_dimensions[letra].width = anchos[idx]
            else:
                largo = max((len(str(c.value)) for c in col if c.value is not None), default=8)
                ws.column_dimensions[letra].width = min(max(10, largo + 2), 60)
    ruta = _nombre(nombre, tid, "xlsx")
    wb.save(ruta)
    return ruta


def crear_word(resultado, nombre, tid):
    doc = Document()
    if resultado.get("titulo"):
        doc.add_heading(resultado["titulo"], level=0)
    for sec in resultado.get("secciones") or []:
        if sec.get("titulo"):
            doc.add_heading(sec["titulo"], level=1)
        for p in sec.get("parrafos") or []:
            if p:
                doc.add_paragraph(p)
        for v in sec.get("vinetas") or []:
            if v:
                doc.add_paragraph(v, style="List Bullet")
        tabla = sec.get("tabla") or {}
        enc, filas = tabla.get("encabezados") or [], [f for f in (tabla.get("filas") or []) if f]
        if enc:
            t = doc.add_table(rows=1, cols=len(enc))
            t.style = "Table Grid"
            for i, h in enumerate(enc):
                t.rows[0].cells[i].text = str(h)
                for r in t.rows[0].cells[i].paragraphs[0].runs:
                    r.bold = True
            for f in filas:
                celdas = t.add_row().cells
                for i, v in enumerate(f[:len(enc)]):
                    celdas[i].text = "" if v is None else str(v)
    ruta = _nombre(nombre, tid, "docx")
    doc.save(ruta)
    return ruta


def ejecutar(plan, resultado, tid):
    """Devuelve la ruta del archivo generado, o '' si la tarea es solo texto."""
    tipo = plan.get("tipo_entregable")
    nombre = plan.get("nombre_archivo") or "documento"
    if tipo == "excel" and resultado.get("hojas"):
        return crear_excel(resultado, nombre, tid)
    if tipo == "word" and resultado.get("secciones"):
        return crear_word(resultado, nombre, tid)
    return ""


def extraer_texto(nombre, datos: bytes, limite=15000):
    """Lee el contenido de adjuntos (xlsx, docx, txt, csv) para que la IA lo entienda."""
    n = (nombre or "").lower()
    try:
        if n.endswith((".xlsx", ".xlsm")):
            wb = load_workbook(io.BytesIO(datos), data_only=False)
            partes = []
            for ws in wb.worksheets:
                partes.append(f"--- Hoja: {ws.title} ---")
                for fila in ws.iter_rows(values_only=True):
                    if any(v is not None for v in fila):
                        partes.append(" | ".join("" if v is None else str(v) for v in fila))
            texto = "\n".join(partes)
        elif n.endswith(".docx"):
            d = Document(io.BytesIO(datos))
            texto = "\n".join(p.text for p in d.paragraphs)
            for t in d.tables:
                for r in t.rows:
                    texto += "\n" + " | ".join(c.text for c in r.cells)
        elif n.endswith((".txt", ".csv", ".md", ".json")):
            texto = datos.decode("utf-8", errors="replace")
        else:
            return f"[Adjunto '{nombre}' (formato no leído automáticamente)]"
    except Exception as e:
        return f"[No se pudo leer el adjunto '{nombre}': {e}]"
    return f"[ADJUNTO: {nombre}]\n{texto[:limite]}"
