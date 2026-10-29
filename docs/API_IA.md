# ☁️ API de IA opcional (manual completo)

> ¿Prefieres lo corto? → [Versión fácil](facil/API_IA.md)

La Academia corre con **IA local** y eso es suficiente. La **API de IA** es una ayuda **opcional** para dos cosas:
**esperar menos** (una lección a fondo tarda de 25 a 35 minutos en un PC modesto) y, con un modelo mayor, **subir la
calidad** cuando se pueda. Viene **apagada**. Razón y límites: [Propósito §8](PROPOSITO.md).

## Qué proveedores admite

Cualquier servicio compatible con la API de OpenAI (`/chat/completions`) y la API de Anthropic. Ya vienen listos, con
su dirección y el enlace para crear la clave: Anthropic (Claude), OpenAI, Google Gemini, OpenRouter, Groq, Cerebras,
Together AI, Fireworks AI, DeepSeek, Mistral AI, xAI, SambaNova, NVIDIA NIM y Ollama Cloud (modelos abiertos grandes alojados por Ollama; clave en ollama.com/settings/keys). Con **«Otro»** puedes poner la dirección de
cualquier otro servicio (o de un servidor propio).

## Cómo se conecta (administrador, 2 minutos)

1. **Ajustes → 🔔 Modo corto, avisos y ☁️ API de IA → 🛠️ Administración.**
2. Elige el **proveedor**: la dirección se rellena sola y aparece el enlace para crear tu clave.
3. Pega la **clave**. Pulsa **📋 Ver modelos** (la Academia le pregunta al servicio cuáles puede usar tu clave) y elige uno.
4. Pon los **precios** de tu proveedor (USD por millón de tokens, entrada y salida) y el **tope global** al mes.
5. Pulsa **🔌 Probar** (una pregunta mínima: muestra tiempo, tokens y costo) y **💾 Guardar**. Marca el interruptor
   **«Permitir la API en esta Academia»**.
6. Cada persona decide después, en su propia cuenta, si la usa.

## 🆓 Plan gratuito (viene encendido)

Casilla **«Mi clave es del plan gratuito»** (Administración). Con ella: costo **0**, no se aplican los topes en dólares y se cuentan las llamadas y los
tokens. El límite lo pone el proveedor; al alcanzarlo (429) la tarea pasa al modelo de respaldo y luego a la IA local. **Privacidad:** en el nivel
gratuito algunos proveedores (Google, por ejemplo) pueden usar lo que reciben para mejorar sus productos y personas pueden leerlo; por eso nunca sale tu
nombre ni lo personal, y la pantalla lo avisa. Si tu proyecto tiene facturación activada, desmarca la casilla: se calcula el costo y vuelven los topes.

## Gemini (recomendado para empezar)

Proveedor **Google Gemini**, modelo `gemini-3.8-flash` (el Flash más nuevo al 2026-10-28). Al elegirlo se rellenan solos la dirección,
el modelo y el **esfuerzo de razonamiento** (`low`, `medium` o `high`; medio por defecto; «minimal» no existe en 3.8 Flash).
Gemini 3 no admite `temperature`: la Academia no la manda. Los **tokens de razonamiento se cobran como salida** y salen del mismo tope de
la respuesta, así que la Academia amplía el tope (+2.000, +6.000 o +12.000) para que no se corte. Precios de lanzamiento: US$ 0,75 de entrada y
US$ 3,75 de salida por millón hasta el 2026-12-31 (luego 1,50 / 7,50); ya vienen puestos y los puedes cambiar. Clave en https://aistudio.google.com/apikey.

## Qué decide cada persona

| Opción | Por defecto |
|---|---|
| Usar la API en mi cuenta | **No** |
| Para qué tareas | **solo «📖 Lecciones con sus fuentes»** (escribir la lección, contrastar sus fuentes, consultas de papers, ruta rápida y reexplicaciones). Con los atajos «Solo lecciones», «Todo» o «Nada», o grupo por grupo: 🗺️ rutas, metas, frontera y mercado · 📰 noticias y síntesis · 📝 pruebas, quizzes y verificación |
| Mandar mis metas y situación | **No** |
| Mi tope al mes (USD) | 5 |

## Qué sale y qué NO sale

| Sale (solo si la persona la activó y para esos grupos) | **Nunca** sale |
|---|---|
| El tema, las fuentes y los textos de la tarea técnica de estudio | El **tutor** (tu conversación), tus **apuntes y fotos** |
| Las metas y la situación, **solo** si la persona marca la casilla | Tus **entregas y respuestas**, tus propias **ideas** y aportes |
| | Tu **cartera, alertas y pronósticos** de 💹 Acciones, tus reportes y lo estudiado fuera |

