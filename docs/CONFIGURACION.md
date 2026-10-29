# ⚙️ Configuración (manual completo)

> ¿Prefieres lo corto? → [Versión fácil](facil/CONFIGURACION.md)

La configuración está en dos segmentos, igual que en **⚙️ Ajustes**:

- **🟢 Básico** — lo que cualquiera necesita: tu perfil, prioridades, ritmo, apariencia y tus datos.
- **🛠️ Avanzado** — dónde corre la IA, cuánto trabaja, la actualización diaria, la versión, la seguridad y el contenido.

Y un atajo para no tocar nada a mano: **🪄 Configuración automática**.

## 🪄 Configuración automática (auto-escaneo)

En **Ajustes** (arriba, solo para quien administra) o en el instalador:

1. **🔍 Escanear mi PC** → te pregunta **sí/no** y te dice qué va a revisar.
2. Revisa, **solo en este PC**: sistema, procesador, memoria, tarjeta gráfica (NVIDIA, AMD, Apple), servidores de IA
   en sus puertos habituales (Ollama 11434, LM Studio 1234, llama.cpp 8080, vLLM 8000, Jan 1337, y los de Docker) con
   sus modelos y cuáles tienen visión, buscadores SearXNG, Tailscale y Docker, y el disco libre.
3. Te muestra **qué puedes usar** (✅ / 🟡 / ➖), **cómo completar lo que falta** (comandos exactos) y la
   **configuración recomendada**: servidor, modelo principal y ligero, buscador, y un ritmo de trabajo acorde a la
   potencia (cuántas lecciones preparar por adelantado y cuántas noticias analizar a fondo).
4. **✅ Aplicar esta configuración** → otra pregunta **sí/no** → aplica al instante, sin reiniciar.

**Privacidad del escaneo:** no lee tus archivos, ni números de serie, ni IPs, ni cuentas; no envía nada a internet.
Se guarda en `datos/escaneo.json` (permisos 600) y **se borra solo a las 24 horas** (la Academia lo revisa cada
minuto); **🗑️ Borrar el escaneo ya** lo elimina antes. Ver el escaneo sin guardar nada: `python3 app/escaneo.py`.

## 🟢 Básico (Ajustes)

| Opción | Qué hace | Por defecto |
|---|---|---|
| Nombre, situación, metas, cómo aprendes | La IA lo lee para adaptar lecciones, ejemplos y el plan | vacío |
| Lecciones nuevas por día | El plan adaptativo sube o baja 1 según tu retención y atrasos | 2 |
| Tarjetas nuevas por día | Si tu retención baja de 80 %, bájalo | 25 |
| Meta de minutos por día | Para la barra de «Hoy» | 60 |
| Cuaderno: solo lápiz | El dedo desplaza la página y solo el lápiz (S Pen, Apple Pencil) dibuja | no |
| Prioridad por área (0-3) | 0 pausada · 1 de fondo · 2 importante · 3 máxima | 0 (las de tus metas: 2) |
| 🌍 Noticias por región (0-3) | De qué regiones quieres noticias y cuáles van primero (ver abajo) | las de `regiones_por_defecto` |
| Apariencia | Modo claro/oscuro, paleta, color de acento, tamaño de letra ([APARIENCIA.md](APARIENCIA.md)) | automático |
| Tus datos | Reporte y descarga de todo en ZIP | — |

## 🛠️ Avanzado

### En Ajustes → 🛠️ Avanzado (solo administradores)

- **🤖 Dónde se procesa la IA → ⚙️ Cambiar:** presets de un toque (Ollama, LM Studio, llama.cpp, llama-swap +
  SearXNG, Docker), **🔍 Detectar servidores**, **🔌 Probar conexión** y **💾 Guardar** (aplica al instante).
- **🕕 Actualización diaria:** a qué hora se bajan las noticias y se preparan las lecciones (6:00 por defecto).
- **🧩 Esta instalación:** versión, si hay una nueva y **⬇️ Actualizar ahora** ([VERSIONES.md](VERSIONES.md)).

Quién es administrador: quien entra **desde el propio PC**, o las cuentas de `administradores` (por defecto la
primera de `usuarios_permitidos`) también desde el celular por Tailscale. Quien entra con la clave de acceso usa la
Academia pero no la administra.

### `datos/configuracion.json`

Lo escribe el instalador o la configuración automática. Tras editarlo a mano, reinicia la Academia.

