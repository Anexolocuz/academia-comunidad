/* Academia — 💹 Acciones bajo vigilancia (lista, detalle, noticias directas/indirectas y pronóstico por escenarios).
   Se carga después de app.js y usa sus utilidades (api, esc, md, ir, VISTAS, esperarTrabajo…). Cada persona ve solo
   su lista; los precios y noticias vienen del servidor (Yahoo Finance, Google Noticias y las noticias de la Academia). */
"use strict";

const AC = {
  impacto: { 2: ["▲▲ muy positivo", "bien"], 1: ["▲ positivo", "bien"], 0: ["● neutro", ""], "-1": ["▼ negativo", "mal"], "-2": ["▼▼ muy negativo", "mal"] },
  cubetas: [["muy probable", "🟢 Muy probable", "bien"], ["probable", "🟡 Probable", "medio"],
            ["poco probable", "🟠 Poco probable", "medio"], ["muy poco probable", "🔴 Muy poco probable", "mal"]],
  rangos: { "1m": [30, "1 mes"], "3m": [91, "3 meses"], "6m": [182, "6 meses"], "1a": [365, "1 año"], "2a": [730, "2 años"] },
  flecha: { sube: "▲", baja: "▼", lateral: "▶" },
};
const acNum = (x, d = 2) => x == null ? "—" : Number(x).toLocaleString(LOC, { minimumFractionDigits: d, maximumFractionDigits: d });
const acPrecio = (x, moneda) => x == null ? "—" : acNum(x, Math.abs(x) >= 1000 ? 0 : 2) + (moneda ? " " + esc(moneda) : "");
const acPct = (x, d = 1) => x == null ? `<span class="suave">—</span>`
  : `<span class="ac-${x > 0 ? "sube" : x < 0 ? "baja" : "igual"}">${x > 0 ? "▲ +" : x < 0 ? "▼ " : ""}${acNum(x, d)} %</span>`;
const acFecha = (t) => new Date(t * 1000).toLocaleDateString(LOC, { day: "numeric", month: "short" });

/* mini-gráfico de 30 días (sin ejes: solo la forma; el color lo da el cambio del periodo, que también va en texto) */
function acSpark(vals) {
  if (!vals || vals.length < 2) return "";
  const W = 96, H = 28, lo = Math.min(...vals), hi = Math.max(...vals), r = hi - lo || 1;
  const pts = vals.map((v, i) => `${(i / (vals.length - 1) * W).toFixed(1)},${(H - 2 - (v - lo) / r * (H - 4)).toFixed(1)}`).join(" ");
  const cls = vals[vals.length - 1] >= vals[0] ? "ac-sube" : "ac-baja";
  return `<svg class="ac-spark ${cls}" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" aria-hidden="true"><polyline points="${pts}"/></svg>`;
}