El **nombre** se quita siempre (el perfil se cambia por «Estudiante anónimo»). La clave se guarda en `datos/secretos.json`
(permiso 600), no va en `configuracion.json`, no se devuelve por la API ni se escribe en el registro, y se borra de los
mensajes de error del servicio.

## Cómo se comporta

- **Si la API falla** (clave, cuota, red, el servicio rechaza algo) o se acaba un tope, **la tarea sigue sola en la IA
  local**, sin perderse. Tras un error de clave o cuota la API descansa 15-60 minutos para no insistir.
- **Se reajusta sola** a cada servicio: si rechaza `temperature` o `max_tokens` (modelos de razonamiento), usa lo que acepta; si no acepta
  `json_schema`, baja a `json_object` o pone el esquema en el texto.
- **Conexión robusta** (`app/red.py`): prueba IPv4 antes que IPv6 y limita la conexión a 10 s. Sin esto, un equipo sin salida por IPv6 se quedaba
  esperando minutos a una dirección que nunca contesta (pasó con Gemini). La lectura de la respuesta espera hasta 240 s entre trozos (el
  razonamiento alto puede tardar en empezar); si el servicio se cuelga más, la tarea sigue en la IA local.
- **Límite de uso o cuota agotada** (429, «quota», «resource exhausted»): primero prueba el modelo de respaldo (cada modelo tiene su propia
  cuota); si también llegó al límite, **la tarea pasa sola a la IA local** y la API descansa 15 minutos (3 horas si es un límite diario o de
  facturación) sin volver a intentarlo mientras tanto. Un modelo que falló o no contestó se deja de intentar primero durante 10 minutos.
- **Servicio saturado:** ante 500/502/503/504 («alta demanda», común en modelos recién salidos) reintenta tres veces con pausas de 3, 10 y 30 s antes de pasar a la IA local.
- **No espera a la GPU**: una tarea que va a la API no se detiene porque otra app esté usando la IA local ni porque se esté jugando (la cola solo espera por la GPU las tareas que irán a la IA local).
- **Costo**: tokens reales cuando el servicio los informa (si no, una estimación) × los precios que pusiste. Sin precios se
  usa una estimación **alta** (US$ 3 / 15 por millón) para que el tope proteja. Las tareas comunes (noticias del día) se cargan
  a la cuenta del administrador. Ves el gasto del mes por persona y total.
- **Tope**: por persona y global; al alcanzarlo, todo vuelve a lo local hasta el mes siguiente.

## Para quien modifica el código

`app/nube.py` (proveedores, privacidad, gasto, llamadas OpenAI/Anthropic en streaming), `app/secretos.py`,
`Contexto._chat` en `app/ia.py` (primero `nube.intentar`; si no aplica, la IA local), marcas `[[PERFIL]]…[[/PERFIL]]` de
`lecciones.texto_perfil` (la IA local las quita; la API las cambia por la versión mínima), rutas `/api/nube*` y vista
`web/nube.js`. Pruebas con un servicio falso en `pruebas/unidad.py` (reajuste de parámetros, privacidad, tope, respaldo
local, Anthropic). Para añadir un proveedor basta una entrada en `PROVEEDORES`.

## Tareas a la vez: carril de la nube y carril local

`trabajos_nube` (Configuración → IA, de 0 a 6) da a la API su **propio carril**, aparte de `trabajos_paralelos` (los «slots» del
servidor local). Con 3 y 2 trabajan hasta 5 tareas a la vez: 3 en la nube y 2 en tu equipo.

- El carril de la nube solo toma tareas que la persona permitió enviar (por grupos) y solo si la API responde.
- El carril local toma primero lo que solo puede hacerse en el equipo (tutor, apuntes, cartera…). De lo que la nube también
  podría hacer, toma únicamente cuando el carril de la nube está lleno o la API no está disponible (límite, fallo o pausa).
- Con 0 no hay carril propio y todo funciona como antes.

## API de reserva y límites mensuales

El administrador puede elegir una **API de reserva** (otro proveedor con su propia clave). Orden de intentos: modelo principal →
su respaldo → modelo de la reserva → su respaldo → IA local. Cada modelo que llega a su límite descansa:

| Qué dice el servicio | Descanso |
|---|---|
| Límite mensual, falta de créditos (402) | 15 días (`nube_reintento_mensual_dias`) |
| Límite diario | 3 horas |
| Límite sin periodo / 429 corto | 15 minutos |
| Clave rechazada (401/403) | 1 hora |

Las pausas de una hora o más se guardan y sobreviven a un reinicio. Por persona (Conexiones → API): usar o no la reserva y cada
cuántos días reintentar un límite mensual.
