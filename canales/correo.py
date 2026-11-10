"""Canal de correo: lee correos no leídos por IMAP (sin marcarlos) y responde por SMTP."""
import datetime
import email
import imaplib
import mimetypes
import os
import re
import smtplib
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.utils import parseaddr

import config
from ejecutores import extraer_texto

_MESES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _dec(s):
    try:
        return str(make_header(decode_header(s or "")))
    except Exception:
        return s or ""


def _html_a_texto(h):
    h = re.sub(r"(?is)<(script|style).*?</\1>", "", h)
    h = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>", "\n", h)
    h = re.sub(r"<[^>]+>", "", h)
    return re.sub(r"\n\s*\n+", "\n\n", h).strip()


def _contenido(msg):
    plano, html, adjuntos = "", "", []
    for parte in msg.walk():
        if parte.is_multipart():
            continue
        nombre = parte.get_filename()
        datos = parte.get_payload(decode=True) or b""
        if nombre:
            adjuntos.append(extraer_texto(_dec(nombre), datos))
            continue
        charset = parte.get_content_charset() or "utf-8"
        texto = datos.decode(charset, errors="replace")
        if parte.get_content_type() == "text/plain":
            plano += texto
        elif parte.get_content_type() == "text/html":
            html += texto
    cuerpo = plano.strip() or _html_a_texto(html)
    return cuerpo + ("\n\n" + "\n\n".join(adjuntos) if adjuntos else "")


def revisar():
    """Devuelve lista de dicts con los correos no leídos de los últimos 3 días."""
    nuevos = []
    M = imaplib.IMAP4_SSL(config.IMAP_HOST, config.IMAP_PORT)
    try:
        M.login(config.CORREO_USUARIO, config.CORREO_PASSWORD)
        M.select("INBOX", readonly=True)  # readonly: no marca como leído
        d = datetime.date.today() - datetime.timedelta(days=3)
        desde = f"{d.day:02d}-{_MESES[d.month - 1]}-{d.year}"
        _, data = M.search(None, "UNSEEN", "SINCE", desde)
        for num in data[0].split():
            _, md = M.fetch(num, "(BODY.PEEK[])")
            msg = email.message_from_bytes(md[0][1])
            remitente = parseaddr(msg.get("From", ""))[1].lower()
            if not remitente or remitente == config.CORREO_USUARIO.lower():
                continue
            permitidos = config.CORREO_REMITENTES_PERMITIDOS
            if permitidos and remitente not in permitidos and \
                    ("@" + remitente.split("@")[-1]) not in permitidos:
                continue
            if config.CORREO_IGNORAR_BOLETINES and (msg.get("List-Unsubscribe") or
                                                    msg.get("Precedence", "").lower() in ("bulk", "list")):
                continue
            mid = (msg.get("Message-ID") or f"<{num.decode()}-{remitente}>").strip()
            nuevos.append({
                "id_externo": mid,
                "remitente": remitente,
                "destino": msg.get("Reply-To") and parseaddr(msg.get("Reply-To"))[1] or remitente,
                "asunto": _dec(msg.get("Subject", "")),
                "mensaje": _contenido(msg),
                "referencia": mid,
            })
    finally:
        try:
            M.logout()
        except Exception:
            pass
    return nuevos


def enviar(destino, asunto, texto, archivo="", referencia=""):
    m = EmailMessage()
    m["From"] = config.CORREO_USUARIO
    m["To"] = destino
    asunto = asunto or ""
    m["Subject"] = asunto if asunto.lower().startswith(("re:", "rv:")) else f"Re: {asunto}"
    if referencia:
        m["In-Reply-To"] = referencia
        m["References"] = referencia
    m.set_content(texto)
    if archivo and os.path.exists(archivo):
        tipo, _ = mimetypes.guess_type(archivo)
        principal, sub = (tipo or "application/octet-stream").split("/", 1)
        with open(archivo, "rb") as f:
            nombre = os.path.basename(archivo).split("_", 1)[-1]
            m.add_attachment(f.read(), maintype=principal, subtype=sub, filename=nombre)
    if config.SMTP_PORT == 465:
        with smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT) as s:
            s.login(config.CORREO_USUARIO, config.CORREO_PASSWORD)
            s.send_message(m)
    else:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT) as s:
            s.starttls()
            s.login(config.CORREO_USUARIO, config.CORREO_PASSWORD)
            s.send_message(m)
