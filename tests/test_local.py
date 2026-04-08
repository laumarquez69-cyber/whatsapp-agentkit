# tests/test_local.py — Simulador de chat en terminal
# Generado por AgentKit

"""
Prueba tu agente sin necesitar WhatsApp.
Simula una conversación en la terminal.
Muestra las imágenes que se enviarían y los mensajes múltiples.
"""

import asyncio
import sys
import os

# Agregar el directorio raíz al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.brain import generar_respuesta
from agent.memory import inicializar_db, guardar_mensaje, obtener_historial, limpiar_historial
from agent.tools import extraer_etiqueta_imagenes, obtener_imagenes_red

TELEFONO_TEST = "test-local-001"


async def main():
    """Loop principal del chat de prueba."""
    await inicializar_db()

    print()
    print("=" * 55)
    print("   AgentKit — Test Local")
    print("   Agente: Franco | Crecimiento Exponencial")
    print("=" * 55)
    print()
    print("  Escribe mensajes como si fueras un cliente.")
    print("  Comandos especiales:")
    print("    'limpiar'  — borra el historial")
    print("    'salir'    — termina el test")
    print()
    print("-" * 55)
    print()

    while True:
        try:
            mensaje = input("Cliente: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\nTest finalizado.")
            break

        if not mensaje:
            continue

        if mensaje.lower() == "salir":
            print("\nTest finalizado.")
            break

        if mensaje.lower() == "limpiar":
            await limpiar_historial(TELEFONO_TEST)
            print("[Historial borrado]\n")
            continue

        # Obtener historial ANTES de guardar
        historial = await obtener_historial(TELEFONO_TEST)

        # Generar respuesta
        respuesta = await generar_respuesta(mensaje, historial)

        # Detectar imágenes a enviar
        respuesta_limpia, red_social = extraer_etiqueta_imagenes(respuesta)

        # Dividir en mensajes múltiples
        partes = [p.strip() for p in respuesta_limpia.split("---") if p.strip()]

        print()
        for i, parte in enumerate(partes):
            print(f"Franco: {parte}")
            print()

            # Mostrar imágenes después del primer mensaje si corresponde
            if red_social and i == 0:
                imagenes = obtener_imagenes_red(red_social)
                if imagenes:
                    print(f"  [📸 Enviando {len(imagenes)} imágenes de {red_social.upper()}]")
                    for img in imagenes:
                        print(f"    → {os.path.basename(img)}")
                    print()

        # Guardar en historial
        await guardar_mensaje(TELEFONO_TEST, "user", mensaje)
        await guardar_mensaje(TELEFONO_TEST, "assistant", respuesta)


if __name__ == "__main__":
    asyncio.run(main())
