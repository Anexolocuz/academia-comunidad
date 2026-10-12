# 📱 Celular, tablet y otros sistemas — versión fácil

> Todo el detalle: [manual completo](../DISPOSITIVOS.md)

La Academia **vive en tu PC**; el celular solo la abre (la IA no corre en el celular).

## Con Tailscale (recomendado: seguro y funciona fuera de casa)

1. Instala **Tailscale** en el PC y en el celular: https://tailscale.com/download (misma cuenta).
2. En el PC, en una terminal: `tailscale serve --bg --https=15443 http://127.0.0.1:8092`
3. En el celular abre: `https://<nombre-de-tu-pc>.<tu-red>.ts.net:15443`
   (el 🪄 escaneo de Ajustes te dice la dirección exacta).

## Sin Tailscale (solo en tu casa)

1. En `datos/configuracion.json` pon `"host": "0.0.0.0"` y `"clave_acceso": "una frase larga"`. Reinicia la Academia.
2. Si Windows pregunta por el cortafuegos: permite solo **Redes privadas**.
3. En el celular: `http://<IP-de-tu-PC>:8092` y escribe la clave.

## Que se vea como app

- **Android:** menú ⋮ → **Instalar app**.
- **iPhone/iPad:** Compartir → **Agregar a inicio**.

## Tablet con lápiz

Ajustes → Básico → marca **«solo lápiz»** para que el dedo no raye el cuaderno.

## ¿Qué sistemas sirven?

PC con **Windows, Mac o Linux** (también Raspberry Pi 5). Para usarla: **cualquier** celular, tablet o navegador moderno.