/* gráfico del precio: línea, media de 50 días y el «cono» del rango estadístico del pronóstico; cruz + tooltip al pasar */
function acGrafico(cont, serie, op = {}) {
  if (!serie || serie.length < 2) { cont.innerHTML = `<p class="vacio">Sin precios.</p>`; return; }
  const W = Math.max(280, cont.clientWidth || 600), H = W < 500 ? 210 : 260, ml = 6, mr = 58, mt = 12, mb = 24;
  const todos = op.todos || serie;   // la media de 50 días se calcula con toda la historia, no solo con lo visible
  const k0 = todos.length - serie.length;
  const sma = serie.map((_, i) => { const j = k0 + i; if (j < 49) return null; let s = 0; for (let k = j - 49; k <= j; k++) s += todos[k][1]; return s / 50; });
  const x0 = serie[0][0], x1 = serie[serie.length - 1][0], cono = op.cono, xEnd = cono ? x1 + cono.dias * 86400 : x1;
  const ys = serie.map((p) => p[1]);
  let lo = Math.min(...ys, cono ? cono.bajo : Infinity), hi = Math.max(...ys, cono ? cono.alto : -Infinity);
  const pad = (hi - lo) * 0.06 || 1; lo -= pad; hi += pad;
  const X = (t) => ml + (t - x0) / (xEnd - x0 || 1) * (W - ml - mr), Y = (v) => mt + (hi - v) / (hi - lo) * (H - mt - mb);
  const paso = (() => { const b = (hi - lo) / 4, e = Math.pow(10, Math.floor(Math.log10(b))); return [1, 2, 2.5, 5, 10].map((m) => m * e).find((m) => m >= b); })();
  let ejes = "";
  for (let v = Math.ceil(lo / paso) * paso; v <= hi; v += paso)
    ejes += `<line class="gp-red" x1="${ml}" x2="${W - mr}" y1="${Y(v)}" y2="${Y(v)}"/><text class="gp-eje" x="${W - mr + 6}" y="${Y(v) + 4}">${acNum(v, paso < 1 ? 2 : 0)}</text>`;
  let ultX = -99;
  serie.forEach((p, i) => {
    const d = new Date(p[0] * 1000), prev = i ? new Date(serie[i - 1][0] * 1000) : null;
    if (prev && d.getMonth() !== prev.getMonth() && X(p[0]) - ultX > 54) {
      ultX = X(p[0]);
      ejes += `<text class="gp-eje" x="${ultX}" y="${H - 6}" text-anchor="middle">${d.toLocaleDateString(LOC, { month: "short" })}${d.getMonth() === 0 ? " " + String(d.getFullYear()).slice(2) : ""}</text>`;
    }
  });
  const camino = (vals) => vals.map((v, i) => v == null ? "" : `${vals[i - 1] == null ? "M" : "L"}${X(serie[i][0]).toFixed(1)},${Y(v).toFixed(1)}`).join("");
  let conoSvg = "";
  if (cono) {
    const ux = X(x1), uy = Y(ys[ys.length - 1]), fx = X(xEnd);
    conoSvg = `<polygon class="gp-cono" points="${ux},${uy} ${fx},${Y(cono.alto)} ${fx},${Y(cono.bajo)}"/>
      <line class="gp-cono-borde" x1="${ux}" y1="${uy}" x2="${fx}" y2="${Y(cono.alto)}"/><line class="gp-cono-borde" x1="${ux}" y1="${uy}" x2="${fx}" y2="${Y(cono.bajo)}"/>
      <text class="gp-eje" x="${fx - 4}" y="${Y(cono.alto) - 5}" text-anchor="end">${acNum(cono.alto)}</text>
      <text class="gp-eje" x="${fx - 4}" y="${Y(cono.bajo) + 13}" text-anchor="end">${acNum(cono.bajo)}</text>`;
  }
  cont.innerHTML = `<svg width="${W}" height="${H}" role="img" aria-label="Precio de ${esc(op.nombre || "")}">${ejes}
    <path class="gp-media" d="${camino(sma)}"/>${conoSvg}<path class="gp-linea" d="${camino(ys)}"/>
    <line class="gp-cruz" id="gpCruz" y1="${mt}" y2="${H - mb}" hidden/><circle class="gp-punto" id="gpPunto" r="4" hidden/>
    <rect x="${ml}" y="0" width="${W - ml - mr}" height="${H}" fill="transparent" id="gpZona"/></svg>
    <div class="gp-leyenda peq suave"><span><i class="gp-l-precio"></i>precio de cierre</span><span><i class="gp-l-media"></i>media de 50 días</span>
    ${cono ? `<span><i class="gp-l-cono"></i>donde termina 8 de cada 10 veces en ${cono.dias} días (estadística)</span>` : ""}</div>`;
  const zona = $("#gpZona", cont), cruz = $("#gpCruz", cont), punto = $("#gpPunto", cont);
  let tip = $("#acTip"); if (!tip) { tip = document.createElement("div"); tip.id = "acTip"; tip.className = "tooltip"; tip.hidden = true; document.body.appendChild(tip); }
  const mover = (e) => {
    const r = zona.getBoundingClientRect(), x = e.clientX - r.left + ml;
    let i = 0, mejor = Infinity;
    serie.forEach((p, k) => { const dd = Math.abs(X(p[0]) - x); if (dd < mejor) { mejor = dd; i = k; } });
    const p = serie[i];
    cruz.setAttribute("x1", X(p[0])); cruz.setAttribute("x2", X(p[0])); cruz.hidden = false;
    punto.setAttribute("cx", X(p[0])); punto.setAttribute("cy", Y(p[1])); punto.hidden = false;
    tip.innerHTML = `<b>${acNum(p[1])}</b> ${esc(op.moneda || "")}<br>${new Date(p[0] * 1000).toLocaleDateString(LOC, { day: "numeric", month: "short", year: "numeric" })}${sma[i] ? `<br>media 50 d: ${acNum(sma[i])}` : ""}`;
    tip.hidden = false; tip.style.left = Math.min(innerWidth - 170, e.clientX + 12) + "px"; tip.style.top = (e.clientY - 56) + "px";
  };
  const salir = () => { tip.hidden = true; cruz.hidden = true; punto.hidden = true; };
  zona.addEventListener("pointermove", mover); zona.addEventListener("pointerdown", mover); zona.addEventListener("pointerleave", salir);
}

