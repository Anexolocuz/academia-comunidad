# 🐳 Docker — versión fácil

> Todo el detalle: [manual completo](../DOCKER.md)

**Necesitas:** Docker Desktop (Windows/Mac) o Docker (Linux): https://docs.docker.com/get-docker/

## Pasos

1. Descarga la Academia (ZIP o `git clone`) y entra a la carpeta.
2. Arranca el asistente:
   - Linux/Mac: `./docker/arrancar.sh`
   - Windows: clic derecho en `docker\arrancar.ps1` → **Ejecutar con PowerShell**
3. Responde:
   - **¿IA dentro de Docker?** → `s` si no tienes Ollama en el PC.
   - **¿Usar tu tarjeta gráfica?** → `s` si te la detecta.
   - **¿Buscador web?** → `s` (lecciones con fuentes actuales).
   - **¿Descargar el modelo?** → `s` (unos 3 GB).
4. Abre **http://127.0.0.1:8092** → ⚙️ Ajustes → 🪄 **Escanear mi PC** → **Aplicar**.

## Lo de todos los días

| Quiero | Comando |
|---|---|
| Actualizar | `docker compose pull && docker compose up -d` |
| Apagar | `docker compose down` |
| Ver qué pasa | `docker compose logs -f academia` |

Tus datos quedan guardados aunque apagues o actualices.
