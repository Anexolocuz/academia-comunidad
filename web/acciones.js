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


/* velas japonesas: cuerpo (apertura-cierre) y mechas (máximo-mínimo); verde = cerró arriba de donde abrió; ▲▼ = patrón detectado */
function acVelas(cont, velas, op = {}) {
  if (!velas || velas.length < 2) { cont.innerHTML = `<p class="vacio">Sin velas.</p>`; return; }
  const W = Math.max(280, cont.clientWidth || 600), H = W < 500 ? 230 : 290, ml = 6, mr = 58, mt = 14, mb = 24;
  const lo0 = Math.min(...velas.map((v) => v[3])), hi0 = Math.max(...velas.map((v) => v[2])), pad = (hi0 - lo0) * 0.06 || 1;
  const lo = lo0 - pad, hi = hi0 + pad, n = velas.length, paso = (W - ml - mr) / n, ancho = Math.max(1.5, Math.min(14, paso * 0.7));
  const X = (k) => ml + (k + 0.5) * paso, Y = (v) => mt + (hi - v) / (hi - lo) * (H - mt - mb);
  const salto = (() => { const b = (hi - lo) / 4, e = Math.pow(10, Math.floor(Math.log10(b))); return [1, 2, 2.5, 5, 10].map((m) => m * e).find((m) => m >= b); })();
  let ejes = "";
  for (let v = Math.ceil(lo / salto) * salto; v <= hi; v += salto)
    ejes += `<line class="gp-red" x1="${ml}" x2="${W - mr}" y1="${Y(v)}" y2="${Y(v)}"/><text class="gp-eje" x="${W - mr + 6}" y="${Y(v) + 4}">${acNum(v, salto < 1 ? 2 : 0)}</text>`;
  let ultX = -99;
  velas.forEach((v, k) => {
    const d = new Date(v[0] * 1000), prev = k ? new Date(velas[k - 1][0] * 1000) : null;
    if (prev && d.getMonth() !== prev.getMonth() && X(k) - ultX > 54) { ultX = X(k); ejes += `<text class="gp-eje" x="${ultX}" y="${H - 6}" text-anchor="middle">${d.toLocaleDateString(LOC, { month: "short" })}</text>`; }
  });
  const porTs = new Map((op.patrones || []).map((r) => [r.ts, r]));
  let cuerpo = "", marcas = "";
  velas.forEach((v, k) => {
    const [, o, h, l, c] = v, sube = c >= o, cls = sube ? "vela-sube" : "vela-baja", y1 = Y(Math.max(o, c)), y2 = Y(Math.min(o, c));
    cuerpo += `<line class="${cls}" x1="${X(k)}" x2="${X(k)}" y1="${Y(h)}" y2="${Y(l)}"/><rect class="${cls}" x="${X(k) - ancho / 2}" y="${y1}" width="${ancho}" height="${Math.max(1, y2 - y1)}"/>`;
    const r = porTs.get(v[0]);
    if (r) marcas += `<text class="vela-marca ${r.sesgo === "alcista" ? "ac-sube" : r.sesgo === "bajista" ? "ac-baja" : "ac-igual"}" x="${X(k)}" y="${r.sesgo === "bajista" ? Y(h) - 5 : Y(l) + 14}" text-anchor="middle">${r.sesgo === "bajista" ? "▼" : r.sesgo === "alcista" ? "▲" : "◆"}</text>`;
  });
  cont.innerHTML = `<svg width="${W}" height="${H}" role="img" aria-label="Velas japonesas de ${esc(op.nombre || "")}">${ejes}${cuerpo}${marcas}
    <line class="gp-cruz" id="gvCruz" y1="${mt}" y2="${H - mb}" hidden/><rect x="${ml}" y="0" width="${W - ml - mr}" height="${H}" fill="transparent" id="gvZona"/></svg>
    <div class="gp-leyenda peq suave"><span><i class="vela-l vela-sube"></i>cerró más alto de lo que abrió</span><span><i class="vela-l vela-baja"></i>cerró más bajo</span>
      <span>▲ patrón alcista · ▼ patrón bajista · ◆ indecisión</span></div>`;
  const zona = $("#gvZona", cont), cruz = $("#gvCruz", cont);
  let tip = $("#acTip"); if (!tip) { tip = document.createElement("div"); tip.id = "acTip"; tip.className = "tooltip"; tip.hidden = true; document.body.appendChild(tip); }
  const mover = (e) => {
    const r = zona.getBoundingClientRect(), k = Math.max(0, Math.min(n - 1, Math.floor((e.clientX - r.left) / paso))), v = velas[k], pt = porTs.get(v[0]);
    cruz.setAttribute("x1", X(k)); cruz.setAttribute("x2", X(k)); cruz.hidden = false;
    tip.innerHTML = `<b>${new Date(v[0] * 1000).toLocaleDateString(LOC, { day: "numeric", month: "short", year: "numeric" })}</b><br>abrió ${acNum(v[1])} · cerró ${acNum(v[4])}<br>máx. ${acNum(v[2])} · mín. ${acNum(v[3])}${pt ? `<br>🕯️ ${esc(pt.patron)}` : ""}`;
    tip.hidden = false; tip.style.left = Math.min(innerWidth - 190, e.clientX + 12) + "px"; tip.style.top = (e.clientY - 70) + "px";
  };
  const salir = () => { tip.hidden = true; cruz.hidden = true; };
  zona.addEventListener("pointermove", mover); zona.addEventListener("pointerdown", mover); zona.addEventListener("pointerleave", salir);
}