/* =============================== LISTA =============================== */
VISTAS.acciones = async () => {
  const d = await api("acciones");
  const cal = d.calibracion || {};
  vista.innerHTML = `<h1>💹 Acciones bajo vigilancia</h1>
    <p class="suave peq">Tu lista con precio al día, alertas y las noticias que mueven cada acción —las <b>directas</b> (de la empresa) y
      las <b>indirectas</b> (competidores, proveedores, clientes, su sector y la economía)—, con un pronóstico por escenarios de
      <b>muy probable</b> a <b>muy poco probable</b>. Cada pronóstico se revisa solo al vencer: así ves si de verdad acierta.</p>
    <div class="tarjeta"><div class="fila"><input id="acBuscar" type="search" placeholder="Buscar empresa o símbolo (Nvidia, Ecopetrol, AAPL, ^GSPC…)" autocomplete="off" style="flex:1;min-width:0">
      <button class="btn pri" id="acBuscarBtn">Buscar</button></div><div id="acResultados"></div></div>
    ${d.cartera ? carteraHtml(d.cartera) : ""}
    <div id="acLista"></div>
    ${cal.n ? `<h2>🎯 ¿Aciertan los pronósticos?</h2><div class="stats">
      <div class="stat"><b>${cal.aciertos}/${cal.n}</b><span>dirección acertada</span></div>
      <div class="stat"><b>${acNum(cal.brier, 3)}</b><span>Brier de la IA (0 = perfecto · 0,25 = moneda al aire)</span></div>
      <div class="stat"><b>${cal.dentro_rango} %</b><span>cayó dentro del rango (lo esperado: ~80 %)</span></div>
      ${cal.n_usuario ? `<div class="stat"><b>${acNum(cal.brier_usuario, 3)}</b><span>tu Brier (${cal.aciertos_usuario}/${cal.n_usuario}) vs. IA ${acNum(cal.brier_ia_mismos, 3)} en los mismos</span></div>` : ""}</div>` : ""}
    <p class="suave peq">⚠️ ${esc(d.descargo)}</p>`;
  const pintarLista = (xs) => {
    $("#acLista").innerHTML = xs.length ? `<div class="tarjeta" style="padding:.4rem .8rem"><ul class="temas ac-lista">${xs.map((a) => `
      <li data-s="${esc(a.simbolo)}" tabindex="0">
        <span class="ac-sim"><b>${esc(a.simbolo)}</b><br><span class="suave peq">${esc(a.nombre)}</span></span>
        ${acSpark(a.spark)}
        <span class="ac-precio"><b>${acPrecio(a.precio, a.moneda)}</b><br><span class="peq">${acPct(a.cambio)}</span></span>
        <span class="ac-extra peq">
          ${a.alertas.length ? `<span class="etq medio" title="${esc(a.alertas.map((x) => x.texto).join(" · "))}">🔔 ${esc(acAlertaCorta(a.alertas[0]))}${a.alertas.length > 1 ? ` +${a.alertas.length - 1}` : ""}</span>` : ""}
          ${a.pronostico ? `<span class="etq ${a.pronostico.p_sube >= 55 ? "bien" : a.pronostico.p_sube <= 45 ? "mal" : ""}" title="${esc(a.pronostico.top || "")}">🔮 ${Math.round(a.pronostico.p_sube)} % sube · ${a.pronostico.dias} d</span>` : ""}
          ${a.trabajo ? `<span class="etq medio"><span class="cargando"></span> ${esc(a.trabajo.estado === "corriendo" ? (a.trabajo.fase || "pronosticando") : "en cola")}</span>` : ""}
          ${a.noticias_nuevas ? `<span class="etq">📰 ${a.noticias_nuevas} nuevas</span>` : ""}
          ${a.error ? `<span class="etq mal" title="${esc(a.error)}">sin conexión</span>` : ""}</span></li>`).join("")}</ul></div>
      <div class="fila"><button class="btn peq" id="acTodas">🔮 Pronosticar todas (30 días)</button><button class="btn peq fantasma" id="acRefrescar">🔄 Actualizar precios</button>
        <span class="suave peq">Precios de Yahoo Finance (pueden ir ~15 min atrasados). Cada día, en la actualización diaria, se renuevan solos las noticias y el pronóstico.</span></div>`
      : `<p class="vacio">Aún no vigilas ninguna acción. Busca una arriba y toca «➕ Vigilar».</p>`;
    $$("[data-s]", $("#acLista")).forEach((li) => { li.onclick = () => ir("accion/" + li.dataset.s); li.onkeydown = (e) => { if (e.key === "Enter") ir("accion/" + li.dataset.s); }; });
    if ($("#acRefrescar")) $("#acRefrescar").onclick = () => refrescar();
    if ($("#acTodas")) $("#acTodas").onclick = async () => {
      let n = 0;
      for (const a of xs) { try { await api("accion/pronostico", { simbolo: a.simbolo, dias: 30 }); n++; } catch (e) { aviso(e.message); } }
      aviso(`🔮 ${n} pronósticos en la cola de la IA (mira ⏳)`); refrescar();
    };
  };
  pintarLista(d.acciones);
  const buscar = async () => {
    const q = $("#acBuscar").value.trim(); if (!q) return;
    $("#acResultados").innerHTML = `<p class="suave peq"><span class="cargando"></span> Buscando…</p>`;
    const r = await api("acciones/buscar?q=" + encodeURIComponent(q)).catch((e) => ({ resultados: [], error: e.message }));
    $("#acResultados").innerHTML = r.resultados.length ? `<ul class="temas">${r.resultados.map((x) => `<li style="cursor:default">
      <span style="flex:1;min-width:0"><b>${esc(x.simbolo)}</b> · ${esc(x.nombre)}<br><span class="suave peq">${esc(x.tipo)} · ${esc(x.bolsa)}${x.sector ? " · " + esc(x.sector) : ""}</span></span>
      <button class="btn peq fantasma" data-ver="${esc(x.simbolo)}">Ver</button>
      ${x.vigilada ? `<span class="etq bien">✓ en tu lista</span>` : `<button class="btn peq pri" data-vig="${esc(x.simbolo)}" data-sector="${esc(x.sector)}" data-industria="${esc(x.industria)}">➕ Vigilar</button>`}</li>`).join("")}</ul>`
      : `<p class="suave peq">${esc(r.error || "Sin resultados. Prueba con el símbolo exacto (p. ej. ECOPETROL.CL para la Bolsa de Colombia).")}</p>`;
    $$("[data-ver]", $("#acResultados")).forEach((b) => (b.onclick = () => ir("accion/" + b.dataset.ver)));
    $$("[data-vig]", $("#acResultados")).forEach((b) => (b.onclick = async () => {
      b.disabled = true; b.innerHTML = `<span class="cargando"></span>`;
      try { await api("acciones/vigilar", { simbolo: b.dataset.vig, sector: b.dataset.sector, industria: b.dataset.industria }); aviso(`💹 ${b.dataset.vig} en vigilancia: la IA arma su mapa de relaciones de fondo`); refrescar(); }
      catch (e) { aviso(e.message); b.disabled = false; b.textContent = "➕ Vigilar"; }
    }));
  };
  $("#acBuscarBtn").onclick = buscar;
  $("#acBuscar").onkeydown = (e) => { if (e.key === "Enter") buscar(); };
  // precios al día mientras la vista está abierta (cada minuto, sin redibujar la búsqueda)
  const id = setInterval(async () => { try { pintarLista((await api("acciones")).acciones); } catch (e) {} }, 60000);
  E.salir = () => clearInterval(id);
};