```jsonc
{
  "nombre": "Mi Academia",
  "modo": "local",                          // "local" o "remoto" (IA en otro PC tuyo); informativo
  "host": "127.0.0.1",                      // NO lo cambies a 0.0.0.0 sin «clave_acceso» (ver Seguridad)
  "puerto": 8092,
  "ia_url": "http://127.0.0.1:11434",       // servidor compatible con OpenAI (/v1/chat/completions)
  "modelo": "gemma3:12b",                   // principal (con visión para leer apuntes y fotos)
  "modelo_ligero": "",                      // opcional: para cuando el principal está ocupado
  "modelos_compatibles": [],                // modelos de OTRAS apps que pueden estar cargados a la vez sin esperar
  "searx_url": "",                          // SearXNG; vacío = sin búsqueda web
  "aigate_url": "",                         // monitor de GPU: URL que devuelve JSON {"busy": true|false} o {"game": …}
  "trabajos_paralelos": 1,                  // tareas de IA a la vez (= llama-server --parallel N)
  "lecciones_adelantadas": 2,               // lecciones listas sin leer por persona (0 = solo al abrirlas)
  "noticias_a_fondo_por_persona": 8,        // noticias diarias a máxima profundidad por persona
  "regiones_por_defecto": {"global": 2},    // regiones de noticias (0-3) de quien aún no eligió las suyas
  "permitir_interrumpir": false,            // false: si otra app usa la IA, tu tarea espera; true: te pregunta
  "usuario_local": "yo",                    // tu perfil cuando entras desde este PC
  "usuarios_permitidos": [],                // cuentas de Tailscale que pueden entrar; [] = cualquiera de tu tailnet
  "administradores": null,                  // null = la primera cuenta permitida

  // --- seguridad (ver SEGURIDAD_Y_DATOS.md) ---
  "clave_acceso": "",                       // clave para entrar desde otros equipos de tu red; vacío = no se puede
  "redes_locales": ["127.0.0.0/8", "::1/128"], // qué cuenta como «este PC»
  "hosts_permitidos": []                    // nombres extra (p. ej. "academia.casa"); localhost y *.ts.net ya valen
}
```

### Variables de entorno

Tienen prioridad sobre el archivo (útil en pruebas y Docker):

| Variable | Clave |
|---|---|
| `ACADEMIA_DATOS` | carpeta de datos (otra = instalación aislada) |
| `ACADEMIA_HOST`, `ACADEMIA_PUERTO` | `host`, `puerto` |
| `ACADEMIA_LLAMA`, `ACADEMIA_MODELO`, `ACADEMIA_MODELO_LIGERO` | `ia_url`, `modelo`, `modelo_ligero` |
| `ACADEMIA_SEARX`, `ACADEMIA_AIGATE` | `searx_url`, `aigate_url` |
| `ACADEMIA_CLAVE`, `ACADEMIA_USUARIO` | `clave_acceso`, `usuario_local` |
| `ACADEMIA_REDES_LOCALES`, `ACADEMIA_HOSTS` | `redes_locales`, `hosts_permitidos` (separadas por comas) |
| `ACADEMIA_INICIAL_<CLAVE>` | valor **de partida** de cualquier clave, que sí se puede cambiar luego en Ajustes |

### Presets propios

Para ofrecer en Ajustes un preset tuyo (p. ej. «IA en el PC de la casa»), crea `privado/presets.json` con el mismo
formato que `PRESETS` en `app/config.py`. Esa carpeta no se publica (ver [VERSIONES.md](VERSIONES.md)).

### Contenido: currículo y noticias

**Currículo** — cada área es un archivo en `curriculo/`:

```json
{
  "id": "mi_area", "nombre": "Mi área", "icono": "🔧", "grupo": "Ingenierías", "color": "#636e72",
  "descripcion": "…", "recursos": [{"t": "Curso X", "u": "https://…"}],
  "modulos": [
    {"id": "base", "t": "Fundamentos", "nivel": 1, "pre": [], "temas": ["Título del tema|descripción corta", "…"]},
    {"id": "avanzado", "t": "Algo avanzado", "nivel": 3, "pre": ["base", "matematicas.calculo1"], "temas": ["…"]}
  ]
}
```

- `nivel`: 1 Fundamentos · 2 Intermedio · 3 Avanzado · 4 Experto · 5 Horizonte.
- `pre`: módulos que hay que dominar al 60 % antes (`id` del mismo archivo o `area.modulo` de otra área).
- **No cambies el orden ni borres temas de un módulo ya estudiado**: el progreso se guarda por posición
  (`area.modulo.N`). Agregar temas al final sí es seguro.
- Idiomas: añade `"idioma": "ja-JP"` (código para la voz) y `"examen": "JLPT"`.
- Reinicia la Academia tras editar. Sin tocar archivos: **🎯 → 📚 Área o carrera completa** crea un área con IA solo para tu cuenta.

### 🌍 Noticias por región

Las fuentes están agrupadas en **segmentos**: **🌍 Global** (medios internacionales, ciencia y tecnología; siempre
existe) y **regiones** (de fábrica: Latinoamérica, México, Colombia, Perú, Chile, Argentina y España).

