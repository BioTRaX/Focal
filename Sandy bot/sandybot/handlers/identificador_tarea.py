# Nombre de archivo: identificador_tarea.py
# Ubicación de archivo: Sandy bot/sandybot/handlers/identificador_tarea.py
# User-provided custom instructions
"""Flujo para identificar tareas programadas desde correos .MSG."""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.helpers import escape_markdown

from ..email_utils import procesar_correo_a_tarea
from ..registrador import responder_registrando
from ..utils import obtener_mensaje
from .estado import UserState
from .procesar_correos import _leer_msg

logger = logging.getLogger(__name__)


async def iniciar_identificador_tarea(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Solicita el correo .MSG o .TXT a analizar."""
    mensaje = obtener_mensaje(update)
    if not mensaje:
        logger.warning("No se recibió mensaje en iniciar_identificador_tarea")
        return

    user_id = update.effective_user.id
    UserState.set_mode(user_id, "identificador_tarea")
    context.user_data.clear()
    await responder_registrando(
        mensaje,
        user_id,
        "identificador_tarea",
        "📎 Adjuntá el archivo *.MSG* o *.TXT* del mantenimiento.\n"
        "No hace falta escribir nada más, yo me encargo del resto 😉",
        "identificador_tarea",
    )


async def procesar_identificador_tarea(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Procesa el .MSG recibido y registra la tarea."""
    mensaje = obtener_mensaje(update)
    if not mensaje or not mensaje.document:
        logger.warning("No se recibió documento en procesar_identificador_tarea")
        return

    user_id = mensaje.from_user.id
    partes = (mensaje.text or "").split()
    cliente = partes[0] if partes else "METROTEL"
    carrier = partes[1] if len(partes) > 1 else None

    nombre = mensaje.document.file_name or ""
    archivo = await mensaje.document.get_file()
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        await archivo.download_to_drive(tmp.name)
        ruta = tmp.name

    try:
        if nombre.lower().endswith(".msg"):
            contenido = _leer_msg(ruta)
            if not contenido:
                await responder_registrando(
                    mensaje,
                    user_id,
                    nombre,
                    "Instalá la librería 'extract-msg' para leer archivos .MSG.",
                    "identificador_tarea",
                )
                os.remove(ruta)
                return
        elif nombre.lower().endswith(".txt"):
            contenido = Path(ruta).read_text(encoding="utf-8", errors="ignore")
            if not contenido:
                await responder_registrando(
                    mensaje,
                    user_id,
                    nombre,
                    "El archivo está vacío o no pude leerlo.",
                    "identificador_tarea",
                )
                os.remove(ruta)
                return
        else:
            await responder_registrando(
                mensaje,
                user_id,
                nombre,
                "Solo se admiten archivos .msg o .txt.",
                "identificador_tarea",
            )
            os.remove(ruta)
            return

        (
            tarea,
            creada_nueva,
            ids_pendientes,
            carrier_detectado,
        ) = await procesar_correo_a_tarea(
            contenido,
            cliente,
            carrier,
            generar_msg=False,
        )
    except ValueError as exc:
        logger.error("Fallo identificando tarea: %s", exc)
        await responder_registrando(
            mensaje,
            user_id,
            nombre,
            "No pude identificar la tarea en el correo. Podés cargarla "
            "manualmente con /ingresar_tarea",
            "identificador_tarea",
        )
        os.remove(ruta)
        return
    except Exception as exc:  # pragma: no cover
        logger.error("Fallo identificando tarea: %s", exc)
        await responder_registrando(
            mensaje,
            user_id,
            nombre,
            "No pude identificar la tarea en el correo.",
            "identificador_tarea",
        )
        os.remove(ruta)
        return
    finally:
        if os.path.exists(ruta):
            os.remove(ruta)
    carrier_nombre = "Sin carrier"
    servicios_txt = ""
    if tarea.carrier_id:
        from ..database import Carrier, Servicio, SessionLocal, TareaServicio

        with SessionLocal() as s:
            car = s.get(Carrier, tarea.carrier_id)
            if car:
                carrier_nombre = car.nombre
            servicios_ids = [
                ts.servicio_id
                for ts in s.query(TareaServicio).filter(
                    TareaServicio.tarea_id == tarea.id
                )
            ]
            servicios_pares = []
            for sid in servicios_ids:
                srv = s.get(Servicio, sid)
                if srv:
                    propio = str(srv.id) if srv.id else ""
                    car = srv.id_carrier or ""
                    servicios_pares.append(f"{propio} , {car}")
            servicios_txt = "; ".join(servicios_pares)

    if creada_nueva:
        detalle = f"✅ *Tarea Registrada ID: {tarea.id}*\n"
    else:
        interno = tarea.id_interno or "N/D"
        detalle = f"🔄 La tarea {interno} ya estaba registrada (ID BD: {tarea.id})\n"

    carrier_md = escape_markdown(carrier_nombre, version=1)
    tipo_md = escape_markdown(tarea.tipo_tarea, version=1)
    detalle += (
        f"ID Carrier: {tarea.id_interno or 'N/D'}\n"
        f"• Carrier: {carrier_md}\n"
        f"• Tipo   : {tipo_md}\n"
        f"• Inicio : {tarea.fecha_inicio} UTC-3\n"
        f"• Fin    : {tarea.fecha_fin} UTC-3\n"
    )
    if tarea.tiempo_afectacion:
        detalle += f"• Afectación: {tarea.tiempo_afectacion}\n"
    if tarea.descripcion:
        desc_md = escape_markdown(tarea.descripcion, version=1)
        detalle += f"• Descripción: {desc_md}\n"
    if servicios_txt:
        detalle += f"• Servicio afectado: {servicios_txt}\n"
    if ids_pendientes:
        detalle += f"⚠️ *Servicios pendientes*: {', '.join(ids_pendientes)}"

    await update.message.reply_text(detalle, parse_mode="Markdown")
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("Sí", callback_data="carrier_manual_si"), InlineKeyboardButton("No", callback_data="carrier_manual_no")]]
    )
    await responder_registrando(
        mensaje,
        user_id,
        nombre,
        "¿Querés ingresar el carrier manualmente?",
        "identificador_tarea",
        reply_markup=keyboard,
    )
    context.user_data["tarea_carrier"] = tarea.id
    context.user_data["carrier_detectado"] = carrier_detectado or carrier_nombre
    context.user_data["esperando_carrier_confirm"] = True
