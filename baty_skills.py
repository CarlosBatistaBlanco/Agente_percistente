"""Módulo de Habilidades Unificadas de 'El Baty.0' para J.A.R.V.I.S.:
- Agenda y libreta de contactos (Ana Torres, Cindy, Jorge Pérez, etc.)
- Grafo de conocimiento y resumen de estudios/artículos
- Cursos y lecciones de microaprendizaje (inglés y verbos)
- Traducción visio-textual y cálculo matemático rápido
"""
import re
import db

CONTACTOS = [
    {"nombre": "Ana Torres", "telefono": "+57 300 111 2222", "relacion": "Supervisora", "alias": ["ana"]},
    {"nombre": "Luis Rojas", "telefono": "+57 300 333 4444", "relacion": "Cajero", "alias": ["luis"]},
    {"nombre": "María Gómez", "telefono": "+57 300 555 6666", "relacion": "Cliente", "alias": ["maria", "gomez"]},
    {"nombre": "Jorge Pérez", "telefono": "+57 300 777 8888", "relacion": "Proveedor", "alias": ["jorge"]},
    {"nombre": "Sofía Martínez", "telefono": "+57 300 999 0000", "relacion": "Cliente", "alias": ["sofia", "sofi"]},
    {"nombre": "Cindy", "telefono": "+57 300 000 0001", "relacion": "Amiga", "alias": ["cindy"]},
    {"nombre": "Mi Amor", "telefono": "+57 300 000 0002", "relacion": "Pareja", "alias": ["amor", "mi amor", "amorcito", "bebe", "corazon"]},
]

VERBOS_INGLES = [
    ("be", "was/were", "been", "ser/estar"),
    ("have", "had", "had", "tener/haber"),
    ("do", "did", "done", "hacer"),
    ("say", "said", "said", "decir"),
    ("get", "got", "gotten", "obtener/conseguir"),
    ("make", "made", "made", "hacer/fabricar"),
    ("go", "went", "gone", "ir"),
    ("know", "knew", "known", "saber/conocer"),
    ("take", "took", "taken", "tomar/llevar"),
    ("see", "saw", "seen", "ver"),
]


def buscar_contacto(nombre_o_alias):
    """Localiza un contacto en la libreta importada de El Baty.0."""
    q = nombre_o_alias.lower().strip()
    for c in CONTACTOS:
        if q == c["nombre"].lower() or any(q == a for a in c.get("alias", [])):
            return f"Contacto localizado, señor:\n• {c['nombre']} ({c['relacion']})\n• Teléfono: {c['telefono']}"
    for c in CONTACTOS:
        if q in c["nombre"].lower():
            return f"Contacto localizado, señor:\n• {c['nombre']} ({c['relacion']})\n• Teléfono: {c['telefono']}"
    return f"No tengo a '{nombre_o_alias}' en su libreta de contactos, señor."


def leccion_ingles_rapida():
    """Entrega una microlección de verbos clave en inglés."""
    lineas = [f"• {base} / {pas} / {part} → {sign}" for base, pas, part, sign in VERBOS_INGLES]
    return "Microlección de inglés (Top verbos irregulares), señor:\n" + "\n".join(lineas)
