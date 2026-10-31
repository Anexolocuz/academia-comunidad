# Hermes como motor de IA (opcional)

Por defecto la Academia habla con la IA local a través de `ia_url` (llama-swap u otro servidor compatible con OpenAI). Con
`motor: "hermes"` envía las mismas peticiones a la API de un **perfil de Hermes Agent**. No hace falta para usar la Academia.

## Qué cambia y qué no
- Cambia solo el destino de la llamada en `app/ia.py` (`Contexto._chat`): URL `hermes_url` + `/v1/chat/completions`, cabecera
  `Authorization: Bearer <clave>` y modelo `academia`.
- No cambia: la cola de trabajos, la prioridad, la cortesía con otras apps que usan la IA, el reintento ante JSON mal formado ni el
  análisis de la respuesta.
- La API de Hermes ignora `response_format`, `seed` y `chat_template_kwargs`: el esquema JSON se añade al final de la conversación
  como instrucción («responde solo con un objeto JSON que cumpla este esquema») y el perfil ya trabaja sin pensamiento.
- La API de Hermes no permite fijar `max_tokens`/`temperature` por petición de forma garantizada; el perfil define su razonamiento.

## Perfil de Hermes recomendado (ligero)
Un perfil propio (`hermes profile create academia --no-skills --no-alias`) con: un solo modelo, **sin memoria** (para no llenar la
memoria de Hermes con el texto de las lecciones), **sin herramientas** (el texto de noticias y webs que recibe la Academia no debe poder
ejecutar comandos), sin enlaces (hooks) y sin asesor MoA. Con eso el mensaje base baja de ~20 000 a ~650 tokens por petición.
La API se publica solo en `127.0.0.1` (`platforms.api_server` del perfil principal, que es el que posee el único oyente del equipo)
y las rutas del perfil son `/p/academia/v1/...` con su propia clave (`API_SERVER_KEY` del `.env` del perfil). **No** se publica por
Tailscale ni por internet.

## Activarlo
1. Crear el perfil y su clave como arriba y reiniciar el gateway de Hermes (`systemctl --user restart hermes-gateway`).
2. Guardar la clave: `secretos.guardar("hermes", clave)` (queda en `datos/secretos.json`, permiso 600).
3. En `datos/configuracion.json`: `"motor": "hermes"` (y `hermes_url` si cambia el puerto). Se aplica sin reiniciar.
4. Volver a lo anterior: `"motor": "local"`.

## Medido (2026-10-30, Gemma 4 26B-A4B, una pregunta de opción múltiple con esquema)
Directo a llama-swap: 6,8 y 7,0 s. Por Hermes: 5,5 y 4,4 s (el prefijo de ~10 000 tokens se reutiliza de la caché; sin ella
la primera petición tarda ~40 s). El JSON salió válido y completo en las 4 pruebas.
