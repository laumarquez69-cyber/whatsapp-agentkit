# agent/providers/whapi.py — Adaptador para Whapi.cloud
# Generado por AgentKit

import os
import base64
import logging
import httpx
from fastapi import Request
from agent.providers.base import ProveedorWhatsApp, MensajeEntrante

logger = logging.getLogger("agentkit")


class ProveedorWhapi(ProveedorWhatsApp):
    """Proveedor de WhatsApp usando Whapi.cloud (REST API simple)."""

    def __init__(self):
        self.token = os.getenv("WHAPI_TOKEN")
        self.base_url = "https://gate.whapi.cloud"

    async def parsear_webhook(self, request: Request) -> list[MensajeEntrante]:
        """Parsea el payload de Whapi.cloud."""
        body = await request.json()
        mensajes = []
        for msg in body.get("messages", []):
            # Detectar si el mensaje tiene imagen (comprobante de pago)
            tiene_imagen = msg.get("type") == "image" or "image" in msg
            texto = ""
            if msg.get("text"):
                texto = msg["text"].get("body", "")
            elif msg.get("image"):
                texto = msg["image"].get("caption", "[imagen]")
                if not texto:
                    texto = "[imagen]"

            mensajes.append(MensajeEntrante(
                telefono=msg.get("chat_id", ""),
                texto=texto,
                mensaje_id=msg.get("id", ""),
                es_propio=msg.get("from_me", False),
                tiene_imagen=tiene_imagen,
            ))
        return mensajes

    async def enviar_mensaje(self, telefono: str, mensaje: str) -> bool:
        """Envía mensaje de texto via Whapi.cloud."""
        if not self.token:
            logger.warning("WHAPI_TOKEN no configurado — mensaje no enviado")
            return False
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{self.base_url}/messages/text",
                json={"to": telefono, "body": mensaje},
                headers=headers,
            )
            if r.status_code != 200:
                logger.error(f"Error Whapi texto: {r.status_code} — {r.text}")
            return r.status_code == 200

    async def enviar_imagen(self, telefono: str, ruta_imagen: str, caption: str = "") -> bool:
        """Envía una imagen via Whapi.cloud usando base64."""
        if not self.token:
            logger.warning("WHAPI_TOKEN no configurado — imagen no enviada")
            return False

        # Leer la imagen y convertir a base64
        try:
            with open(ruta_imagen, "rb") as f:
                imagen_bytes = f.read()
            imagen_b64 = base64.b64encode(imagen_bytes).decode("utf-8")
        except FileNotFoundError:
            logger.error(f"Imagen no encontrada: {ruta_imagen}")
            return False

        # Determinar el tipo MIME
        ext = ruta_imagen.lower().rsplit(".", 1)[-1]
        mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}.get(ext, "image/jpeg")

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        payload = {
            "to": telefono,
            "media": f"data:{mime};base64,{imagen_b64}",
        }
        if caption:
            payload["caption"] = caption

        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                f"{self.base_url}/messages/image",
                json=payload,
                headers=headers,
            )
            if r.status_code != 200:
                logger.error(f"Error Whapi imagen: {r.status_code} — {r.text}")
            return r.status_code == 200
