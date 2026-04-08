# agent/tools.py — Herramientas del agente
# Generado por AgentKit

"""
Herramientas específicas de Crecimiento Exponencial.
Maneja el envío de imágenes de precios según la red social del cliente.
"""

import os
import re
import logging

logger = logging.getLogger("agentkit")

# Directorio donde están las imágenes de precios
KNOWLEDGE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "knowledge")

# Mapeo de red social → imágenes de precios
IMAGENES_POR_RED = {
    "instagram": [
        "instagram-seguidores.jpg",
        "instagram-likes.JPG",
        "instagram-views.JPG",
    ],
    "tiktok": [
        "tiktok-seguidores.JPG",
        "tiktok-likes.JPG",
        "tiktok-views.JPG",
        "tiktok-comentarios.JPG",
        "tiktok-compartidos.JPG",
        "tiktok-guardados.JPG",
    ],
    "facebook": [
        "facebook-seguidores.JPG",
        "facebook-likes.JPG",
        "facebook-views.JPG",
    ],
    "youtube": [
        "youtube-suscriptores.JPG",
        "youtube-views.JPG",
        "youtube-views monetizables.JPG",
        "youtube-horas de reproduccion.JPG",
        "youtube-likes.JPG",
    ],
    "spotify": [
        "spotify-reproducciones con garantia.JPG",
        "spotify-reproducciones sin garantia.JPG",
        "spotify-seguidores.JPG",
        "spotify-oyentes mensuales.JPG",
    ],
    "telegram": [
        "telegram-miembros.JPG",
    ],
}

# Aliases para detectar la red social en el mensaje
ALIASES_RED = {
    "instagram": ["instagram", "insta", "ig"],
    "tiktok": ["tiktok", "tik tok", "tt"],
    "facebook": ["facebook", "fb", "face"],
    "youtube": ["youtube", "yt", "you tube"],
    "spotify": ["spotify", "spoti"],
    "telegram": ["telegram", "tg"],
}


def detectar_red_social(texto: str) -> str | None:
    """
    Detecta qué red social menciona el cliente en su mensaje.
    Retorna el nombre normalizado o None si no detecta ninguna.
    """
    texto_lower = texto.lower()
    for red, aliases in ALIASES_RED.items():
        for alias in aliases:
            if alias in texto_lower:
                return red
    return None


def obtener_imagenes_red(red_social: str) -> list[str]:
    """
    Retorna las rutas completas de las imágenes de precios para una red social.
    Solo incluye las que existen en disco.
    """
    imagenes = IMAGENES_POR_RED.get(red_social, [])
    rutas = []
    for img in imagenes:
        ruta = os.path.join(KNOWLEDGE_DIR, img)
        if os.path.exists(ruta):
            rutas.append(ruta)
        else:
            logger.warning(f"Imagen no encontrada: {ruta}")
    return rutas


def extraer_etiqueta_imagenes(respuesta: str) -> tuple[str, str | None]:
    """
    Busca la etiqueta [ENVIAR_IMAGENES:red_social] en la respuesta de Claude.
    Retorna (respuesta_sin_etiqueta, red_social) o (respuesta_original, None).
    """
    patron = r"\[ENVIAR_IMAGENES:(\w+)\]"
    match = re.search(patron, respuesta)
    if match:
        red = match.group(1).lower()
        respuesta_limpia = re.sub(patron, "", respuesta).strip()
        return respuesta_limpia, red
    return respuesta, None