- **Cada persona** elige en Ajustes → Básico → 🌍 *Noticias por región* una prioridad por región:
  **0** no la quiero · **1** poco · **2** normal · **3** primero. Decide qué noticias ve, en qué orden (una historia
  vale por la región de mayor prioridad entre las fuentes que la cuentan) y cuáles se preparan a fondo para ella.
- Quien aún no eligió usa `regiones_por_defecto` (de fábrica `{"global": 2}`); el administrador lo cambia con
  **«Usar mis prioridades de arriba»**.
- **Solo se descargan** las regiones que alguna persona activa tiene en 1 o más (más Global).
- La **síntesis** del día/semana/mes/año es común a todos y sale solo del segmento Global.

**Administrar** (Ajustes → Avanzado → 🗺️ *Regiones y fuentes*): **➕ Agregar región** (nombre + emoji),
**Quitar región** (Global no), y en cada región **🔌 Probar** / **➕ Agregar fuente** (nombre, RSS, idioma, peso) o 🗑️ quitarla.
Una fuente solo se agrega si responde con noticias y es una dirección pública de internet. Lo que agregas o quitas se
guarda en `datos/regiones.json` (tuyo, no se toca al actualizar); el catálogo de fábrica es `config/fuentes.json`.

**Formato de `config/fuentes.json`:** `regiones` = `{id: {nombre, icono, descripcion}}`; cada fuente tiene `n`
(nombre), `u` (RSS/Atom), `peso` (1-3), `areas`, `idioma` y `region` (si falta: global). Las de `"tipo": "lectura"`
son para practicar idiomas (no tienen región). `palabras` asigna áreas por palabras clave. Probar una fuente a mano:
`curl -sL <url> | grep -c "<item"`.


## Rutas vivas (2026-10-27)

| Clave | De fábrica | Qué hace |
|---|---|---|
| `mercado_cada_dias` | 30 | Cada cuántos días se renueva el nivel profesional frente al mercado de cada ruta (una tarea de IA por área). |
| `revision_rutas_cada_dias` | 7 | Cada cuántos días se revisa cada ruta y se le agrega lo que falta. |
| `verificar_lecciones` | false | true = cada lección nueva se contrasta sola con fuentes verificadas (una tarea de IA más por lección). |

Con `1` y `1` todo se renueva a diario (más horas de IA; la cola respeta a las demás apps).


## 💹 Acciones (2026-10-28)

| Clave | De fábrica | Qué hace |
|---|---|---|
| `acciones_pronostico_diario` | true | En la actualización diaria, un pronóstico a 30 días por cada acción vigilada de cada persona activa (si el último tiene más de 20 h; de fondo, detrás de lo de estudio). false = solo precios, noticias y alertas; el pronóstico se pide a mano. |

Los precios vienen de Yahoo Finance y las noticias de Yahoo Finance y Google Noticias (RSS de búsqueda), sin claves.
No hay nada más que configurar.


## ☁️ API de IA y 🔔 avisos (claves de `configuracion.json`)

| Clave | Por defecto | Para qué |
|---|---|---|
| `nube_activa` | `false` | interruptor general de la API (cada persona decide además) |
| `nube_proveedor`, `nube_url`, `nube_modelo` | vacíos | proveedor elegido (ver [API de IA](API_IA.md)), su dirección y el modelo |
| `nube_precio_in`, `nube_precio_out` | `0` | USD por millón de tokens; `0` = estimación alta |
| `nube_tope_global_usd` | `20` | gasto máximo al mes entre todas las personas |
| `url_publica` | vacía | dirección con la que se abre la Academia (va dentro del aviso) |
| `ntfy_url` | `https://ntfy.sh` | servidor de ntfy |

La clave de la API y el token del bot **no** están aquí: van en `datos/secretos.json`. Se cambian desde Ajustes → 🔔 … → Administración.
Las opciones de cada persona (usar la API, tope, avisos, modo corto) están en su perfil y en la base.

## Prioridad frente a otras apps de IA

| Clave | De fábrica | Qué hace |
|---|---|---|
| `modelos_cedibles` | `[]` | Modelos de otras apps que ceden el turno a lo que PIDES cuando llevan 20 s sin procesar (p. ej. `["modelo-de-mi-agente"]`). Vacío = siempre esperar. |
| `supermemory_estado_url` | `""` | URL de otra app de IA que devuelva JSON `{"en_curso": true\|false}` (p. ej. un servicio de memoria como Supermemory detrás de un proxy propio): la Academia no entra a mitad de su trabajo. Esa app puede consultar `GET /api/prioridad` (`usuario_esperando`, `diaria`, `fondo`, `corriendo`) para no empezar trabajo nuevo mientras alguien espera o para dejarle turnos a la Academia. |