/* 🕯️ patrones de velas detectados (martillo, hombre colgado, doji, envolventes…) con lo que pasó antes en este mismo activo */
function patronesHtml(pt) {
  const rec = (pt && pt.recientes) || [];
  const fila = (r) => {
    const h = r.historia, col = r.sesgo === "alcista" ? "bien" : r.sesgo === "bajista" ? "mal" : "";
    return `<div class="tarjeta ac-escenario ac-${col || "medio"}"><div class="fila entre"><b>🕯️ ${esc(r.patron)}</b><span class="etq ${col}">${esc(r.sesgo)} · ${acFecha(r.ts)}</span></div>
      <div class="peq">${esc(r.explicacion)}</div>
      <div class="suave peq" style="margin-top:.25rem">${h && h.n >= 5 ? `En este activo, las ${h.n} veces anteriores, 5 sesiones después el precio estaba más alto el <b>${h.sube_pct} %</b> de las veces (cambio medio ${acPct(h.media)}).` : `Pocos casos anteriores en este activo para medirla${h ? ` (${h.n})` : ""}: no te fíes de ella sola.`}</div></div>`;
  };
  return `<h2>🕯️ Velas y martillos</h2>
    <p class="suave peq">Cada vela resume un día: el cuerpo va de la apertura al cierre y las mechas llegan al máximo y al mínimo. Un <b>martillo</b> (cuerpo pequeño arriba y mecha inferior larga tras una caída) sugiere que los vendedores
      perdieron fuerza; el <b>hombre colgado</b> es la misma forma tras una subida y avisa lo contrario. Son pistas, no promesas: mira abajo cuántas veces funcionaron <i>en este mismo activo</i>.</p>
    ${rec.length ? rec.slice(0, 6).map(fila).join("") : `<p class="vacio">No se detectó ningún patrón en las últimas 30 sesiones.</p>`}`;
}

/* espectro del peor al mejor caso: zonas excluyentes que suman 100 %, con la más y la menos probable marcadas */
function casosHtml(c, titulo, nota) {
  if (!c || !c.zonas) return "";
  const col = { peor: "mal", pesimista: "mal", central: "medio", optimista: "bien", mejor: "bien" };
  const max = Math.max(...c.zonas.map((z) => z.prob));
  const rango = (z) => z.desde == null ? `por debajo de ${acNum(z.hasta)}` : z.hasta == null ? `por encima de ${acNum(z.desde)}` : `${acNum(z.desde)} – ${acNum(z.hasta)}`;
  const var_ = (z) => z.desde_pct == null ? `más de ${acNum(Math.abs(z.hasta_pct), 0)} % abajo` : z.hasta_pct == null ? `más de ${acNum(z.desde_pct, 0)} % arriba` : `${acNum(z.desde_pct, 0)} % a ${acNum(z.hasta_pct, 0)} %`;
  return `<h3>${titulo}</h3><div class="ac-espectro" role="list">${c.zonas.map((z) => `
    <div class="ac-zona ac-z-${col[z.clave]}${z.marca === "más probable" ? " ac-z-top" : ""}" role="listitem" title="${esc(rango(z))}">
      <b class="ac-zp">${z.prob} %</b><div class="ac-zb"><i style="height:${Math.max(4, z.prob / max * 100)}%"></i></div>
      <span class="ac-zn">${esc(z.nombre)}</span><span class="peq suave">${esc(var_(z))}</span><span class="peq suave">${esc(rango(z))}</span>
      ${z.marca ? `<span class="etq ${z.marca === "más probable" ? "bien" : ""}">${z.marca === "más probable" ? "⭐ lo más probable" : "lo menos probable"}</span>` : ""}</div>`).join("")}</div>
    <p class="suave peq">${esc(nota)} Las 5 zonas son <b>excluyentes</b> (el precio termina en una sola) y suman 100 %; se calculan con la volatilidad actual y lo que pasó en ${c.ventanas} ventanas de ${c.dias} días de los últimos 2 años${c.ajustado_a_ia ? ", ajustadas a la probabilidad de subir del pronóstico" : ""}.</p>`;
}

