# 🩺 Salud, alarma y línea base

> Parte de [Plan de mejoras](PLAN_MEJORAS.md), fase F0 «Operación sana». Versión corta: [fácil](facil/SALUD.md).

Antes de mejorar cómo se aprende hay que saber **si la Academia funciona y de dónde se parte**. Esta función añade
cuatro cosas: un tablero de salud, una alarma que vive fuera del servicio, una cola de IA que sobrevive a los reinicios y una
línea base de uso por persona.

## 1. Tablero 🩺 Salud

Botón 🩺 de la barra superior (o `#/salud`). Tiene dos partes:

| Parte | Quién la ve | Qué muestra |
|---|---|---|
| **Estado del equipo** | solo el administrador | problemas detectados (con gravedad), tareas en cola y corriendo, la más vieja y la más larga, fallos de las últimas 24 h, si el servidor de IA responde, temperatura y uso de la GPU, disco libre, tamaño de la base, gasto de la API del mes, tiempo encendida, estado de la rutina diaria y qué pasó con la cola en el último reinicio |
| **Tu línea base de uso** | cada persona, solo la suya | la primera foto de cómo estudia y la de hoy, con la diferencia y **de dónde sale cada número** |

Los mismos datos están en `GET /api/salud` (administrador) y `GET /api/salud/linea_base` (la persona que consulta). La lista de
problemas sale de una sola función (`salud.evaluar`), así que **la pantalla y la alarma nunca se contradicen**.

### Qué se considera un problema

| Problema | Cuándo | Gravedad |
|---|---|---|
| La rutina diaria no se ejecutó | pasaron más de 3 horas de su hora programada y no corrió (en los 3 primeros minutos tras arrancar no se avisa: empieza sola) | alta |
| La rutina diaria falló | terminó con un error (queda anotado con su mensaje) | alta |
| La rutina diaria tarda demasiado | lleva más de 30 minutos armando la cola | media |
| Tarea de IA colgada | una tarea lleva más de 3 horas corriendo (una lección a fondo tarda unos 30 minutos) | alta |
| Muchos fallos | 5 o más tareas de IA fallaron en 24 horas | media |
| Tareas perdidas en un reinicio | alguien esperaba una respuesta que no se pudo reconstruir (ver sección 3) | media |
| GPU caliente | 80 °C (media) o 85 °C (alta) | media / alta |
| Servidor de IA caído | hay tareas esperando y el servidor de IA no responde | alta |
| Disco casi lleno | menos de 5 GB libres | alta |

Lo que no se puede medir (por ejemplo, un equipo sin GPU NVIDIA) no se muestra ni se inventa.

## 2. Vigía: la alarma que vive fuera del servicio

Si el servicio se cae, él mismo no puede avisar. Por eso existe `app/vigia.py`, un proceso aparte, sin dependencias, que se ejecuta cada
pocos minutos (un temporizador de systemd, un cron o una tarea programada), pide `/api/salud` y avisa.

```bash
python3 app/vigia.py                   # una comprobación (lo normal, lo llama el temporizador)
python3 app/vigia.py --probar          # manda un mensaje de prueba por el canal y termina
python3 app/vigia.py --pausar [motivo] # silencia solo la alarma de «servicio caído» (parada a propósito)
python3 app/vigia.py --reanudar        # quita la pausa
```

**Cómo no molestar de más**

- «Servicio caído» solo se avisa después de **2 comprobaciones seguidas** fallidas (un reinicio normal tarda segundos). Con una comprobación cada
  2 minutos, la alarma llega en menos de 5 minutos.
- Cada problema se avisa **una vez**; si es de gravedad alta y sigue, se recuerda cada 6 horas; cuando se resuelve llega un aviso de recuperación.
- Si el servicio no responde, no se declara «resuelto» ningún otro problema (no se sabe).
- La pausa se quita sola en cuanto el servicio vuelve a responder.

