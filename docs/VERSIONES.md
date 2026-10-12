# 🏷️ Versiones y actualizaciones (manual completo)

> ¿Prefieres lo corto? → [Versión fácil](facil/VERSIONES.md)

## Una sola versión para todo

El número de versión vive en **un solo archivo: `VERSION`** (formato `MAYOR.MENOR.PARCHE`, p. ej. `1.0.0`). De ahí
salen, siempre iguales:

| Dónde | Cómo se ve |
|---|---|
| La app | Ajustes → Avanzado → 🧩 Esta instalación · cabecera `Server: Academia/1.0.0` · `GET /api/version` |
| El instalador | «Instalador de la Academia v1.0.0» |
| Git | etiqueta `v1.0.0` |
| Docker | `ghcr.io/anexolocuz/academia-comunidad:v1.0.0` (y `latest`) |
| Descarga sin Git | GitHub Releases → `academia-v1.0.0.zip` |
| Qué cambió | [CHANGELOG.md](../CHANGELOG.md) → sección `## [1.0.0]` |

Al publicar una etiqueta, GitHub comprueba que coincide con `VERSION`, construye la imagen Docker (x86 y ARM),
crea la versión con sus notas sacadas del CHANGELOG y adjunta el ZIP. Si no coinciden, no publica nada.

**Qué número sube:** PARCHE = arreglos · MENOR = funciones nuevas compatibles · MAYOR = cambios que piden hacer algo
al actualizar (se explica en el CHANGELOG). Las bases de datos viejas se migran solas al arrancar (`app/base.py`,
`MIGRACIONES`): nunca hace falta borrar tus datos.

## Actualizar

| Instalación | Cómo |
|---|---|
| Con Git (instalador) | botón **⬇️ Actualizar ahora** en Ajustes → Avanzado, o `./actualizar.sh` / `ACTUALIZAR.bat` |
| Docker | `docker compose pull && docker compose up -d` (fijar versión: `ACADEMIA_VERSION` en `.env`) |
| ZIP | descarga el nuevo de Releases, descomprímelo y copia tu carpeta `datos/` dentro |

Ninguna actualización toca `datos/`.

## Cómo se mantiene sincronizado el proyecto (para quien lo mantiene)

El proyecto tiene un repositorio de trabajo y el repositorio público. `privado/publicar.sh` (en el de trabajo)
publica cada versión:

1. Exige que no haya cambios sin commit y que el CHANGELOG tenga la sección de la versión de `VERSION`.
2. Exporta el código con `git archive` **sin la carpeta `privado/`** y le suma `privado/publico/` (los flujos de GitHub).
3. Busca datos personales con una lista de patrones prohibidos; si encuentra uno, **aborta**.
4. Corre la prueba de humo sobre la exportación.
5. Hace el commit en el público (identidad noreply), crea la etiqueta `vX.Y.Z`, sube, y pone la misma etiqueta en el de trabajo.

`--ensayo` hace todo menos subir. Para una versión nueva: cambia `VERSION`, añade la sección al `CHANGELOG.md`,
commit, y `privado/publicar.sh`.

Si tú mantienes tu propia copia (fork), puedes hacer lo mismo con tus propios `privado/presets.json` y patrones.
