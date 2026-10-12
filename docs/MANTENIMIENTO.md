# 🔧 Mantenimiento (manual completo)

> ¿Prefieres lo corto? → [Versión fácil](facil/MANTENIMIENTO.md)

## Rutina recomendada

| Cada | Qué | Cómo |
|---|---|---|
| Semana | Respaldo de tus datos | 📄 Reporte → «⬇️ Todos mis datos (ZIP)», o copia `datos/` (abajo) |
| Mes | Actualizar la app | `./actualizar.sh` · Windows: `ACTUALIZAR.bat` |
| Mes | Revisar el reporte | 📈 → 📄 Reporte: necesidades y recomendaciones |
| Cuando cambies de modelo | Probar la IA | Ajustes → 🤖 IA → Probar conexión |

## Iniciar, detener, reiniciar, ver qué pasa

**Docker**: `docker compose ps` · `docker compose restart academia` · `docker compose logs -f academia` (ver [DOCKER.md](DOCKER.md)).

**Linux**
```bash
systemctl --user status academia        # ¿corre?
systemctl --user restart academia       # reiniciar (tras editar currículo/config)
systemctl --user stop academia
journalctl --user -u academia -f        # registro en vivo
```

**Windows**: para reiniciar, cierra `pythonw.exe` (Administrador de tareas) y abre `shell:startup\Academia.vbs`
(o reinicia el PC). Registro: `datos\academia.log`.

**macOS**: `launchctl unload/load ~/Library/LaunchAgents/com.academia.servidor.plist` · registro `datos/academia.log`.

⚠️ Reiniciar mientras la IA escribe una lección la interrumpe. Si estaba a medio escribir las partes (lección a
fondo sin terminar), se vuelve a escribir entera al abrirla o en la siguiente actualización diaria; si ya tenía el
texto completo, solo se rehacen el quiz y las tarjetas. La versión anterior de una lección reescrita queda en la tabla
`leccion_anterior` («📜 Ver la versión anterior»). Antes de reiniciar mira la barra superior o `http://127.0.0.1:8092/api/ia`
(`"actual": null` = libre).

## Respaldo y restauración

Todo tu progreso está en **`datos/`**:

| Archivo | Qué es |
|---|---|
| `academia.db` (+ `-wal`, `-shm`) | perfil, avance, tarjetas, repasos, actividad, chequeos, objetivos, entregas, chat, noticias (con su comparación y explicación a fondo), lecciones y sus versiones anteriores; en `kv`: referentes del mercado (`mercado:<área>`) y caché de papers (`papers:<consulta>`) |
| `cuaderno/<cuenta>/*.png` | apuntes a mano |
| `entregas/<cuenta>/*` | fotos de tus ejercicios |
| `configuracion.json` | configuración de esta instalación |

**Copia consistente sin detener nada** (SQLite en caliente):
```bash
python3 -c "import sqlite3; sqlite3.connect('datos/academia.db').backup(sqlite3.connect('respaldo-academia.db'))"
```
y copia además `datos/cuaderno/` y `datos/entregas/`.

**Restaurar:** detén la Academia, reemplaza `datos/academia.db` (borra `academia.db-wal` y `-shm` si existen), copia
las carpetas de imágenes y vuelve a iniciar.

**Mover a otro PC (o a Docker):** instala en el nuevo, detén la Academia, copia toda la carpeta `datos/` encima y reinicia. Las imágenes del cuaderno y de las entregas se reubican solas al arrancar. Para Docker: `docker compose cp datos/. academia:/datos/` con el contenedor detenido no funciona; usa `docker run --rm -v academia_academia-datos:/datos -v "$PWD/datos":/origen alpine cp -a /origen/. /datos/` y luego `docker compose restart academia`.

## Actualizar

Ver [VERSIONES.md](VERSIONES.md). Con Git: `./actualizar.sh` / `ACTUALIZAR.bat` o el botón **⬇️ Actualizar ahora**
(Ajustes → Avanzado → Esta instalación). Con Docker: `docker compose pull && docker compose up -d`. Con ZIP: descarga
el nuevo y copia tu carpeta `datos/` dentro.

`git pull` trae código, currículo y fuentes nuevas; **nunca toca `datos/`**. Si editaste archivos del repositorio
(por ejemplo un JSON del currículo) y `git pull` se queja: `git stash`, `git pull`, `git stash pop`.

## Espacio y limpieza

- Las noticias sin analizar se borran solas a los 400 días y las de lectura en idiomas a los 14.
- La base crece poco (unos MB por mes). Las imágenes del cuaderno y de entregas son lo que más ocupa: puedes borrar
  notas o entregas viejas desde la app.
- Compactar la base (con la app detenida): `python3 -c "import sqlite3; sqlite3.connect('datos/academia.db').execute('VACUUM')"`

## Energía y rendimiento

- El trabajo pesado de IA se hace **una vez al día** (hora configurable) y solo si la IA está libre.
- Si el PC es lento: menos lecciones nuevas por día, un modelo más pequeño, o la IA de otro PC tuyo (modo remoto).
- Una lección a fondo genera ~10-15 mil tokens: con un modelo mediano en CPU (~8 tokens/s) son **25-35 minutos**
  (la parte 1 se puede leer a los ~8 min); por eso se preparan solas antes. La actualización diaria puede tener la
  IA ocupada **4-5 horas** (lecciones del día, hasta 3 lecciones antiguas reescritas, 20-25 análisis de noticias,
  comparaciones y explicaciones a fondo, 2 referentes de mercado): todo espera si otra app usa la IA.