/* 🧬 de qué se compone un fondo o índice (qué empresas y qué porcentaje) */
function composicionHtml(c) {
  if (!c) return "";
  if (c.error) return `<p class="suave peq">No pude leer la composición ahora: ${esc(c.error)}</p>`;
  const max = Math.max(...c.filas.map((f) => f.peso));
  return `<div class="tarjeta"><p class="peq" style="margin-top:0">${c.via ? `Un índice no se compra directamente: se compra un fondo que lo copia. Esta es la cartera de <b>${esc(c.via)}</b>. ` : ""}
      Las <b>${c.filas.length}</b> mayores posiciones suman <b>${acNum(c.top_pct, 1)} %</b>; las otras ${acNum(c.n_resto, 0)} empresas reparten el <b>${acNum(c.resto_pct, 1)} %</b> restante.</p>
    <div class="tabla-h"><table class="ac-comp"><tr><th>#</th><th>Empresa</th><th>Peso</th><th></th></tr>
      ${c.filas.map((f, k) => `<tr><td>${k + 1}</td><td><button class="chip" onclick="ir('accion/${esc(f.simbolo)}')">${esc(f.simbolo)}</button> ${esc(f.nombre)}</td>
        <td style="text-align:right"><b>${acNum(f.peso, 2)} %</b></td><td style="width:35%"><div class="barra-prog"><i style="width:${f.peso / max * 100}%"></i></div></td></tr>`).join("")}
      <tr><td></td><td class="suave">Otras ${acNum(c.n_resto, 0)} empresas</td><td style="text-align:right"><b>${acNum(c.resto_pct, 1)} %</b></td><td><div class="barra-prog"><i style="width:${Math.min(100, c.resto_pct / max * 100)}%;opacity:.4"></i></div></td></tr></table></div>
    <p class="suave peq">Concentración: las 10 mayores pesan ${acNum(c.filas.slice(0, 10).reduce((a, f) => a + f.peso, 0), 1)} %. Datos del emisor al cierre del ${esc(c.fecha || "último día")} (${esc(c.fuente)}); ${c.total} posiciones en total.</p></div>`;
}

