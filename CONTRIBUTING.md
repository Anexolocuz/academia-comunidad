# 🤝 Cómo aportar

¡Gracias! La Academia es de la comunidad. Todo aporte se publica bajo la licencia del proyecto (AGPL-3.0-or-later).

## Ideas fáciles para empezar

| Aporte | Dónde | Guía |
|---|---|---|
| 🎨 Una paleta de colores | `web/temas/*.json` + `index.json` | [APARIENCIA.md](docs/APARIENCIA.md) |
| 📚 Un área o temas nuevos | `curriculo/<area>.json` | [CONFIGURACION.md → Contenido](docs/CONFIGURACION.md) |
| 🌍 Fuentes de noticias confiables | `config/fuentes.json` | idem |
| 🌐 Traducir la interfaz o los manuales | `web/app.js`, `docs/` | abre un issue para coordinar |
| 🐛 Arreglos y mejoras | `app/`, `web/` | [ARQUITECTURA.md](docs/ARQUITECTURA.md) |

## Reglas del proyecto

1. **Cero dependencias**: solo la biblioteca estándar de Python y JS sin frameworks (lo de `web/vendor/` va incluido).
2. **Local y privado**: nada de servicios en la nube, telemetría ni CDNs. Lo que salga a internet se documenta en
   [SEGURIDAD_Y_DATOS.md](docs/SEGURIDAD_Y_DATOS.md).
3. **Todo por cuenta**: cada perfil solo ve lo suyo. Ninguna lista fija de áreas en el código.
4. **No romper datos**: cambios de la base solo con `MIGRACIONES` en `app/base.py`; no reordenar temas existentes.
5. **Fácil para todos**: si cambias cómo se instala, se configura o se usa, actualiza la versión **fácil** y la
   **completa** del manual.
6. Funciona en **Windows, macOS y Linux**, y en celular.

## Antes del pull request

```bash
ACADEMIA_DATOS=/tmp/prueba ACADEMIA_PUERTO=8099 python3 app/servidor.py   # prueba a mano, sin tus datos
python3 pruebas/humo.py                                                   # debe salir «✅ Todo bien»
```

Añade una línea en `CHANGELOG.md` bajo `## [Sin publicar]`. No incluyas datos personales (correos, IPs, nombres de
equipos) ni contenido de tu carpeta `datos/`.
