/* Academia — 🩺 Salud: qué falla y de dónde partimos (fase F0). Se carga después de app.js y usa sus utilidades
   (api, esc, VISTAS, vista, hhmm). Dos partes: el estado del equipo (solo el administrador) y la línea base de uso
   de ESTA persona (cada perfil ve solo la suya, con el origen de cada número). */
"use strict";

const SL = {
  grav: { alta: ["mal", "🔴 Alta"], media: ["medio", "🟠 Media"], baja: ["", "🟡 Baja"] },
  tipos: { leccion: "lecciones", sintesis: "síntesis", a_fondo: "noticias a fondo", ruta: "rutas", frontera: "fronteras",
           verificar: "verificaciones", rapida: "rutas rápidas", ciencia: "consultas científicas", pronostico: "pronósticos",
           noticias: "selección de noticias" },
};
const slDur = (s) => s == null ? "—" : s < 90 ? Math.round(s) + " s" : s < 5400 ? Math.round(s / 60) + " min" : (s / 3600).toFixed(1) + " h";
const slFecha = (t) => t ? new Date(t * 1000).toLocaleString(LOC, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "nunca";
const slValor = (v) => v == null ? "—" : typeof v === "object" ? Object.entries(v).map(([k, x]) => `${esc(k)}: <b>${esc(x)}</b>`).join(" · ") : `<b>${esc(v)}</b>`;

function slSistema(f) {
  const c = f.cola, d = f.diaria, s = f.sistema || {}, g = s.gpu, b = f.base_datos || {};
  const problemas = f.problemas.length
    ? `<ul class="temas">${f.problemas.map((p) => `<li style="cursor:default"><span class="etq ${SL.grav[p.gravedad][0]}">${SL.grav[p.gravedad][1]}</span>
        <span style="flex:1;min-width:0">${esc(p.texto)}</span></li>`).join("")}</ul>`
    : `<p class="vacio">✅ Sin problemas: la rutina diaria, la cola, la IA, la GPU y el disco están bien.</p>`;
  const pend = Object.entries(c.pendientes_por_tipo).map(([t, n]) => `${n} ${SL.tipos[t] || t}`).join(" · ") || "nada";
  const r = f.reinicio;
  return `<h2>🩺 Estado del equipo</h2>${problemas}
    <div class="stats">
      <div class="stat"><b>${c.en_cola + c.conflicto}</b><span>en cola${c.conflicto ? ` (${c.conflicto} esperando a otra app)` : ""} · más vieja: ${slDur(c.mas_viejo_s)}</span></div>
      <div class="stat"><b>${c.corriendo}</b><span>corriendo ahora${c.corriendo ? ` · la más larga: ${slDur(c.corriendo_max_s)}` : ""}</span></div>
      <div class="stat"><b>${c.fallidos_24h}</b><span>fallaron en 24 h</span></div>
      <div class="stat"><b>${f.ia.alcanzable === false ? "caída" : f.ia.alcanzable ? "responde" : "—"}</b><span>servidor de IA · ${esc(f.ia.modelo)}</span></div>
      <div class="stat"><b>${g ? g.temp + " °C" : "—"}</b><span>GPU${g ? ` · ${g.uso} % de uso · ${g.vram}/${g.vram_total} GB` : ""}</span></div>
      <div class="stat"><b>${f.disco_libre_gb ?? "—"} GB</b><span>libres en disco · base ${b.db_mb ?? "—"} MB</span></div>
      <div class="stat"><b>${f.api.configurada ? "$" + f.api.gastado_mes_usd : "apagada"}</b><span>API de IA (gasto del mes)</span></div>
      <div class="stat"><b>${slDur(f.ahora - f.inicio_servicio)}</b><span>servicio encendido</span></div></div>
    <p class="suave peq">Pendiente por tipo: ${esc(pend)}.</p>
    <p class="suave peq">🌅 Rutina diaria: programada ${slFecha(d.programada)} · última ejecución ${slFecha(d.ultima)}
      ${d.inicio ? ` · empezó ${slFecha(d.inicio)}, ${d.fin ? "terminó " + slFecha(d.fin) : "sigue armando la cola"}` : ""}
      ${d.error ? ` · <b class="ac-baja">falló: ${esc(d.error)}</b>` : ""}</p>
    ${r ? `<p class="suave peq">🔁 Último reinicio (${slFecha(r.cuando)}): ${r.antes} tareas pendientes antes, <b>${r.recuperadas}</b> recuperadas,
      ${r.perdidas.length} no se pudieron reconstruir${r.perdidas.length ? ` (${esc([...new Set(r.perdidas.map((x) => x.tipo))].join(", "))})` : ""}.</p>` : ""}
    <p class="suave peq">La alarma por Telegram la manda el <b>vigía</b>, un proceso aparte del servicio (así avisa aunque el servicio se caiga).</p>`;
}

function slBase(b) {
  const ahora = b.ahora, base0 = b.base;
  const fila = ([k, nombre]) => {
    const a = ahora[k], z = base0 && base0[k];
    const num = (x) => x && typeof x.valor === "number" ? x.valor : null;
    const dif = num(a) != null && num(z) != null && a.valor !== z.valor
      ? ` <span class="suave peq">(${a.valor > z.valor ? "+" : ""}${Math.round((a.valor - z.valor) * 10) / 10} desde la línea base)</span>` : "";
    return `<li style="cursor:default;align-items:flex-start"><span style="flex:1;min-width:0"><b>${esc(nombre)}</b>: ${slValor(a.valor)}${dif}
      <br><span class="suave peq">Línea base: ${z ? slValor(z.valor) : "—"} · de dónde sale: ${esc(a.origen)}</span></span></li>`;
  };
  return `<h2>📏 Tu línea base de uso</h2>
    <p class="suave peq">Es la foto de cómo usas la Academia hoy (${base0 ? slFecha(base0.fecha) : "se está tomando"}), guardada una sola vez.
      Sirve para saber con números —no por impresión— si los cambios que vengan te ayudan a aprender más rápido. Solo tú la ves.</p>
    <ul class="temas">${[["minutos_14d", "Minutos de estudio (14 días)"], ["minutos_30d", "Minutos de estudio (30 días)"],
      ["dias_activos_14d", "Días activos (14 días)"], ["minutos_por_dia_activo_14d", "Minutos por día activo"],
      ["temas_dominados", "Temas dominados"], ["minutos_por_tema_dominado", "Minutos por tema dominado"],
      ["temas_por_estado", "Temas por estado"], ["tarjetas", "Tarjetas"], ["segundos_por_tarjeta_30d", "Segundos por tarjeta"],
      ["lecciones", "Lecciones"]].map(fila).join("")}</ul>`;
}

VISTAS.salud = async () => {
  const [base, sis] = await Promise.all([api("salud/linea_base"), api("salud").catch((e) => ({ _error: e.message }))]);
  vista.innerHTML = `<h1>🩺 Salud</h1>
    <p class="suave peq">Qué está pasando por dentro de la Academia y de dónde partimos para medir mejoras. Cada dato dice de dónde sale.</p>
    ${sis._error ? `<p class="vacio">${esc(sis._error)}</p>` : slSistema(sis)}
    ${slBase(base)}`;
};
