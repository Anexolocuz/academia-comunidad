# 🔒 Seguridad y datos (manual completo)

> ¿Prefieres lo corto? → [Versión fácil](facil/SEGURIDAD.md)

## Principios

1. **Cada persona en su propio PC.** La Academia se instala y corre en el PC de quien la usa. No hay servidor central,
   cuentas en la nube ni telemetría. Quien publica el proyecto **no** recibe ni guarda datos de nadie.
2. **Cerrada por defecto.** Solo responde a este mismo PC. Para entrar desde otro equipo hay que decidirlo:
   Tailscale (recomendado) o una clave de acceso.
3. **Lo mínimo sale a internet**, y nunca datos tuyos (ver abajo).

## Qué se guarda y dónde

Todo en la carpeta **`datos/`** (o el volumen `/datos` en Docker), que **nunca** va a git (`.gitignore`):

| Archivo | Contenido |
|---|---|
| `academia.db` | perfil, avance, tarjetas, repasos, actividad, chequeos, metas, entregas, chat del tutor, lecciones, noticias |
| `cuaderno/`, `entregas/` | tus apuntes a mano y fotos de ejercicios |
| `configuracion.json` | configuración de esta instalación (incluye la clave de acceso si pusiste una) |
| `regiones.json` | regiones y fuentes de noticias que agregó o quitó el administrador |
| `escaneo.json` | resultado del auto-escaneo; **se borra solo a las 24 h** |

📄 Reporte → «Qué datos se guardan y cómo se usan» lo explica con el número de registros, y el ZIP de exportación
trae un `LEEME.md` por tabla.

## Qué sale a internet

- Fuentes RSS de noticias **de las regiones que alguien usa** y el texto de esos artículos (para analizarlos y compararlos). Las fuentes nuevas solo se aceptan si son direcciones públicas de internet.
- Búsquedas web, si configuras SearXNG (que anonimiza ante los buscadores).
- Búsquedas de documentos científicos en OpenAlex: solo términos técnicos del tema, sin datos tuyos.
- «Buscar actualizaciones» consulta GitHub solo cuando pulsas el botón.
- **Nada más.** Las librerías web vienen incluidas (`web/vendor/`); la IA es la tuya (local o en otro PC tuyo).

Si usas la IA de otro PC, el texto de lo que estudias, tu perfil y tus fotos de apuntes **pasan** por ese PC para
procesarse, pero no se guardan allí.

## Quién puede entrar

| Desde | Cómo entra | Qué puede hacer |
|---|---|---|
| Este PC (`127.0.0.1`) | directo | todo, incluido administrar |
| Celular/tablet por **Tailscale** (`tailscale serve`) | Tailscale pone tu cuenta en la cabecera `Tailscale-User-Login` | usar su propio perfil; administrar si está en `administradores` |
| Otro equipo de tu red | solo si definiste `clave_acceso` | usar la Academia; **no** administrarla |
| Cualquier otro | **rechazado** (403) | nada |

Cada cuenta ve solo sus datos (progreso, lecciones, cuaderno, entregas). `usuarios_permitidos` limita qué cuentas de
Tailscale entran.

## Protecciones del servidor (desde v1.0.2)

| Riesgo | Protección |
|---|---|
| Alguien de tu red finge ser tú con la cabecera de Tailscale | La cabecera solo se cree si la conexión viene de este PC (`redes_locales`), que es de donde conecta `tailscale serve`. |
| Abrir el servidor a la red por error (`host: 0.0.0.0`) | Sin `clave_acceso`, todo equipo que no sea este PC recibe 403. |
| **CSRF**: una página web que visitas manda órdenes a `127.0.0.1:8092` | Toda escritura exige `Content-Type: application/json` (el navegador no lo deja enviar a otro sitio sin permiso) y, si trae `Origin`, debe coincidir con el `Host`. |
| **DNS rebinding**: un dominio malicioso que apunta a 127.0.0.1 | El `Host` debe ser localhost/127.0.0.1/::1, `*.ts.net`, una IP o uno de `hosts_permitidos` (si no: 421). |
| Fuerza bruta a la clave | Comparación en tiempo constante y 1 s por intento, de a uno aunque lleguen muchos a la vez; la cookie es un HMAC de la clave (`HttpOnly`, `SameSite=Strict`) y cambia si cambias la clave. |
| Enlaces maliciosos en RSS o en respuestas de la IA | Solo se enlazan URLs `http(s)`; el markdown pasa por DOMPurify; el texto se escapa. |
| Ver archivos fuera de `web/` | Rutas resueltas y comprobadas; imágenes del cuaderno/entregas solo de su dueño. |
| Instrucciones maliciosas a la IA (p. ej. escondidas en una noticia) que intenten meter código en la interfaz | Identificadores y colores que genera la IA se limpian (`curriculo._normalizar`); todo su texto se escapa o pasa por DOMPurify. |
| Un enlace de RSS que apunte a tu red (router, NAS) — SSRF | El lector de artículos solo abre direcciones públicas de internet, también tras redirecciones (`noticias.url_publica`). |
| Otros usuarios del mismo PC leyendo tus datos | `datos/` con permisos 700 y `configuracion.json` 600 (Linux/macOS). |
| Clickjacking / sniffing | `X-Frame-Options: SAMEORIGIN`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`. |
| El servidor como «proxy» (SSRF) | Probar/detectar servidores de IA y escanear solo para administradores. |
| Docker | Sin root, solo lectura, sin capacidades, `no-new-privileges`; IA y buscador sin puertos publicados. |

`python3 pruebas/humo.py` comprueba estas protecciones (también lo hace GitHub en cada cambio).

## Recomendaciones

- **Celular:** usa Tailscale; no abras el puerto en tu router ni lo expongas a internet.
- **Clave de acceso:** solo en tu red de casa, larga (4+ palabras) y distinta de otras claves. La conexión es HTTP
  sin cifrar en tu red: para cifrado, Tailscale.
- Mantén la Academia actualizada ([VERSIONES.md](VERSIONES.md)) y respalda `datos/` ([MANTENIMIENTO.md](MANTENIMIENTO.md)).
- Si tu servidor de IA escucha en la red (`OLLAMA_HOST=0.0.0.0`), protégelo con cortafuegos: cualquiera de la red
  podría usarlo.

## Reportar un problema de seguridad

Ver [SECURITY.md](../SECURITY.md): por mensaje privado en GitHub (Security → Report a vulnerability), no en un issue público.
