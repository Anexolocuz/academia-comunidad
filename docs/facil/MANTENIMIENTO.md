# 🔧 Mantenimiento — versión fácil

> Todo el detalle: [manual completo](../MANTENIMIENTO.md)

| Cada | Haz esto |
|---|---|
| Semana | **Respaldo:** Ajustes → Tus datos → ⬇️ Descargar (o copia la carpeta `datos/`) |
| Mes | **Actualizar:** Ajustes → Avanzado → ⬇️ Actualizar ahora (Docker: `docker compose pull && docker compose up -d`) |
| Mes | Lee tu **📄 Reporte** |

## Reiniciar la Academia

- **Linux:** `systemctl --user restart academia`
- **Windows / Mac:** reinicia el PC (arranca sola).
- **Docker:** `docker compose restart academia`

Mejor cuando la barra de arriba diga que la IA está libre.

## Cambiar de PC

1. Instala la Academia en el PC nuevo.
2. Copia tu carpeta `datos/` del viejo al nuevo.
3. Reinicia. Todo sigue igual.