/* =============================== DETALLE =============================== */
VISTAS.accion = async ([sim], q) => {
  if (!sim) return ir("acciones");
  const d = await api("accion?s=" + encodeURIComponent(sim));
  const m = d.meta || {}, ind = d.indicadores || {}, vig = d.vigilada, ult = d.pronosticos[0];
  const rango = q.r || "6m";
  // primero lo que la IA juzgó relevante (y por impacto), al final lo que no mueve el precio
  const peso = (n) => (n.analisis?.relevante === false ? 0 : 1) * 10 + Math.abs(n.analisis?.impacto || 0);
  const ordenar = (xs) => xs.sort((a, b) => peso(b) - peso(a) || b.publicada - a.publicada);
  const directas = ordenar(d.noticias.filter((n) => n.relacion === "directa")), indirectas = ordenar(d.noticias.filter((n) => n.relacion !== "directa"));
  const rel = d.relaciones;
  vista.innerHTML = `<div class="fila entre"><button class="btn peq fantasma" onclick="ir('acciones')">← Mis acciones</button>
      ${vig ? `<button class="btn peq fantasma" id="acQuitar">Dejar de vigilar</button>` : `<button class="btn peq pri" id="acVigilar">➕ Vigilar</button>`}</div>
    <h1 style="margin-bottom:.1rem">${esc(d.nombre)} <span class="suave">· ${esc(d.simbolo)}</span></h1>
    <div class="suave peq">${[d.tipo, d.bolsa, d.sector, d.industria].filter(Boolean).map(esc).join(" · ")}</div>
    <div class="ac-cabeza"><b class="ac-grande">${acPrecio(m.precio, d.moneda)}</b> ${acPct(m.cambio, 2)}
      <span class="suave peq">${m.hora ? "· " + new Date(m.hora * 1000).toLocaleString(LOC, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : ""}</span></div>
    ${d.error ? `<p class="etq mal">No se pudo actualizar el precio: ${esc(d.error)}</p>` : ""}
    ${d.alertas.length ? `<div class="tarjeta" style="border-color:var(--medio)">${d.alertas.map((a) => `<div>🔔 ${a.url ? `<a href="${escUrl(a.url)}" target="_blank" rel="noopener">${esc(a.texto)}</a>` : `<b>${esc(a.texto)}</b>`}</div>`).join("")}</div>` : ""}
    <div class="tarjeta"><div class="chips" style="margin-bottom:.5rem">${Object.entries(AC.rangos).map(([k, v]) => `<button class="chip ${k === rango ? "activo" : ""}" onclick="ir('accion/${esc(d.simbolo)}?r=${k}')">${v[1]}</button>`).join("")}</div>
      <div id="acGraf" class="graf-precio"></div></div>
    <h2>🧭 Lectura rápida</h2>
    <div class="stats">
      <div class="stat"><b class="peq">${acPct(ind.rend?.["5d"])}</b><span>5 días</span></div>
      <div class="stat"><b class="peq">${acPct(ind.rend?.["1m"])}</b><span>1 mes</span></div>
      <div class="stat"><b class="peq">${acPct(ind.rend?.["3m"])}</b><span>3 meses</span></div>
      <div class="stat"><b class="peq">${acPct(ind.rend?.ytd)}</b><span>en el año</span></div>
      <div class="stat"><b class="peq">${acPct(ind.rend?.["1a"])}</b><span>1 año</span></div>
      <div class="stat"><b>${ind.volatilidad == null ? "—" : Math.round(ind.volatilidad) + " %"}</b><span>volatilidad anual</span></div>
      <div class="stat"><b>${ind.rsi == null ? "—" : Math.round(ind.rsi)}</b><span>RSI (14)</span></div>
      <div class="stat"><b class="peq">${acPct(ind.desde_max)}</b><span>desde máx. 52 sem.</span></div>
      ${d.mercado && d.mercado.beta != null ? `<div class="stat" title="Beta: cuánto se mueve cuando el mercado (${esc(d.mercado.nombre)}) se mueve 1 %. Correlación ${acNum(d.mercado.correlacion, 2)} en ${d.mercado.dias} días."><b>${acNum(d.mercado.beta, 2)}</b><span>beta vs. ${esc(d.mercado.referencia)}</span></div>` : ""}</div>
    ${d.mercado && d.mercado.propio != null ? `<p class="peq">📊 Hoy el mercado (${esc(d.mercado.nombre)}) se movió ${acPct(d.mercado.cambio_ref)}; con su beta, el movimiento <b>propio</b> de ${esc(d.simbolo)} fue ${acPct(d.mercado.propio)} ${Math.abs(d.mercado.propio) >= 1.5 ? "— algo de la empresa (o de su sector) la movió: mira las noticias." : "— se movió casi solo por el mercado."}</p>` : ""}
    ${d.lectura.length ? `<ul class="peq">${d.lectura.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}
    <h2>🔮 Pronóstico</h2>
    <div id="acPron">${vig ? `<div class="tarjeta"><div class="fila">
        <label class="peq">Horizonte <select id="acDias">${d.horizontes.map((h) => `<option value="${h}" ${h === 30 ? "selected" : ""}>${h} días</option>`).join("")}</select></label>
        <label class="peq" title="Opcional: antes de ver el de la IA, ¿qué probabilidad le das tú a que suba? Se mide igual que el de la IA al vencer.">Tu estimación de que suba <input id="acMio" type="number" min="1" max="99" placeholder="%" style="width:5rem"></label>
        <button class="btn pri" id="acPronBtn">🔮 Nuevo pronóstico</button></div>
        <div id="acPronEstado" class="suave peq"></div>
        <p class="suave peq" style="margin:.4rem 0 0">Dar tu estimación antes de leer la de la IA es práctica de verdad: al vencer verás quién estuvo mejor calibrado.</p></div>
        ${ult ? pronosticoHtml(ult, d) : `<p class="vacio">Aún no hay pronóstico. Pide uno (tarda unos minutos) o espera a la actualización diaria.</p>`}`
      : `<p class="suave">Vigila esta acción para pedir pronósticos y recibir alertas.</p>`}</div>
    <h2>📰 Noticias que la mueven</h2>
    <div class="chips" style="margin-bottom:.5rem"><button class="chip activo" data-tab="dir">🎯 Directas (${directas.length})</button><button class="chip" data-tab="ind">🕸️ Indirectas (${indirectas.length})</button>
      <button class="chip" id="acNotBtn">🔄 Buscar ahora</button></div>
    <p class="suave peq" id="acNotInfo">Directas: tratan de la empresa. Indirectas: le llegan por un competidor, proveedor, cliente, su sector o la economía.
      ${d.noticias_fecha ? `Última búsqueda: ${new Date(d.noticias_fecha * 1000).toLocaleString(LOC, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}.` : ""}</p>
    <div id="acNoticias"></div>
    <h2>🕸️ De qué depende</h2>
    ${rel ? `<div class="tarjeta"><p>${esc(rel.negocio)}</p>
      ${[["competidores", "⚔️ Competidores"], ["proveedores", "📦 Proveedores clave"], ["clientes", "🤝 Clientes clave"]].map(([k, t]) => (rel[k] || []).length ? `<div class="peq" style="margin:.4rem 0"><b>${t}:</b>
        ${rel[k].map((x) => x.simbolo ? `<button class="chip" onclick="ir('accion/${esc(x.simbolo)}')" title="${esc(x.que || "")}">${esc(x.nombre)} · ${esc(x.simbolo)}</button>` : `<span class="chip" title="${esc(x.que || "")}">${esc(x.nombre)}</span>`).join(" ")}</div>` : "").join("")}
      <b class="peq">🌐 Factores que la mueven</b><ul class="peq">${(rel.factores || []).map((f) => `<li><b>${esc(f.nombre)}</b> — ${esc(f.como)}</li>`).join("")}</ul></div>`
      : `<p class="suave peq">${vig ? "La IA está armando el mapa de relaciones (competidores, proveedores, factores): con él llegan las noticias indirectas." : "Al vigilarla, la IA arma su mapa de relaciones."}</p>`}
    ${d.pronosticos.length > 1 || (ult && ult.resultado) ? `<h2>📒 Historial de pronósticos</h2><div class="tabla-h"><table>
      <tr><th>Fecha</th><th>Horizonte</th><th>Precio</th><th>P(sube) IA</th><th>Tuya</th><th>Resultado</th></tr>
      ${d.pronosticos.map((p) => `<tr><td>${acFecha(p.creado)}</td><td>${p.dias} d</td><td>${acNum(p.precio)}</td><td>${Math.round(p.p_sube)} %</td>
        <td>${p.p_usuario == null ? "—" : Math.round(p.p_usuario) + " %"}</td>
        <td>${p.resultado ? `${acPct(p.resultado.cambio)} ${p.resultado.acierto ? "✅" : "❌"}${p.resultado.dentro_rango ? " · en rango" : " · fuera de rango"}` : `<span class="suave">vence ${acFecha(p.creado + p.dias * 86400)}</span>`}</td></tr>`).join("")}</table></div>` : ""}
    ${vig ? `<h2>⚙️ Alertas y nota</h2><div class="tarjeta"><div class="fila">
      <label class="peq">Avisar si sube de <input id="acArriba" type="number" step="any" value="${vig.alerta_arriba ?? ""}" style="width:7rem"></label>
      <label class="peq">si baja de <input id="acAbajo" type="number" step="any" value="${vig.alerta_abajo ?? ""}" style="width:7rem"></label>
      <label class="peq">si se mueve más de <input id="acPctAl" type="number" step="0.5" min="0" value="${vig.alerta_pct ?? 4}" style="width:4.5rem"> % en el día</label></div>
      <div class="fila" style="margin-top:.5rem"><b class="peq">💼 Mi posición:</b>
        <label class="peq">cantidad <input id="acCant" type="number" step="any" min="0" value="${vig.cantidad ?? ""}" style="width:6rem"></label>
        <label class="peq">precio de compra <input id="acCompra" type="number" step="any" min="0" value="${vig.precio_compra ?? ""}" style="width:7rem"></label>
        <span class="suave peq">(opcional: suma a 💼 Mi cartera)</span></div>
      <textarea id="acNota" placeholder="Tu nota: por qué la sigues, a qué precio la compraste, qué esperas…" style="margin-top:.5rem">${esc(vig.nota || "")}</textarea>
      <div class="fila" style="margin-top:.4rem"><button class="btn peq pri" id="acGuardar">Guardar</button><span class="suave peq">Las alertas salen aquí, en ☀️ Hoy y en el resumen de Hermes por Telegram.</span></div></div>` : ""}
    ${d.conceptos.length ? `<h2>🎓 Para entender esta vista</h2><div class="chips">${d.conceptos.map((c) => `<button class="chip" onclick="ir('tema/${esc(c.id)}')">${esc(c.t)}</button>`).join("")}</div>` : ""}
    <p class="suave peq" style="margin-top:1rem">⚠️ ${esc(d.descargo)}</p>`;

  // gráfico (con el cono del último pronóstico si sigue vigente)
  const dias = AC.rangos[rango][0], desde = Date.now() / 1000 - dias * 86400;
  const visible = d.serie.filter((p) => p[0] >= desde);
  const vigente = ult && ult.creado + ult.dias * 86400 > Date.now() / 1000 && ult.datos.rango?.bajo;
  const rg = ind.rangos?.[ult?.dias || 30];
  const cono = vigente ? { dias: ult.dias, bajo: ult.datos.rango.bajo, alto: ult.datos.rango.alto } : rg ? { dias: ult?.dias || 30, bajo: rg.bajo, alto: rg.alto } : null;
  const dibujar = () => acGrafico($("#acGraf"), visible.length > 1 ? visible : d.serie, { todos: d.serie, cono, moneda: d.moneda, nombre: d.nombre });
  dibujar();
  const alRedimensionar = () => { clearTimeout(alRedimensionar.t); alRedimensionar.t = setTimeout(() => $("#acGraf") && dibujar(), 200); };
  addEventListener("resize", alRedimensionar);
  E.salir = () => { removeEventListener("resize", alRedimensionar); const t = $("#acTip"); if (t) t.hidden = true; };

  // noticias por pestaña
  const pintarNoticias = (xs) => {
    $("#acNoticias").innerHTML = xs.length ? xs.map((n) => {
      const a = n.analisis || {}, im = AC.impacto[a.impacto ?? "x"];
      return `<div class="tarjeta ac-noticia${a.relevante === false ? " ac-irrelevante" : ""}">
        <div class="suave peq">${acFecha(n.publicada)} · ${esc(n.fuente)} · <span title="Por qué está ligada">${esc(a.via || n.via)}</span></div>
        <a href="${escUrl(n.url)}" target="_blank" rel="noopener"><b>${esc(n.titulo)}</b></a>
        ${a.resumen && a.resumen !== n.titulo ? `<div class="peq">${esc(a.resumen)}</div>` : ""}
        <div class="fila" style="margin-top:.3rem">${im ? `<span class="etq ${im[1]}">${im[0]}</span>` : `<span class="etq">sin leer por la IA</span>`}
          ${a.plazo ? `<span class="etq">efecto en ${esc(a.plazo)}</span>` : ""}${a.relevante === false ? `<span class="etq">poco relevante</span>` : ""}</div></div>`;
    }).join("") : `<p class="vacio">Sin noticias en los últimos 14 días.</p>`;
  };
  pintarNoticias(directas);
  $$("[data-tab]").forEach((b) => (b.onclick = () => {
    $$("[data-tab]").forEach((x) => x.classList.toggle("activo", x === b));
    pintarNoticias(b.dataset.tab === "dir" ? directas : indirectas);
  }));
  $("#acNotBtn").onclick = async () => {
    $("#acNotBtn").innerHTML = `<span class="cargando"></span> Buscando…`;
    try { const r = await api("accion/noticias", { simbolo: d.simbolo }); aviso(r.omitido ? "Ya se buscó hace menos de 10 min" : `📰 ${r.nuevas} noticias nuevas`); refrescar(); }
    catch (e) { aviso(e.message); }
  };

  if ($("#acVigilar")) $("#acVigilar").onclick = async () => {
    try { await api("acciones/vigilar", { simbolo: d.simbolo }); aviso("💹 En vigilancia"); refrescar(); } catch (e) { aviso(e.message); }
  };
  if ($("#acQuitar")) $("#acQuitar").onclick = async () => {
    if (!(await preguntarSiNo("¿Dejar de vigilar " + esc(d.simbolo) + "?", "Sale de tu lista y de las alertas. Sus pronósticos guardados no se borran.", "Sí, quitar", "No"))) return;
    await api("acciones/quitar", { simbolo: d.simbolo }); ir("acciones");
  };
  if ($("#acGuardar")) $("#acGuardar").onclick = async () => {
    try {
      await api("acciones/ajustar", { simbolo: d.simbolo, alerta_arriba: $("#acArriba").value, alerta_abajo: $("#acAbajo").value,
        alerta_pct: $("#acPctAl").value, nota: $("#acNota").value, cantidad: $("#acCant").value, precio_compra: $("#acCompra").value });
      aviso("✅ Guardado");
    } catch (e) { aviso(e.message); }
  };
  const seguir = async (id, mapa) => {
    try {
      await esperarTrabajo(id, (t) => { if ($("#acPronEstado")) $("#acPronEstado").innerHTML = `<span class="cargando"></span> ${mapa ? "🕸️ Mapa de relaciones: " : ""}${esc(textoEstado(t))}`; });
      refrescar();
    } catch (e) { if ($("#acPronEstado")) $("#acPronEstado").textContent = "Error: " + e.message; }
  };
  if ($("#acPronBtn")) $("#acPronBtn").onclick = async () => {
    try {
      const j = await api("accion/pronostico", { simbolo: d.simbolo, dias: +$("#acDias").value, p_usuario: $("#acMio").value });
      $("#acPronBtn").disabled = true; seguir(j.trabajo);
    } catch (e) { aviso(e.message); }
  };
  if (d.trabajo && d.trabajo.id) {
    const mapa = d.trabajo.tipo === "relaciones";   // el mapa no impide pedir un pronóstico (que lo usa si ya está)
    if ($("#acPronBtn") && !mapa) $("#acPronBtn").disabled = true;
    seguir(d.trabajo.id, mapa);
  }
};

function pronosticoHtml(p, d) {
  const x = p.datos, base = x.base || {};
  const porCubeta = AC.cubetas.map(([k, t, c]) => [t, c, (x.escenarios || []).filter((e) => e.etiqueta === k)]).filter((c) => c[2].length);
  const lista = (titulo, xs) => xs && xs.length ? `<div><b class="peq">${titulo}</b><ul class="peq">${xs.map((y) => `<li>${esc(y)}</li>`).join("")}</ul></div>` : "";
  return `<div class="tarjeta" style="border-color:var(--acento)">
    <div class="suave peq">${acFecha(p.creado)} · a ${p.dias} días · desde ${acNum(p.precio)} · ${x.noticias_usadas} noticias leídas${p.p_usuario != null ? ` · tu estimación: ${Math.round(p.p_usuario)} %` : ""}</div>
    <div class="ac-prob"><b>${Math.round(p.p_sube)} %</b><span>de que esté <b>más alto</b> en ${p.dias} días · <span class="etq ${x.sesgo === "alcista" ? "bien" : x.sesgo === "bajista" ? "mal" : ""}">sesgo ${esc(x.sesgo)}</span></span></div>
    <div class="barra-prog ac-barra" title="La marca es la estadística sola"><i style="width:${p.p_sube}%"></i><u style="left:${base.p_sube ?? 50}%"></u></div>
    <p class="suave peq">La estadística sola (${base.ventanas || 0} ventanas de ${p.dias} días en 2 años): sube el <b>${Math.round(base.p_sube ?? 50)} %</b> de las veces
      ${base.p10 != null ? `y 8 de cada 10 terminan entre ${acPct(base.p10)} y ${acPct(base.p90)}` : ""}. Rango estimado del precio: <b>${acNum(x.rango?.bajo)} – ${acNum(x.rango?.alto)}</b>.
      ${p.resultado ? `<br><b>Resultado:</b> ${acPct(p.resultado.cambio)} → ${p.resultado.acierto ? "✅ acertó la dirección" : "❌ falló la dirección"}, ${p.resultado.dentro_rango ? "dentro" : "fuera"} del rango.` : ""}</p>
    ${x.margen_motivo ? `<p class="suave peq">🎚️ Margen de la IA frente a la estadística: ${esc(x.margen_motivo)}.</p>` : ""}
    <div class="leccion" id="acResumen">${md(x.resumen || "")}</div>
    ${(x.temas || []).length ? `<div class="peq" style="margin-top:.4rem"><b>🎓 Estúdialo en tu Academia:</b> ${x.temas.map((t) => `<button class="chip" onclick="ir('tema/${esc(t.id)}')">${esc(t.t)}</button>`).join(" ")}</div>` : ""}</div>
  ${porCubeta.map(([t, c, es]) => `<h3>${t}</h3>${es.map((e) => `<div class="tarjeta ac-escenario ac-${c}">
    <div class="fila entre"><b>${AC.flecha[e.direccion] || ""} ${esc(e.titulo)}</b><span class="etq ${c}">${e.probabilidad} %</span></div>
    <div class="peq">${esc(e.que_pasaria)}</div><div class="suave peq" style="margin-top:.25rem"><b>Por qué:</b> ${esc(e.por_que)}</div>
    <div class="peq" style="margin-top:.25rem">✔️ <b>Se estaría cumpliendo si:</b> ${esc(e.confirma)}<br>✖️ <b>Se descarta si:</b> ${esc(e.descarta)}</div>
    ${e.noticias?.length ? `<div class="peq suave" style="margin-top:.25rem">📰 ${e.noticias.map((n) => `<a href="${escUrl(n.url)}" target="_blank" rel="noopener">${esc(n.titulo)}</a> <span class="etq">${esc(n.relacion)}</span>`).join(" · ")}</div>` : ""}</div>`).join("")}`).join("")}
  ${(x.catalizadores || []).length ? `<h3>📅 Catalizadores</h3><div class="tarjeta"><ul class="peq">${x.catalizadores.map((c) => `<li><b>${esc(c.evento)}</b> (${esc(c.cuando)}): ${esc(c.efecto)}</li>`).join("")}</ul></div>` : ""}
  <div class="tarjeta rejilla">${lista("👍 A favor", x.a_favor)}${lista("👎 En contra", x.en_contra)}${lista("👀 Qué vigilar", x.vigilar)}${lista("🎓 Conceptos para aprender", x.aprender)}</div>`;
}

/* tarjeta en ☀️ Hoy: lo guardado (sin esperar a internet), con las alertas primero */
async function acHoy(el) {
  try {
    const d = await api("acciones?rapido=1");
    if (!d.acciones.length || !el.isConnected) return;
    const xs = [...d.acciones].sort((a, b) => b.alertas.length - a.alertas.length).slice(0, 6);
    el.innerHTML = `<h2>💹 Tus acciones</h2><div class="tarjeta" style="padding:.4rem .8rem;cursor:pointer" onclick="ir('acciones')"><ul class="temas ac-lista">${xs.map((a) => `
      <li><span class="ac-sim"><b>${esc(a.simbolo)}</b></span>${acSpark(a.spark)}
      <span class="ac-precio"><b>${acPrecio(a.precio, a.moneda)}</b> <span class="peq">${acPct(a.cambio)}</span></span>
      <span class="ac-extra peq">${a.alertas.length ? `<span class="etq medio">🔔 ${esc(acAlertaCorta(a.alertas[0]))}</span>` : ""}
      ${a.pronostico ? `<span class="etq">🔮 ${Math.round(a.pronostico.p_sube)} %</span>` : ""}</span></li>`).join("")}</ul></div>`;
  } catch (e) { /* sin acciones: no se muestra nada */ }
}

const acAlertaCorta = (a) => a.tipo.startsWith("noticia") ? "📰 " + a.texto.split(":")[0] : a.texto;

/* 💼 cartera: valor, ganancia, concentración y lo que la diversificación le ahorra al riesgo */
function carteraHtml(c) {
  const barras = (xs) => xs.map((x) => `<div class="ac-peso"><span>${esc(x.nombre)}</span><div class="barra-prog"><i style="width:${x.peso}%"></i></div><b>${Math.round(x.peso)} %</b></div>`).join("");
  return `<h2>💼 Mi cartera</h2><div class="tarjeta">
    <div class="stats" style="margin-top:0">
      <div class="stat"><b>${acPrecio(c.total, c.moneda)}</b><span>valor (en ${esc(c.moneda)})</span></div>
      <div class="stat"><b class="peq">${acPct(c.ganancia_pct)}</b><span>ganancia: ${acPrecio(c.ganancia, c.moneda)}</span></div>
      <div class="stat"><b class="peq">${acPrecio(c.hoy, c.moneda)}</b><span>cambio de hoy</span></div>
      ${c.riesgo ? `<div class="stat" title="Volatilidad anual de la cartera completa frente al promedio ponderado de cada acción (${c.riesgo.dias} días)"><b>${Math.round(c.riesgo.volatilidad)} %</b><span>volatilidad de la cartera (sola cada una: ${Math.round(c.riesgo.suma_individual)} %)</span></div>` : ""}</div>
    ${c.riesgo && c.riesgo.ahorro != null ? `<p class="peq">🛡️ La diversificación le quita <b>${Math.round(c.riesgo.ahorro)} %</b> al riesgo: las acciones no suben y bajan todas a la vez.</p>` : ""}
    ${c.avisos.map((a) => `<p class="peq">⚠️ ${esc(a)}</p>`).join("")}
    <div class="rejilla"><div><b class="peq">Por acción</b>${barras(c.posiciones.map((p) => ({ nombre: p.simbolo, peso: p.peso })))}</div>
      <div><b class="peq">Por sector</b>${barras(c.sectores)}</div><div><b class="peq">Por moneda</b>${barras(c.monedas)}</div></div>
    <p class="suave peq">Convertido a ${esc(c.moneda)} con la tasa de hoy. La volatilidad no incluye el efecto del dólar.</p></div>`;
}
