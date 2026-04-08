# agent/main.py — Servidor FastAPI + Webhook + Polling de WhatsApp
# Generado por AgentKit

"""
Servidor principal del agente de WhatsApp para Crecimiento Exponencial.
Usa webhook como método principal y polling como respaldo para no perder mensajes.
"""

import os
import asyncio
import logging
import httpx
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse
from dotenv import load_dotenv

from agent.brain import generar_respuesta
from agent.memory import inicializar_db, guardar_mensaje, obtener_historial
from agent.providers import obtener_proveedor
from agent.tools import extraer_etiqueta_imagenes, obtener_imagenes_red

# Cargar .env desde la raíz del proyecto
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_project_root, ".env"), override=True)

# Configuración de logging según entorno
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
log_level = logging.DEBUG if ENVIRONMENT == "development" else logging.INFO
logging.basicConfig(level=log_level)
logger = logging.getLogger("agentkit")

# Proveedor de WhatsApp (se configura en .env con WHATSAPP_PROVIDER)
proveedor = obtener_proveedor()
PORT = int(os.getenv("PORT", 8000))

# Set para rastrear mensajes ya procesados (evita duplicados entre webhook y polling)
mensajes_procesados: set[str] = set()
MAX_PROCESADOS = 5000  # Limpiar set cuando crezca mucho


async def procesar_mensaje(telefono: str, texto: str, mensaje_id: str, tiene_imagen: bool = False):
    """Procesa un mensaje entrante: genera respuesta y la envía."""
    # Evitar duplicados
    if mensaje_id in mensajes_procesados:
        return
    mensajes_procesados.add(mensaje_id)

    # Limpiar set si crece mucho
    if len(mensajes_procesados) > MAX_PROCESADOS:
        mensajes_procesados.clear()

    logger.info(f"Mensaje de {telefono}: {texto}")

    # Obtener historial ANTES de guardar el mensaje actual
    historial = await obtener_historial(telefono)

    # Generar respuesta con Claude
    respuesta = await generar_respuesta(texto, historial)

    # Guardar mensaje del usuario Y respuesta del agente en memoria
    await guardar_mensaje(telefono, "user", texto)
    await guardar_mensaje(telefono, "assistant", respuesta)

    # Enviar respuesta por WhatsApp (soporta múltiples mensajes e imágenes)
    await enviar_respuesta_multiple(telefono, respuesta)

    logger.info(f"Respuesta a {telefono} enviada")


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
        if red_social and i == 0:
            imagenes = obtener_imagenes_red(red_social)
            for img_ruta in imagenes:
                await proveedor.enviar_imagen(telefono, img_ruta)
                logger.info(f"Imagen enviada: {os.path.basename(img_ruta)}")
                await asyncio.sleep(1)

        # Pequeña pausa entre mensajes para que lleguen en orden
        if i < len(partes) - 1:
            await asyncio.sleep(0.5)


async def polling_whapi():
    """
    Consulta mensajes nuevos directamente a la API de Whapi cada 10 segundos.
    Respaldo para cuando el webhook no funciona.
    """
    token = os.getenv("WHAPI_TOKEN")
    if not token:
        logger.warning("WHAPI_TOKEN no configurado — polling desactivado")
        return

    logger.info("Polling de mensajes activado (cada 10 segundos)")
    ultimo_timestamp = 0

    while True:
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    "https://gate.whapi.cloud/messages/list",
                    params={"count": 10},
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=15.0,
                )
                if r.status_code == 200:
                    data = r.json()
                    for msg in data.get("messages", []):
                        # Solo mensajes entrantes (no propios) con texto
                        if msg.get("from_me"):
                            continue

                        msg_id = msg.get("id", "")
                        timestamp = msg.get("timestamp", 0)

                        # Solo procesar mensajes nuevos
                        if timestamp <= ultimo_timestamp:
                            continue
                        if msg_id in mensajes_procesados:
                            continue

                        texto = ""
                        if msg.get("text"):
                            texto = msg["text"].get("body", "")
                        elif msg.get("image"):
                            texto = msg["image"].get("caption", "[imagen]")
                            if not texto:
                                texto = "[imagen]"

                        if not texto:
                            continue

                        telefono = msg.get("chat_id", "")
                        ultimo_timestamp = max(ultimo_timestamp, timestamp)

                        # Procesar en background para no bloquear el polling
                        asyncio.create_task(
                            procesar_mensaje(telefono, texto, msg_id)
                        )

        except Exception as e:
            logger.error(f"Error en polling: {e}")

        await asyncio.sleep(10)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicializa la base de datos y el polling al arrancar."""
    await inicializar_db()
    logger.info("Base de datos inicializada")
    logger.info(f"Servidor AgentKit corriendo en puerto {PORT}")
    logger.info(f"Proveedor de WhatsApp: {proveedor.__class__.__name__}")

    # Iniciar polling como tarea en background
    polling_task = asyncio.create_task(polling_whapi())

    yield

    # Cancelar polling al cerrar
    polling_task.cancel()


app = FastAPI(
    title="AgentKit — Crecimiento Exponencial",
    version="1.0.0",
    lifespan=lifespan
)


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
    Recibe mensajes de WhatsApp via webhook.
    Sigue funcionando en paralelo con el polling.
    """
    try:
        mensajes = await proveedor.parsear_webhook(request)

        for msg in mensajes:
            if msg.es_propio or not msg.texto:
                continue

            await procesar_mensaje(msg.telefono, msg.texto, msg.mensaje_id, msg.tiene_imagen)

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Error en webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))