/* ⚔️ alternativas y competencia: quién es, cuánto rinde frente a los demás y si ya lo vigilas */
function familiaHtml(f, actual) {
  if (!f) return "";
  const faltan = f.grupos.some((g) => g.items.some((x) => !x.vigilada));
  return `<h2>⚔️ ${esc(f.nombre)}</h2><p class="suave peq">${esc(f.descripcion)}</p>
    ${faltan ? `<div class="fila" style="margin-bottom:.5rem"><button class="btn peq pri" id="acFamilia">➕ Vigilar a todos</button><span class="suave peq">${f.nucleo && f.nucleo.length ? "Las ⭐ van a tu lista con alertas; las demás a un grupo plegable. Sin gastar IA." : "Los agrega a tu lista (sin gastar IA)."}</span></div>` : ""}
    ${f.grupos.map((g) => `<h3>${esc(g.titulo)}</h3><div class="tabla-h"><table class="ac-comp"><tr><th>Símbolo</th><th>Qué es</th><th>1 mes</th><th>3 meses</th><th>1 año</th><th>Volat.</th><th>Dividendo</th></tr>
      ${g.items.map((x) => `<tr${x.simbolo === actual ? ` class="ac-actual"` : ""}><td><button class="chip" onclick="ir('accion/${esc(x.simbolo)}')">${esc(x.simbolo)}</button>${x.vigilada ? ` <span title="En tu lista">✓</span>` : ""}</td>
        <td class="peq"><b>${esc(x.nombre)}</b><br><span class="suave">${esc(x.que)}</span></td>
        ${["1m", "3m", "1a"].map((k) => `<td style="text-align:right">${x.rend ? acPct(x.rend[k]) : `<span class="suave">—</span>`}</td>`).join("")}
        <td style="text-align:right">${x.volatilidad == null ? "—" : Math.round(x.volatilidad) + " %"}</td>
        <td style="text-align:right">${x.div_rend == null ? `<span class="suave">—</span>` : x.div_rend > 0 ? acNum(x.div_rend, 1) + " %" : `<span class="suave">no paga</span>`}</td></tr>`).join("")}</table></div>`).join("")}
    <p class="suave peq">Los rendimientos salen de los precios guardados; un símbolo con «—» aún no se ha consultado (ábrelo o vigílalo).</p>`;
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
      <button class="btn pri" id="acBuscarBtn">Buscar</button></div><div id="acResultados"></div>
      ${d.acciones.some((a) => a.grupo === "energia") ? "" : `<div class="fila" style="margin-top:.5rem"><button class="btn peq" id="acEnergia">⚡ Agregar la energía eléctrica del mundo</button>
        <span class="suave peq">Generadoras, redes y fabricantes de ~220 empresas de todos los países y sus fondos. Sin alertas ni IA diaria.</span></div>`}</div>
    ${d.cartera ? carteraHtml(d.cartera) : ""}
    <div id="acVista"></div>
    <div id="acLista"></div>
    ${cal.n ? `<h2>🎯 ¿Aciertan los pronósticos?</h2><div class="stats">
      <div class="stat"><b>${cal.aciertos}/${cal.n}</b><span>dirección acertada</span></div>
      <div class="stat"><b>${acNum(cal.brier, 3)}</b><span>Brier de la IA (0 = perfecto · 0,25 = moneda al aire)</span></div>
      <div class="stat"><b>${cal.dentro_rango} %</b><span>cayó dentro del rango (lo esperado: ~80 %)</span></div>
      ${cal.n_usuario ? `<div class="stat"><b>${acNum(cal.brier_usuario, 3)}</b><span>tu Brier (${cal.aciertos_usuario}/${cal.n_usuario}) vs. IA ${acNum(cal.brier_ia_mismos, 3)} en los mismos</span></div>` : ""}</div>` : ""}
    <p class="suave peq">⚠️ ${esc(d.descargo)}</p>`;
  /* ---- Cómo se ve la lista (se guarda por persona): agrupar en dos niveles, ordenar y mostrar el dividendo ---- */
  let cfg = d.vista, datos = d.acciones, panelAbierto = false;
  const ETQ_NIVEL = { tema: "Tema (familia)", subtema: "Tipo de energía", dividendos: "Dividendos", sector: "Sector", pais: "País de la bolsa", moneda: "Moneda", ninguno: "Sin agrupar" };
  const ETQ_SUB = { ...ETQ_NIVEL, ninguno: "Sin subdividir" };
  const ETQ_ORDEN = { manual: "Mi orden", dividendo: "Dividendo, de mayor a menor", cambio: "Cambio del día", nombre: "Nombre" };
  const ETQ_MESES = { 12: "Últimos 12 meses", 24: "Promedio anual de 24 meses" };
  const ETQ_ABIERTOS = { primero: "Solo el primer grupo", todos: "Todos abiertos", ninguno: "Todos cerrados" };
  const mapa = (xs) => Object.fromEntries(xs.map((x) => [x.clave, x.nombre]));
  const NOM_TEMA = mapa(d.temas), NOM_SUB = mapa(d.subtemas);
  const NOM_DIV = { paga: "💰 Pagan dividendos", nopaga: "🚫 No pagan dividendos", sd: "⏳ Dividendo por conocer" };
  const ORDEN_FIJO = { tema: ["otras", ...d.temas.map((t) => t.clave).filter((c) => c !== "otras")], subtema: d.subtemas.map((x) => x.clave), dividendos: ["paga", "nopaga", "sd"] };
  const claveDe = (nivel, a) => ({ tema: a.tema, subtema: a.subtema || "sin", sector: a.sector || "Sin sector", pais: a.pais, moneda: a.moneda || "—",
    dividendos: !a.dividendo.conocido ? "sd" : a.dividendo.paga ? "paga" : "nopaga", ninguno: "todas" })[nivel];
  const nombreDe = (nivel, c) => nivel === "tema" ? NOM_TEMA[c] || c : nivel === "subtema" ? NOM_SUB[c] || c : nivel === "dividendos" ? NOM_DIV[c] : nivel === "ninguno" ? "Todas tus acciones" : c;
  const abierto = {};   // grupos que la persona abrió o cerró a mano: se conserva al redibujar cada minuto
  const rend = (a) => (a.dividendo.paga && a.dividendo.rend != null ? a.dividendo.rend : -1);
  const ordenarFilas = (xs, orden) => {
    const ys = [...xs];
    if (orden === "dividendo") ys.sort((a, b) => rend(b) - rend(a) || a.nombre.localeCompare(b.nombre, "es"));
    else if (orden === "cambio") ys.sort((a, b) => (b.cambio ?? -1e9) - (a.cambio ?? -1e9));
    else if (orden === "nombre") ys.sort((a, b) => a.nombre.localeCompare(b.nombre, "es"));
    return ys;
  };
  const agrupar = (xs, nivel) => {
    const por = new Map();
    xs.forEach((a) => { const c = claveDe(nivel, a); if (!por.has(c)) por.set(c, []); por.get(c).push(a); });
    const fijo = ORDEN_FIJO[nivel];
    const claves = [...por.keys()].sort((a, b) => fijo ? fijo.indexOf(a) - fijo.indexOf(b) : por.get(b).length - por.get(a).length || String(a).localeCompare(String(b), "es"));
    return claves.map((c) => [c, por.get(c)]);
  };
  const resumenGrupo = (xs) => {
    const pg = xs.filter((a) => a.dividendo.paga && a.dividendo.rend != null);
    const prom = pg.length ? pg.reduce((s, a) => s + a.dividendo.rend, 0) / pg.length : null;
    return `${xs.length}` + (cfg.mostrar_dividendo ? ` · 💰 ${pg.length} pagan${prom != null ? ` · promedio ${acNum(prom, 1)} %` : ""}` : "");
  };
  const chipDividendo = (a) => {
    const dv = a.dividendo;
    if (!cfg.mostrar_dividendo || !dv.conocido) return "";
    if (!dv.paga) return `<span class="etq" title="No pagó dividendos en los últimos ${cfg.dividendo_meses} meses">sin dividendo</span>`;
    const ult = dv.ultimo ? new Date(dv.ultimo * 1000).toLocaleDateString("es") : "—";
    return `<span class="etq bien" title="${esc(acNum(dv.anual, 2) + " " + (a.moneda || "") + " por acción al año · " + dv.pagos + " pagos en " + cfg.dividendo_meses + " meses · último " + ult)}">💰 ${acNum(dv.rend, 1)} %</span>`;
  };
  const filaHtml = (a, flechas) => `
      <li data-s="${esc(a.simbolo)}" tabindex="0">
        <span class="ac-sim"><b>${a.nucleo ? "⭐ " : ""}${esc(a.simbolo)}</b><br><span class="suave peq">${esc(a.nombre)}</span></span>
        ${acSpark(a.spark)}
        <span class="ac-precio"><b>${acPrecio(a.precio, a.moneda)}</b><br><span class="peq">${acPct(a.cambio)}</span></span>
        ${flechas && !a.grupo ? `<span class="ac-orden no-imprimir" aria-label="Orden en tu lista"><button class="btn peq fantasma" data-sube="${esc(a.simbolo)}" title="Subir en la lista" aria-label="Subir ${esc(a.simbolo)}">▲</button><button class="btn peq fantasma" data-baja="${esc(a.simbolo)}" title="Bajar en la lista" aria-label="Bajar ${esc(a.simbolo)}">▼</button></span>` : ""}
        <span class="ac-extra peq">
          ${chipDividendo(a)}
          ${a.alertas.length ? `<span class="etq medio" title="${esc(a.alertas.map((x) => x.texto).join(" · "))}">🔔 ${esc(acAlertaCorta(a.alertas[0]))}${a.alertas.length > 1 ? ` +${a.alertas.length - 1}` : ""}</span>` : ""}
          ${a.pronostico ? `<span class="etq ${a.pronostico.p_sube >= 55 ? "bien" : a.pronostico.p_sube <= 45 ? "mal" : ""}" title="${esc(a.pronostico.top || "")}">🔮 ${Math.round(a.pronostico.p_sube)} % sube · ${a.pronostico.dias} d</span>` : ""}
          ${a.trabajo ? `<span class="etq medio"><span class="cargando"></span> ${esc(a.trabajo.estado === "corriendo" ? (a.trabajo.fase || "pronosticando") : "en cola")}</span>` : ""}
          ${a.noticias_nuevas ? `<span class="etq">📰 ${a.noticias_nuevas} nuevas</span>` : ""}
          ${a.error ? `<span class="etq mal" title="${esc(a.error)}">sin conexión</span>` : ""}</span></li>`;
  const filasHtml = (xs, flechas) => `<ul class="temas ac-lista">${xs.map((a) => filaHtml(a, flechas)).join("")}</ul>`;
  const detalle = (ruta, titulo, resumen, cuerpo, porDefecto, clase) => {
    const op = ruta in abierto ? abierto[ruta] : porDefecto;
    return `<details class="${clase}" data-r="${esc(ruta)}"${clase === "ac-sub" ? ` style="margin:.3rem 0"` : ""}${op ? " open" : ""}><summary><b>${esc(titulo)}</b> <span class="suave peq">· ${resumen}</span></summary>${cuerpo}</details>`;
  };
  const pintarLista = (todas) => {
    datos = todas;
    const n1 = cfg.agrupar, n2 = cfg.subagrupar === n1 ? "ninguno" : cfg.subagrupar;
    const flechas = n1 === "ninguno" && n2 === "ninguno" && cfg.orden === "manual";
    const core = todas.filter((a) => !a.grupo);
    const cuerpoDe = (c1, xs1, abre1) => {
      const subs = agrupar(xs1, n2);
      return subs.length <= 1 ? filasHtml(ordenarFilas(xs1, cfg.orden), flechas)
        : subs.map(([c2, xs2]) => detalle(`${c1}/${c2}`, nombreDe(n2, c2), resumenGrupo(xs2), filasHtml(ordenarFilas(xs2, cfg.orden), false), abre1, "ac-sub")).join("");
    };
    const grupos = agrupar(todas, n1);
    const abre = (gi) => cfg.abiertos === "todos" || (cfg.abiertos === "primero" && gi === 0);
    $("#acLista").innerHTML = todas.length ? (n1 === "ninguno"
        ? `<div class="tarjeta" style="padding:.4rem .8rem">${cuerpoDe("todas", todas, true)}</div>`
        : grupos.map(([c1, xs1], gi) => detalle(c1, nombreDe(n1, c1), resumenGrupo(xs1), cuerpoDe(c1, xs1, abre(gi)), abre(gi), "tarjeta")).join(""))
      + `<div class="fila"><button class="btn peq" id="acTodas">🔮 Pronosticar las de mi lista principal (30 días)</button><button class="btn peq fantasma" id="acRefrescar">🔄 Actualizar precios</button>
        <span class="suave peq">Precios de Yahoo Finance (pueden ir ~15 min atrasados). Cada día se renuevan solos las noticias y el pronóstico de las de la lista principal; los grupos plegables solo guardan precios.</span></div>`
      : `<p class="vacio">Aún no vigilas ninguna acción. Busca una arriba y toca «➕ Vigilar».</p>`;
    $$("details[data-r]", $("#acLista")).forEach((dt) => (dt.ontoggle = () => { abierto[dt.dataset.r] = dt.open; }));
    $$("[data-s]", $("#acLista")).forEach((li) => { li.onclick = () => ir("accion/" + li.dataset.s); li.onkeydown = (e) => { if (e.key === "Enter") ir("accion/" + li.dataset.s); }; });
    const mover = async (sim, delta) => {
      const orden = core.map((x) => x.simbolo), i = orden.indexOf(sim), j = i + delta;
      if (i < 0 || j < 0 || j >= orden.length) return;
      [orden[i], orden[j]] = [orden[j], orden[i]];
      try { await api("acciones/orden", { simbolos: orden }); refrescar(); } catch (e) { aviso(e.message); }
    };
    $$("[data-sube]", $("#acLista")).forEach((b) => (b.onclick = (e) => { e.stopPropagation(); mover(b.dataset.sube, -1); }));
    $$("[data-baja]", $("#acLista")).forEach((b) => (b.onclick = (e) => { e.stopPropagation(); mover(b.dataset.baja, 1); }));
    if ($("#acRefrescar")) $("#acRefrescar").onclick = () => refrescar();
    if ($("#acTodas")) $("#acTodas").onclick = async () => {
      let n = 0;
      for (const a of core) { try { await api("accion/pronostico", { simbolo: a.simbolo, dias: 30 }); n++; } catch (e) { aviso(e.message); } }
      aviso(`🔮 ${n} pronósticos en la cola de la IA (mira ⏳)`); refrescar();
    };
  };
  const pintarVista = () => {
    const sel = (id, etq, etqs, claves, valor) => `<label class="peq" style="display:flex;flex-direction:column;gap:.15rem">${etq}
      <select id="${id}">${claves.map((c) => `<option value="${esc(c)}"${String(c) === String(valor) ? " selected" : ""}>${esc(etqs[c] ?? c)}</option>`).join("")}</select></label>`;
    const o = d.opciones;
    $("#acVista").innerHTML = `<details class="tarjeta"${panelAbierto ? " open" : ""} id="acVistaDet"><summary><b>⚙️ Cómo ver mi lista</b>
        <span class="suave peq">· agrupada por ${esc(ETQ_NIVEL[cfg.agrupar].toLowerCase())}${cfg.subagrupar !== "ninguno" && cfg.subagrupar !== cfg.agrupar ? `, subdividida por ${esc(ETQ_SUB[cfg.subagrupar].toLowerCase())}` : ""} · orden: ${esc(ETQ_ORDEN[cfg.orden].toLowerCase())}</span></summary>
      <div class="fila" style="flex-wrap:wrap;gap:.8rem;margin-top:.6rem;align-items:flex-end">
        ${sel("vAgrupar", "Agrupar por", ETQ_NIVEL, o.agrupar, cfg.agrupar)}
        ${sel("vSub", "Subdividir por", ETQ_SUB, o.subagrupar, cfg.subagrupar)}
        ${sel("vOrden", "Ordenar cada grupo por", ETQ_ORDEN, o.orden, cfg.orden)}
        ${sel("vMeses", "El dividendo se calcula con", ETQ_MESES, o.dividendo_meses, cfg.dividendo_meses)}
        ${sel("vAbiertos", "Al abrir la lista", ETQ_ABIERTOS, o.abiertos, cfg.abiertos)}
        <label class="peq" style="display:flex;gap:.35rem;align-items:center"><input type="checkbox" id="vDiv"${cfg.mostrar_dividendo ? " checked" : ""}> Mostrar el dividendo en cada fila</label>
      </div>
      <p class="suave peq">«Tipo de energía» separa la energía en renovables, nucleares, fósiles, mixtas, redes, equipos y almacenamiento (solo aplica a ⚡ energía eléctrica). «Dividendos» separa las que pagan de las que no y, con «Dividendo, de mayor a menor», ordena por el rendimiento anual (dividendos de los últimos 12 meses ÷ precio de hoy; incluye pagos especiales y, en los fondos, sus distribuciones). El país es el de la bolsa donde cotiza.</p></details>`;
    $("#acVistaDet").ontoggle = (e) => { panelAbierto = e.target.open; };
    const guardar = async (cambio) => {
      try {
        cfg = (await api("acciones/vista", cambio)).vista;
        Object.keys(abierto).forEach((k) => delete abierto[k]);
        datos = (await api("acciones")).acciones;
        pintarVista(); pintarLista(datos);
      } catch (e) { aviso(e.message); }
    };
    $("#vAgrupar").onchange = (e) => guardar({ agrupar: e.target.value });
    $("#vSub").onchange = (e) => guardar({ subagrupar: e.target.value });
    $("#vOrden").onchange = (e) => guardar({ orden: e.target.value });
    $("#vMeses").onchange = (e) => guardar({ dividendo_meses: Number(e.target.value) });
    $("#vAbiertos").onchange = (e) => guardar({ abiertos: e.target.value });
    $("#vDiv").onchange = (e) => guardar({ mostrar_dividendo: e.target.checked });
  };
  pintarVista();
  pintarLista(d.acciones);
  if ($("#acEnergia")) $("#acEnergia").onclick = async () => {
    if (!(await preguntarSiNo("¿Agregar la energía eléctrica del mundo?", "Pone en tu lista a GE Vernova, Talen, Constellation, Vistra, NextEra, ISA, Celsia y GEB, y en un grupo plegable a sus rivales y a las eléctricas de todos los países (~220). Las ocho primeras tendrán alertas; el resto no.", "Sí, agregar", "No"))) return;
    try {
      const r = await api("acciones/familia", { familia: "energia" });
      aviso(r.en_curso ? "Ya se están agregando" : `⚡ Agregando ${r.en_segundo_plano || ""} en segundo plano: aparecen en unos minutos`);
      setTimeout(refrescar, 15000);
    } catch (e) { aviso(e.message); }
  };
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
  let vistaGraf = q.g || (() => { try { return localStorage.getItem("acGraf"); } catch (e) { return null; } })() || "linea";
  if (vistaGraf !== "velas") vistaGraf = "linea";
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
      <div class="chips" style="margin:.2rem 0 .5rem"><span class="suave peq">Ver como:</span>
        <button class="chip ${vistaGraf === "linea" ? "activo" : ""}" data-graf="linea">📈 Línea</button><button class="chip ${vistaGraf === "velas" ? "activo" : ""}" data-graf="velas">🕯️ Velas</button></div>
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
      <div class="stat" title="${esc((d.dividendos.historial || []).slice(-6).map((x) => new Date(x[0] * 1000).toLocaleDateString("es") + ": " + acNum(x[1], 2)).join(" · ") || "Sin pagos en los últimos 2 años")}"><b>${d.dividendos.vista.paga ? acNum(d.dividendos.vista.rend, 1) + " %" : d.dividendos.vista.conocido ? "No paga" : "—"}</b><span>dividendo anual (${d.dividendos.meses} m)${d.dividendos.vista.paga ? ` · ${d.dividendos.vista.pagos} pagos` : ""}</span></div>
      <div class="stat"><b class="peq">${acPct(ind.desde_max)}</b><span>desde máx. 52 sem.</span></div>
      ${d.mercado && d.mercado.beta != null ? `<div class="stat" title="Beta: cuánto se mueve cuando el mercado (${esc(d.mercado.nombre)}) se mueve 1 %. Correlación ${acNum(d.mercado.correlacion, 2)} en ${d.mercado.dias} días."><b>${acNum(d.mercado.beta, 2)}</b><span>beta vs. ${esc(d.mercado.referencia)}</span></div>` : ""}</div>
    ${d.mercado && d.mercado.propio != null ? `<p class="peq">📊 Hoy el mercado (${esc(d.mercado.nombre)}) se movió ${acPct(d.mercado.cambio_ref)}; con su beta, el movimiento <b>propio</b> de ${esc(d.simbolo)} fue ${acPct(d.mercado.propio)} ${Math.abs(d.mercado.propio) >= 1.5 ? "— algo de la empresa (o de su sector) la movió: mira las noticias." : "— se movió casi solo por el mercado."}</p>` : ""}
    ${d.lectura.length ? `<ul class="peq">${d.lectura.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}
    ${patronesHtml(d.patrones)}
    ${d.con_composicion ? `<h2>🧬 De qué se compone</h2><div id="acComp"><p class="suave peq"><span class="cargando"></span> Leyendo la composición…</p></div>` : ""}
    ${familiaHtml(d.familia, d.simbolo)}
    ${ind.rangos?.[30]?.casos ? casosHtml(ind.rangos[30].casos, "🎚️ Del peor al mejor caso a 30 días (solo estadística)", "Esto es lo que dice el precio por sí solo, sin IA ni noticias.") : ""}
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
    <div class="fila entre"><h2 style="margin-bottom:0">🕸️ De qué depende</h2>${vig && !d.trabajo ? `<button class="btn peq fantasma" id="acRelBtn" title="Vuelve a pedirle a la IA el mapa de competidores, proveedores, clientes y factores">🔄 Rehacer el mapa</button>` : ""}</div>
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
  const velasVisibles = (d.velas || []).filter((v) => v[0] >= desde);
  const dibujar = () => {
    if (vistaGraf === "velas" && velasVisibles.length > 1) acVelas($("#acGraf"), velasVisibles, { nombre: d.nombre, patrones: (d.patrones?.recientes || []) });
    else acGrafico($("#acGraf"), visible.length > 1 ? visible : d.serie, { todos: d.serie, cono, moneda: d.moneda, nombre: d.nombre });
  };
  $$("[data-graf]").forEach((b) => (b.onclick = () => {
    vistaGraf = b.dataset.graf; try { localStorage.setItem("acGraf", vistaGraf); } catch (e) {}
    $$("[data-graf]").forEach((x) => x.classList.toggle("activo", x === b)); dibujar();
  }));
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

  if (d.con_composicion) api("accion/composicion?s=" + encodeURIComponent(d.simbolo)).then((r) => { if ($("#acComp")) $("#acComp").innerHTML = composicionHtml(r.composicion); })
    .catch((e) => { if ($("#acComp")) $("#acComp").innerHTML = `<p class="suave peq">No pude leer la composición: ${esc(e.message)}</p>`; });
  if ($("#acFamilia")) $("#acFamilia").onclick = async () => {
    $("#acFamilia").disabled = true; $("#acFamilia").innerHTML = `<span class="cargando"></span> Agregando…`;
    try {
      const r = await api("acciones/familia", { familia: d.familia.clave });
      aviso(r.en_segundo_plano ? `💹 Agregando ${r.en_segundo_plano} en segundo plano: aparecen en tu lista en unos minutos` : r.en_curso ? "Ya se están agregando" : `💹 ${r.agregados.length} agregados` + (Object.keys(r.fallidos).length ? `; fallaron: ${Object.keys(r.fallidos).join(", ")}` : ""));
      setTimeout(refrescar, r.en_segundo_plano ? 15000 : 0);
    }
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
  if ($("#acRelBtn")) $("#acRelBtn").onclick = async () => {
    try { const j = await api("accion/relaciones", { simbolo: d.simbolo }); $("#acRelBtn").disabled = true; aviso("🕸️ La IA rehace el mapa (mira ⏳)"); seguir(j.trabajo, true); }
    catch (e) { aviso(e.message); }
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
  const casos = x.casos || d.indicadores?.rangos?.[p.dias]?.casos;
  const nombreCaso = { peor: "💥 Peor caso", pesimista: "🔻 Pesimista", central: "➖ Central", optimista: "🔺 Optimista", mejor: "🚀 Mejor caso" };
  const porCaso = (x.escenarios || []).some((e) => e.caso) ? Object.keys(nombreCaso).map((k) => [nombreCaso[k] + (casos ? ` · ${casos.zonas.find((z) => z.clave === k)?.prob ?? ""} %` : ""),
    k === "peor" || k === "pesimista" ? "mal" : k === "central" ? "medio" : "bien", (x.escenarios || []).filter((e) => e.caso === k)]).filter((c) => c[2].length) : null;
  const porCubeta = porCaso || AC.cubetas.map(([k, t, c]) => [t, c, (x.escenarios || []).filter((e) => e.etiqueta === k)]).filter((c) => c[2].length);
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
  ${x.casos ? casosHtml(x.casos, "🎚️ Del peor al mejor caso", "Aquí sí entra el pronóstico de la IA.") : casos ? casosHtml(casos, "🎚️ Del peor al mejor caso (solo estadística)", "Este pronóstico es anterior a esta vista: se muestra la estadística sin el ajuste de la IA.") : ""}
  <h3 style="margin-bottom:.1rem">🧩 Escenarios concretos${porCaso ? ", ordenados del peor al mejor caso" : ""}</h3><p class="suave peq" style="margin-top:0">Cada escenario es un evento que <b>puede ocurrir junto con otros</b>, por eso su probabilidad no compite con la de los demás ni suma 100 %.</p>
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
