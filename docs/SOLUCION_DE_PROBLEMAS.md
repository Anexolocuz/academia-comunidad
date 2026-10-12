# 🩺 Solución de problemas (manual completo)

> ¿Prefieres lo corto? → [Versión fácil](facil/PROBLEMAS.md)

Primero, tres comprobaciones que resuelven la mayoría:

1. ¿La app corre? Abre `http://127.0.0.1:8092/api/ia` en el PC donde está instalada. Si no carga → «No abre».
2. ¿La IA responde? Ajustes → 🤖 IA → **Probar conexión**.
3. ¿Qué dice el registro? Linux: `journalctl --user -u academia -n 80` · Windows/macOS: `datos/academia.log`.

## La app

| Síntoma | Causa probable | Solución |
|---|---|---|
| No abre en `127.0.0.1:8092` | No está corriendo | Linux: `systemctl --user restart academia` y mira el registro. Windows: abre `shell:startup\Academia.vbs`. Prueba a mano: `python3 app/servidor.py` (verás el error). |
| «Address already in use» | Otro programa usa el puerto | Cambia `"puerto"` en `datos/configuracion.json` y reinicia (y `tailscale serve` al puerto nuevo). |
| Pantalla «Algo falló» | Error del servidor | Recarga; si sigue, el registro dice qué fue. |
| Cambios del currículo no aparecen | No reiniciaste | Reinicia la Academia. Valida el JSON: `python3 -m json.tool curriculo/x.json`. |
| Todo vacío en «Hoy» | Todas las áreas en prioridad 0 | Ajustes → sube alguna área. |

## Instalación, escaneo y Docker

| Síntoma | Causa | Solución |
|---|---|---|
| El escaneo no encuentra mi Ollama | Está apagado o en otro puerto | Ábrelo (`ollama serve`) y vuelve a escanear; si usa otro puerto, ponlo a mano en Avanzado → IA. |
| En Docker no encuentra la IA de mi PC | Ollama escucha solo en 127.0.0.1 | `OLLAMA_HOST=0.0.0.0` en el PC ([DOCKER.md](DOCKER.md)), o usa el perfil `ollama`. |
| «Esta Academia solo acepta conexiones desde su propio PC» | Entras desde otro equipo sin Tailscale ni clave | Usa Tailscale o define `clave_acceso` ([DISPOSITIVOS.md](DISPOSITIVOS.md)). |
| «Host no permitido» (421) | Entras con un nombre que la Academia no conoce | Añádelo a `hosts_permitidos`. |
| SearXNG de Docker no arranca | Falta `SEARXNG_SECRET` | Corre `docker/arrancar.sh` o añade `SEARXNG_SECRET=$(openssl rand -hex 32)` a `.env`. |
| macOS: «no se puede abrir Instalar.command» | Gatekeeper | Clic derecho → Abrir → Abrir. |
| Windows: el .bat se cierra solo | Falta Python | Vuelve a abrirlo después de que winget instale Python. |

## Celular / Tailscale

| Síntoma | Causa | Solución |
|---|---|---|
| El celular no abre la dirección | Tailscale apagado en el celular o en el PC | Actívalo en ambos (misma cuenta o tailnet). |
| «403 Cuenta no autorizada» | Tu cuenta no está en `usuarios_permitidos` | Agrégala en `datos/configuracion.json` o déjalo en `[]`. |
| Funcionaba y dejó de abrir | `tailscale serve` se borró | `tailscale serve status`; vuelve a publicarla: `tailscale serve --bg --https=15443 http://127.0.0.1:8092`. |
| Chrome dice que no es segura | Usaste `http://` o la IP | Usa `https://<pc>.<tailnet>.ts.net:15443/`. |

## IA

| Síntoma | Causa | Solución |
|---|---|---|
| «En cola: la IA está terminando una tarea de otra app» | Otra app (p. ej. Hermes) usa otro modelo | Normal: tu tarea arranca sola al quedar libre y la otra termina completa. Si prefieres poder interrumpir, actívalo en Ajustes → IA (la tarea de la otra app fallaría). |
| Se queda «En cola» mucho rato | Hay otra tarea larga (lección, chequeo) | Normal: la barra superior dice qué hace. Las tareas de fondo ceden ante lo que pides tú. |
| Error de conexión con la IA | Servidor de IA apagado o URL mal | Ollama: ábrelo / `ollama serve`. Modo remoto: el otro PC está apagado o Tailscale desconectado. |
| `model not found` | El nombre del modelo no existe en tu servidor | Ajustes → IA → Probar conexión → elige uno de la lista. |
| Respuestas cortadas o «JSON» con error | El modelo se enredó | La app detecta bucles y reintenta sola; si se repite, usa un modelo más grande. |
| Lecciones muy lentas | Modelo grande en CPU | Modelo más pequeño, menos lecciones por día, o deja que se preparen en la actualización diaria. |
| No lee mis apuntes/fotos | El modelo no tiene visión | Usa un modelo con visión (gemma3, qwen-vl, llava). En llama.cpp hace falta el `--mmproj`. |
| Lecciones sin fuentes web | Sin buscador | Configura `searx_url` (ver CONFIGURACION.md). |
| Lecciones o módulos sin documentos científicos | Sin internet o OpenAlex no responde | Comprueba `curl https://api.openalex.org/works?search=test`. Sin red la lección se escribe igual, sin la sección de investigación. |
| Papers poco relacionados en «🔬 Investigación» | Consulta del módulo demasiado general | Las consultas en inglés están en `kv` (`consulta_en:<área.módulo>`): bórrala para que se regenere, o escríbela tú más técnica. En las lecciones solo se muestran los que la IA citó. |
| La comparación de fuentes dice «solo una fuente» | Nadie más cubrió la historia (ni en la búsqueda) | Normal en noticias pequeñas. |
| El nivel de mercado no aparece | Aún no se armó el referente del área | 📈 → «📊 Medir contra lo que pide hoy el mercado» (necesita búsqueda web), o espera la actualización diaria (2 áreas por día, por prioridad). |
| La lección tarda más de 30 min | Lección a fondo en CPU | Normal (ver MANTENIMIENTO). Puedes leer desde que termina la parte 1. |

## Contenido y aprendizaje

| Síntoma | Solución |
|---|---|
| Un dato de una lección parece incorrecto | Revisa las fuentes citadas; usa «🔄 Reescribir la lección»; pregunta al tutor con 🌐. |
| Me sale un tema que ya sé | ⚡ Prueba de nivel del módulo (Ruta) o «Ya lo domino». |
| Mi nivel profesional no sube | Hace falta el 70 % de **cada** nivel anterior. Haz pruebas de nivel de lo que ya sabes. |
| La voz 🔊 no suena | Android: Ajustes → Texto a voz (Google) → instala el idioma. Windows: Configuración → Hora e idioma → Voz. |
| El S Pen no dibuja / el dedo raya | Botón ✋/👆 de la barra del cuaderno (modo solo lápiz). Usa Chrome o Samsung Internet actualizados. |

## Datos

| Síntoma | Solución |
|---|---|
| «database is locked» | Algo más tiene abierta la base (un visor SQLite). Ciérralo. |
| Perdí el progreso al reinstalar | Restaura `datos/` desde tu respaldo (MANTENIMIENTO.md). |
| Quiero empezar de cero | Detén la app y mueve `datos/academia.db` a otro lugar (es tu respaldo). |