**Canal de aviso.** La variable de entorno `ACADEMIA_ALARMA_CMD` es un programa que recibe el texto por la entrada estándar. Puede ser un
script que lo mande por Telegram, ntfy, correo o lo que prefieras. Sin ella, el aviso solo se imprime en el registro y el programa
termina con código **2** mientras haya un problema avisado (para que cualquier supervisor externo también lo lea). Si el canal falla, el aviso
no se da por entregado y se reintenta en la siguiente comprobación.

**Ejemplo con systemd** (usuario, sin privilegios): una unidad `oneshot` que ejecuta `python3 vigia.py` con `WorkingDirectory=…/app`,
`Environment=ACADEMIA_ALARMA_CMD=…` y `SuccessExitStatus=0 2`, y un temporizador con `OnUnitActiveSec=2min`. Solo necesita escribir en
`datos/` (guarda ahí `vigia.json` y la pausa).

Variables útiles: `ACADEMIA_PUERTO` o `ACADEMIA_URL_VIGIA` (a qué servicio preguntar) y `ACADEMIA_DATOS` (dónde guardar su estado).

## 3. Cola de IA que sobrevive a los reinicios

La cola de IA vive en memoria. Hasta ahora, cada reinicio hacía perder lo pendiente (el 2026-10-28 se perdieron 291 tareas). Ahora:

1. **Diario.** Al encolar una tarea se anota en la tabla `cola_diario` (tipo, persona, etiqueta, prioridad); al terminar —bien o con error— se borra.
2. **Al arrancar** se lee lo que había pendiente del proceso anterior y se vacía el diario.
3. **`reanudar()`** vuelve a encolar todo lo que se puede reconstruir desde la base: lecciones a medias, las del plan de hoy, rutas marcadas «preparar todo»,
   contraste de fuentes, pronósticos de acciones, noticias a fondo, síntesis, **revisión de rutas y fronteras vivas vencidas**.
4. **Conciliación.** Se compara lo que había con lo que ahora está en la cola. Lo que no vuelve se registra con su tipo. Solo lo que **una persona estaba esperando en pantalla**
   (una pregunta al tutor, una corrección, una prueba…) se muestra como problema: no hay de dónde reconstruirlo y hay que pedirlo otra vez. El trabajo de fondo que no volvió se
   rehace en la rutina diaria.

Comprobación hecha con una copia de la base real: 189 tareas pendientes → `kill -9` al servicio → 189 recuperadas, 0 perdidas.

## 4. Línea base de uso

La primera vez que una persona abre 🩺 se guarda **una foto fija** (`kv: linea_base:<persona>`). Las siguientes visitas muestran la foto de hoy junto a ella, para
saber con números si algo mejora. Cada métrica indica su origen:

| Métrica | De dónde sale |
|---|---|
| Minutos de estudio (14 y 30 días) | suma de los latidos de tiempo de estudio |
| Días activos (14 días) | días distintos con cualquier actividad registrada |
| Minutos por día activo | minutos de 14 días / días activos |
| Temas por estado y temas dominados | tabla de avance (hoy «dominado» aún no exige prueba diferida: eso llega en la fase F3) |
| Minutos por tema dominado | todo el tiempo estudiado / temas dominados (aproximado) |
| Tarjetas (total y vencidas) | tabla de tarjetas |
| Segundos por tarjeta | mediana de los repasos de menos de 5 minutos en 30 días |
| Lecciones (escritas y completas) | tabla de lecciones |

**Privacidad.** La línea base es por persona: nadie ve la de otra. El estado del equipo es solo del administrador y no incluye contenido de nadie
(solo cuentas por tipo de tarea).

## 5. Pruebas

`python3 pruebas/unidad_salud.py` (12 pruebas: evaluación de problemas, resumen de cola, diario y conciliación, ganchos de la cola, rutina diaria,
línea base y decisiones del vigía) además de `pruebas/unidad.py` y `pruebas/humo.py`.
