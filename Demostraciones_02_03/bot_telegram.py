"""Canal de Telegram de AnimaBot Veterinaria. Colocar junto a chatbot_memoria.py y consulta_llm.py.

Solo consultas: servicios, precios, horarios, disponibilidad y consulta de citas por código.
Las operaciones de escritura (reservar, modificar, cancelar) no se ejecutan desde este canal."""

import asyncio
import json
import logging
import os
from getpass import getpass
from urllib.error import HTTPError, URLError

from telegram import Update
from telegram.error import InvalidToken, NetworkError, TelegramError
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from chatbot_memoria import nuevo_historial, procesar_turno

BIENVENIDA = (
    "¡Hola! Soy AnimaBot, el asistente de AnimaBot Veterinaria 🐾\n"
    "Puedo contarte sobre nuestros servicios, precios y horarios de atención, "
    "y consultar los horarios libres para tu mascota.\n"
    "Escribe /help para ver ejemplos."
)
AYUDA = (
    "/start: mostrar la bienvenida.\n"
    "/help: ver esta ayuda.\n"
    "/reset: reiniciar esta conversación.\n\n"
    "Puedes preguntarme, por ejemplo:\n"
    "• ¿Qué servicios ofrecen y cuánto cuestan?\n"
    "• ¿Cuánto cuesta la vacunación?\n"
    "• ¿Qué horarios y dónde atienden?\n"
    "• ¿Qué horas libres hay para consulta general el viernes?\n"
    "• Consultar una cita con su código (empieza por AB-).\n\n"
    "Servicios: consulta general, vacunación, desparasitación, peluquería y baño, cirugía menor.\n"
    "En esta versión las operaciones de reserva, cambio o cancelación de citas quedan sin ejecutar."
)
CIERRE_DESCARTE = (
    {"role": "user", "content": "Descartar la solicitud pendiente."},
    {"role": "assistant", "content": "Solicitud descartada; no se ejecutó la operación."},
)


async def enviar_texto(mensaje, texto):
    for inicio in range(0, len(texto), 4000):
        await mensaje.reply_text(texto[inicio:inicio + 4000])


async def iniciar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_message is not None:
        context.chat_data.setdefault("historial", nuevo_historial())
        await enviar_texto(update.effective_message, BIENVENIDA)


async def ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_message is not None:
        await enviar_texto(update.effective_message, AYUDA)


async def reiniciar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_message is not None:
        context.chat_data["historial"] = nuevo_historial()
        await enviar_texto(
            update.effective_message,
            "Conversación reiniciada. Dime qué deseas consultar. Las reservas del negocio se conservan.",
        )


def sin_markdown(texto):
    # Los mensajes se envían como texto plano: se quitan los ** que usa el módulo del chatbot.
    return str(texto).replace("**", "")


def formatear_resultado(resultado, plan):
    mensaje = sin_markdown(resultado.get("mensaje") or "")
    if resultado.get("tipo") == "confirmacion":
        # Se conserva el resumen de la solicitud y se descarta la última línea ("Pulsa Confirmar..."),
        # porque Telegram no tiene botones para confirmar en esta versión.
        resumen = mensaje.split("\n\nPulsa")[0].strip()
        return (
            f"{resumen}\n\n"
            "Esta versión de Telegram solo atiende consultas. "
            "La operación no se ejecutó y no se guardó ningún cambio en las citas."
        )
    if mensaje:
        return mensaje
    datos = resultado.get("datos")
    if plan.get("accion") == "disponibilidad" and isinstance(datos, dict) and "horarios" in datos:
        horas = ", ".join(datos["horarios"]) or "Sin horarios disponibles"
        return f"Horarios libres:\n{horas}"
    return json.dumps(datos, ensure_ascii=False, indent=2)


async def recibir_texto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mensaje = update.effective_message
    if mensaje is None or not mensaje.text or not mensaje.text.strip():
        return
    clave = context.bot_data.get("clave_modelo", "")
    modelo = context.bot_data.get("modelo", "")
    if not clave or not modelo:
        await enviar_texto(mensaje, "Falta configurar GROQ_API_KEY o GROQ_MODEL en el servidor del bot.")
        return
    historial = context.chat_data.get("historial")
    if historial is None:
        historial = nuevo_historial()
    try:
        resultado, actualizado, plan = await asyncio.to_thread(
            procesar_turno, mensaje.text.strip(), historial, clave, modelo
        )
        texto = formatear_resultado(resultado, plan)
    except HTTPError:
        await enviar_texto(mensaje, "El servicio rechazó la consulta. Revisa la configuración o los datos.")
        return
    except (URLError, TimeoutError):
        await enviar_texto(mensaje, "No pude completar la conexión. Intenta la consulta más tarde.")
        return
    except (ValueError, KeyError, IndexError, TypeError):
        await enviar_texto(mensaje, "La respuesta del servicio no tiene el formato esperado.")
        return
    if resultado.get("tipo") == "confirmacion":
        # Nunca se llama a ejecutar(..., confirmar=True). Se cierra la operación en el historial,
        # igual que "Descartar" en Gradio, para que no contamine las consultas siguientes.
        actualizado = actualizado + [dict(m) for m in CIERRE_DESCARTE]
    context.chat_data["historial"] = actualizado
    await enviar_texto(mensaje, texto)


async def comando_desconocido(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await enviar_texto(update.effective_message, "No conozco ese comando. Usa /start, /help o /reset.")


async def otro_mensaje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await enviar_texto(update.effective_message, "Por ahora recibo consultas escritas. Envíame un mensaje de texto.")


async def informar_error(update, context):
    # Registramos la clase del error sin imprimir credenciales ni URL del bot.
    logging.error("Error del bot: %s", type(context.error).__name__)


def registrar_handlers(aplicacion):
    privado = filters.ChatType.PRIVATE
    aplicacion.add_handler(CommandHandler("start", iniciar, filters=privado))
    aplicacion.add_handler(CommandHandler("help", ayuda, filters=privado))
    aplicacion.add_handler(CommandHandler("reset", reiniciar, filters=privado))
    aplicacion.add_handler(
        MessageHandler(privado & filters.TEXT & ~filters.COMMAND, recibir_texto)
    )
    aplicacion.add_handler(MessageHandler(privado & filters.COMMAND, comando_desconocido))
    aplicacion.add_handler(MessageHandler(privado & ~filters.TEXT, otro_mensaje))
    aplicacion.add_error_handler(informar_error)


def main():
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip() or getpass("Token de BotFather (oculto): ").strip()
    if not token:
        print("Necesito el token de Telegram para iniciar.")
        return
    try:
        aplicacion = Application.builder().token(token).build()
        aplicacion.bot_data["clave_modelo"] = os.getenv("GROQ_API_KEY", "").strip()
        aplicacion.bot_data["modelo"] = os.getenv("GROQ_MODEL", "").strip()
        registrar_handlers(aplicacion)
        if not aplicacion.bot_data["clave_modelo"] or not aplicacion.bot_data["modelo"]:
            print("Los comandos funcionarán. Configura GROQ_API_KEY y GROQ_MODEL para las consultas.")
        print("Bot en ejecución. Abre su conversación en Telegram. Para detenerlo: Ctrl+C.")
        aplicacion.run_polling(allowed_updates=["message"])
    except InvalidToken:
        print("Token inválido. Comprueba la credencial entregada por BotFather.")
    except NetworkError:
        print("No fue posible iniciar la conexión con Telegram. Revisa Internet e inténtalo otra vez.")
    except TelegramError as error:
        print(f"Telegram no completó el inicio: {type(error).__name__}.")


if __name__ == "__main__":
    main()
