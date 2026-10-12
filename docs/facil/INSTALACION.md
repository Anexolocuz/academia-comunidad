# 🧰 Instalación — versión fácil

> Todo el detalle: [manual completo](../INSTALACION.md)

## Antes de empezar

- Un PC tuyo: Windows 10/11, Mac o Linux. Mejor con 16 GB de RAM (sirve con 8).
- Una IA local: **Ollama** (https://ollama.com/download) y un modelo: `ollama pull gemma3:4b`.

## Pasos

1. **Descarga** la Academia (ZIP de Releases o `git clone`).
2. **Abre el instalador:**
   - Windows → **INSTALAR.bat** (si falta Python, lo instala; luego ábrelo otra vez).
   - Mac → **Instalar.command**.
   - Linux → `./instalar.sh`.
3. **«¿Escanear este PC?»** → `s`. Revisa tu PC (no tus archivos) y el resultado se borra solo en 24 h.
4. **«¿Aplicar esta configuración?»** → `s`.
5. **Tu nombre de perfil** → Enter o escríbelo.
6. **¿Celular?** → `s` si tienes Tailscale (ver [CELULAR](CELULAR.md)).
7. Se abre **http://127.0.0.1:8092**. ¡Listo! Arranca sola cada vez que prendes el PC.

**¿Sin preguntas?** Usa `--auto`: `./instalar.sh --auto` o `INSTALAR.bat --auto`.

## Si no tienes IA todavía

Puedes instalar igual. Después: instala Ollama, baja el modelo, y en la Academia ve a
⚙️ Ajustes → 🪄 **Escanear mi PC** → **Aplicar**.

## Desinstalar

Respaldar primero la carpeta `datos/` (ahí está tu progreso). Luego los pasos de tu sistema en el [manual completo](../INSTALACION.md#desinstalar).
