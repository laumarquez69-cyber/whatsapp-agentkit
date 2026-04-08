# agent/main.py — Servidor FastAPI + Webhook de WhatsApp
# Generado por AgentKit

"""
Servidor principal del agente de WhatsApp para Crecimiento Exponencial.
Funciona con cualquier proveedor (Whapi, Meta, Twilio) gracias a la capa de providers.
Soporta envío de múltiples mensajes y de imágenes de precios.
"""

import os
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse
from dotenv import load_dotenv

from agent.brain import generar_respuesta
from agent.memory import inicializar_db, guardar_mensaje, obtener_historial
from agent.providers import obtener_proveedor
from agent.tools import extraer_etiqueta_imagenes, obtener_imagenes_red

load_dotenv()

# Configuración de logging según entorno
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
log_level = logging.DEBUG if ENVIRONMENT == "development" else logging.INFO
logging.basicConfig(level=log_level)
logger = logging.getLogger("agentkit")

# Proveedor de WhatsApp (se configura en .env con WHATSAPP_PROVIDER)
proveedor = obtener_proveedor()
PORT = int(os.getenv("PORT", 8000))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicializa la base de datos al arrancar el servidor."""
    await inicializar_db()
    logger.info("Base de datos inicializada")
    logger.info(f"Servidor AgentKit corriendo en puerto {PORT}")
    logger.info(f"Proveedor de WhatsApp: {proveedor.__class__.__name__}")
    yield


app = FastAPI(
    title="AgentKit — Crecimiento Exponencial",
    version="1.0.0",
    lifespan=lifespan
)


async def enviar_respuesta_multiple(telefono: str, respuesta: str):
    """
    Envía la respuesta al cliente. Si contiene el separador ---,
    la divide en múltiples mensajes individuales.
    También detecta la etiqueta [ENVIAR_IMAGENES:red] para enviar imágenes.
    """
    # Primero extraer la etiqueta de imágenes si existe
    respuesta, red_social = extraer_etiqueta_imagenes(respuesta)

    # Dividir por el separador --- en múltiples mensajes
    partes = [p.strip() for p in respuesta.split("---") if p.strip()]

    for i, parte in enumerate(partes):
        await proveedor.enviar_mensaje(telefono, parte)
        logger.info(f"Mensaje {i+1}/{len(partes)} enviado a {telefono}")

        # Si hay imágenes para enviar, las mandamos después del primer mensaje
        # (o después del mensaje "Perfecto!" que es el primero del paso 3)
        if red_social and i == 0:
            imagenes = obtener_imagenes_red(red_social)
            for img_ruta in imagenes:
                await proveedor.enviar_imagen(telefono, img_ruta)
                logger.info(f"Imagen enviada: {os.path.basename(img_ruta)}")
                # Pequeña pausa entre imágenes para no saturar la API
                await asyncio.sleep(1)

        # Pequeña pausa entre mensajes para que lleguen en orden
        if i < len(partes) - 1:
            await asyncio.sleep(0.5)


@app.get("/")
async def health_check():
    """Endpoint de salud para Railway/monitoreo."""
    return {"status": "ok", "service": "agentkit-crecimiento-exponencial"}


@app.get("/webhook")
async def webhook_verificacion(request: Request):
    """Verificación GET del webhook (requerido por Meta Cloud API, no-op para otros)."""
    resultado = await proveedor.validar_webhook(request)
    if resultado is not None:
        return PlainTextResponse(str(resultado))
    return {"status": "ok"}


@app.post("/webhook")
async def webhook_handler(request: Request):
    """
    Recibe mensajes de WhatsApp via el proveedor configurado.
    Procesa el mensaje, genera respuesta con Claude y la envía de vuelta.
    """
    try:
        # Parsear webhook — el proveedor normaliza el formato
        mensajes = await proveedor.parsear_webhook(request)

        for msg in mensajes:
            # Ignorar mensajes propios o vacíos
            if msg.es_propio or not msg.texto:
                continue

            logger.info(f"Mensaje de {msg.telefono}: {msg.texto}")

            # Obtener historial ANTES de guardar el mensaje actual
            historial = await obtener_historial(msg.telefono)

            # Generar respuesta con Claude
            respuesta = await generar_respuesta(msg.texto, historial)

            # Guardar mensaje del usuario Y respuesta del agente en memoria
            await guardar_mensaje(msg.telefono, "user", msg.texto)
            await guardar_mensaje(msg.telefono, "assistant", respuesta)

            # Enviar respuesta por WhatsApp (soporta múltiples mensajes e imágenes)
            await enviar_respuesta_multiple(msg.telefono, respuesta)

            logger.info(f"Respuesta a {msg.telefono} enviada")

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Error en webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))
