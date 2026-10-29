/* Academia — interfaz (sin frameworks). Rutas con hash: #/hoy, #/tema/<id>... */
"use strict";
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const vista = $("#vista");
const E = {};  // estado compartido
const LOC = /^es\b/i.test(navigator.language || "") ? navigator.language : "es";   // fechas en el español de cada persona
const escUrl = (u) => (/^https?:\/\//i.test(String(u ?? "")) ? esc(u) : "#");   // solo http(s): nada de javascript: desde RSS o la IA
const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const NIVELES = { 1: "Fundamentos", 2: "Intermedio", 3: "Avanzado", 4: "Experto", 5: "Horizonte" };
const AREA_ES = {};

async function api(ruta, datos, metodo) {
  const op = { method: metodo || (datos ? "POST" : "GET"), headers: {} };
  if (datos) { op.body = JSON.stringify(datos); op.headers["Content-Type"] = "application/json"; }
  const r = await fetch("api/" + ruta, op);
  const j = await r.json().catch(() => ({ error: "respuesta inválida (" + r.status + ")" }));
  if (j && j.error) throw new Error(j.error);
  return j;
}

function aviso(t, ms = 2600) {
  const a = $("#aviso"); a.textContent = t; a.hidden = false;
  clearTimeout(aviso._t); aviso._t = setTimeout(() => (a.hidden = true), ms);
}

function modal(html, alAbrir) {
  const m = $("#modal"); $("#modalCaja").innerHTML = html; m.hidden = false;
  if (alAbrir) alAbrir($("#modalCaja"));
  return () => (m.hidden = true);
}
function cerrarModal() { $("#modal").hidden = true; }
$("#modal").addEventListener("click", (e) => { if (e.target.id === "modal") cerrarModal(); });
// Escape y cambiar de vista cierran la ventana (lo que había en ella queda guardado: pruebas, ubicación, resultados)
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("#modal").hidden) cerrarModal(); });
window.addEventListener("hashchange", () => { if (!$("#modal").hidden) cerrarModal(); });

/* ---------- markdown + LaTeX + voz ---------- */
marked.setOptions({ gfm: true, breaks: false });
function md(texto) {
  // proteger LaTeX de marked: $$...$$ y $...$
  const guard = [];
  let t = String(texto || "").replace(/\$\$([\s\S]+?)\$\$/g, (m) => { guard.push(m); return `@@M${guard.length - 1}@@`; })
    .replace(/(^|[^\\$])\$([^\n$]+?)\$/g, (m, a, b) => { guard.push("$" + b + "$"); return `${a}@@M${guard.length - 1}@@`; })
    .replace(/\\\[([\s\S]+?)\\\]/g, (m) => { guard.push(m); return `@@M${guard.length - 1}@@`; })
    .replace(/\\\(([\s\S]+?)\\\)/g, (m) => { guard.push(m); return `@@M${guard.length - 1}@@`; });
  let h = marked.parse(t);
  h = h.replace(/@@M(\d+)@@/g, (m, i) => esc(guard[+i]));
  return DOMPurify.sanitize(h, { ADD_TAGS: ["details", "summary"] });
}
function renderMath(el) {
  try {
    renderMathInElement(el, { delimiters: [
      { left: "$$", right: "$$", display: true }, { left: "\\[", right: "\\]", display: true },
      { left: "$", right: "$", display: false }, { left: "\\(", right: "\\)", display: false }],
      throwOnError: false });
  } catch (e) { /* sin fórmulas */ }
}
function pintarMd(el, texto, idioma) {
  el.innerHTML = md(texto); renderMath(el);
  $$("a", el).forEach((a) => { a.target = "_blank"; a.rel = "noopener"; });
  if (idioma) ponerVoz(el, idioma);
}
const NO_LATINO = /[Ѐ-ӿ぀-ヿ㐀-鿿가-힯]/;
function ponerVoz(el, idioma) {
  // botón 🔊 en celdas y líneas con texto del idioma estudiado
  const prueba = idioma.startsWith("de") || idioma.startsWith("en") ? null : NO_LATINO;
  $$("td:first-child, li, p, h3", el).forEach((n) => {
    const t = n.innerText.trim();
    if (!t || t.length > 300 || (prueba && !prueba.test(t))) return;
    if (!prueba && n.tagName !== "TD") return;  // alemán/inglés: solo tablas de vocabulario
    const b = document.createElement("button"); b.className = "hablar"; b.textContent = "🔊"; b.title = "Escuchar";
    b.onclick = (e) => { e.stopPropagation(); hablar(soloIdioma(t, prueba), idioma); };
    n.appendChild(b);
  });
}
function soloIdioma(t, prueba) {
  if (!prueba) return t.split(/[|(—–-]/)[0].trim();
  const partes = t.split(/[\s,;:()|—–-]+/).filter((p) => prueba.test(p));
  return partes.join(" ") || t;
}
function hablar(texto, idioma) {
  if (!("speechSynthesis" in window)) return aviso("Este navegador no puede leer en voz alta");
  speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(texto); u.lang = idioma; u.rate = 0.85;
  const voz = speechSynthesis.getVoices().find((v) => v.lang.replace("_", "-").startsWith(idioma.slice(0, 2)));
  if (voz) u.voice = voz;
  speechSynthesis.speak(u);
}
document.addEventListener("selectionchange", () => {
  const s = String(getSelection()); const b = $("#leerSel");
  if (b) b.hidden = !(s.trim() && E.idiomaActual);
});

/* ---------- trabajos de la IA (cola con espera) ---------- */
async function esperarTrabajo(id, alCambiar) {
  let decidido = false;
  for (;;) {
    let t;
    try { t = await api("trabajo?id=" + id); }
    catch (e) {   // api() lanza con el error real del trabajo; un corte de red no es un fallo: se sigue esperando
      if (e instanceof TypeError || /inválida/.test(e.message)) { await new Promise((r) => setTimeout(r, 3000)); continue; }
      t = { estado: "error", error: e.message };
    }
    alCambiar && alCambiar(t);
    if (t.estado === "listo") return t.resultado;
    if (t.estado === "error" && await preguntarReintento(t.error)) { await api("trabajo/reintentar", { id }); continue; }
    if (t.estado === "error" || t.estado === "desconocido") throw new Error(t.error || "el trabajo se perdió (¿se reinició el servidor?)");
    if (t.estado === "conflicto" && !decidido) {
      decidido = true;
      if (E.permitirInterrumpir === undefined) { try { E.permitirInterrumpir = (await api("ia")).permitir_interrumpir; } catch (e) {} }
      if (!E.permitirInterrumpir) { await new Promise((r) => setTimeout(r, 3000)); continue; }   // por defecto: esperar en la cola, sin preguntar
      const p = await preguntarConflicto(t.otros);
      if (p) await api("trabajo/decidir", { id, permiso: p });
    }
    await new Promise((r) => setTimeout(r, t.estado === "corriendo" ? 900 : 1600));
  }
}
// Una tarea de la IA falló: ofrecer reintentarla ahí mismo (vuelve a la cola con la misma prioridad)
function preguntarReintento(error) {
  return new Promise((ok) => {
    modal(`<h2>❌ La tarea de la IA falló</h2><p class="suave peq">${esc(error || "error desconocido")}</p>
      <p>Puedes reintentarla: vuelve a la cola y la IA la hace de nuevo desde el principio.</p>
      <div class="fila"><button class="btn pri" id="rtSi">🔄 Reintentar</button><button class="btn" id="rtNo">Ahora no</button></div>`, (m) => {
      $("#rtSi", m).onclick = () => { cerrarModal(); ok(true); };
      $("#rtNo", m).onclick = () => { cerrarModal(); ok(false); };
    });
  });
}
async function reintentarTrabajos(ids) {
  try { const r = await api("trabajo/reintentar", { ids }); aviso(`🔄 ${r.reintentados} tarea(s) de vuelta en la cola`); }
  catch (e) { aviso("No se pudo reintentar: " + e.message); }
  E.colaHtml = null; if (location.hash.includes("cola")) refrescar();
}
function preguntarConflicto(otros) {
  return new Promise((ok) => {
    modal(`<h2>La IA local está ocupada</h2>
      <p>Otro programa tiene cargado <b>${esc(otros.join(", "))}</b> (probablemente Hermes u Open WebUI).
      Si la Academia carga su modelo, ese programa pierde el suyo y su tarea en curso puede fallar.</p>
      <div class="fila" style="flex-direction:column;align-items:stretch">
        <button class="btn" data-p="esperar">⏳ Esperar a que termine (recomendado)</button>
        <button class="btn" data-p="ligero">⚡ Usar el modelo ligero ahora (más rápido, menos preciso)</button>
        ${E.permitirInterrumpir === false ? "" : `<button class="btn" data-p="interrumpir">⚠️ Interrumpir y usar el modelo principal</button>`}
      </div>`, (c) => $$("[data-p]", c).forEach((b) => (b.onclick = () => { cerrarModal(); ok(b.dataset.p === "esperar" ? null : b.dataset.p); })));
  });
}
function textoEstado(t) {
  if (!t) return "";
  if (t.estado === "cola") return `En cola (puesto ${t.pos || "?"})… la IA está terminando otra tarea`;
  if (t.estado === "conflicto") return `En cola: la IA está terminando una tarea de otra app${t.otros && t.otros.length ? ` (${t.otros.join(", ")})` : ""}; la tuya arranca sola cuando quede libre`;
  if (t.estado === "corriendo") return (t.fase || "Trabajando") + "…";
  return t.estado;
}

/* ---------- tiempo de estudio REAL (2026-10-11) ----------
   Antes contaba 30 s cada 30 s con la pestaña visible, aunque nadie la usara (una lección abierta toda la noche
   sumaba 12 h). Ahora cada 5 s solo cuenta si hubo una acción real (desplazar, tocar, clic, tecla, escribir) hace
   poco, o si está sonando el audio 🔊. «Hace poco» = lo que tardas en leer la pantalla que tienes delante a tu
   velocidad medida, con margen (60-240 s): leer un párrafo largo sin tocar nada sigue contando. */
const ACT = { ultima: Date.now(), acumulado: 0, acciones: 0, audio: 0 };
["scroll", "wheel", "pointerdown", "keydown", "touchstart", "input", "mousemove"].forEach((ev) =>
  addEventListener(ev, () => { if (Date.now() - ACT.ultima > 1000) ACT.acciones++; ACT.ultima = Date.now(); }, { passive: true, capture: true }));
const hablando = () => "speechSynthesis" in window && speechSynthesis.speaking;
function umbralInactivo() {
  const wpm = E.wpm || 180;
  const pal = LECT.activa ? LECT.palabrasEnPantalla() : 0;
  return Math.min(240, Math.max(60, (pal / wpm) * 60 * 1.5));
}
const estudioActivo = () => document.visibilityState === "visible" && (Date.now() - ACT.ultima < umbralInactivo() * 1000 || hablando());
function enviarTiempo() {
  if (ACT.acumulado < 5) return;
  const s = ACT.acumulado; ACT.acumulado = 0;
  api("tiempo", { segundos: s, area: E.areaActual || null, tema: E.temaActual || null, metodo: E.metodo }).catch(() => {});
}
setInterval(() => {
  if (!E.estudiando || !estudioActivo()) return;
  ACT.acumulado += 5; LECT.tick(5);
}, 5000);
setInterval(enviarTiempo, 30000);
addEventListener("pagehide", () => { enviarTiempo(); LECT.terminar(); });
document.addEventListener("visibilitychange", () => { if (document.visibilityState === "hidden") { enviarTiempo(); LECT.enviar(); } });

/* ---------- lectura: cuánto leíste, a qué velocidad, por idioma y fórmulas ----------
   El texto se parte en bloques (párrafos, ítems, filas, fórmulas). Cada bloque es «es», el idioma que estudias
   («de», «en», «ja»…) o «formulas». Con actividad real, el tiempo se reparte entre los bloques que están en la
   franja central de la pantalla (pesando por palabras; una fórmula ≈ 12 palabras de esfuerzo). Un bloque cuenta
   como leído cuando estuvo en pantalla al menos lo que tardarías en leerlo a 3× tu velocidad. */
const PALABRAS_ES = /\b(el|la|los|las|que|de|del|y|en|un|una|por|para|con|se|no|como|su|al|lo|más|pero|este|esta)\b/gi;
const PALABRAS_EN = /\b(the|and|is|are|of|to|in|that|it|you|with|for|this|be|was|have|not|on|at)\b/gi;
const PALABRAS_DE = /\b(der|die|das|und|ist|nicht|ich|mit|zu|ein|eine|den|sie|auf|für|von|sich|auch|wir)\b/gi;
function idiomaBloque(t, idioma) {
  const base = (idioma || "").slice(0, 2);
  if (!base || base === "es") return "es";
  if (["ja", "zh", "ko", "ru"].includes(base)) return NO_LATINO.test(t) ? base : "es";
  const n = (re) => (t.match(re) || []).length;
  const es = n(PALABRAS_ES), otro = n(base === "de" ? PALABRAS_DE : base === "en" ? PALABRAS_EN : /$^/g);
  return otro > es ? base : "es";
}
function contarPalabras(t, cat) {
  if (["ja", "zh"].includes(cat)) return Math.round((t.match(/[぀-ヿ㐀-鿿]/g) || []).length / 2.5);   // ≈ caracteres por palabra
  return (t.match(/\S+/g) || []).length;
}
const LECT = {
  activa: null,
  iniciar(el, info) {
    if (this.activa && this.activa.el === el) return this.medir();
    this.terminar();
    this.activa = { id: Date.now().toString(36) + Math.random().toString(36).slice(2, 8), el, ...info, inicio: Date.now() / 1000,
      cats: {}, seg: 0, acciones0: ACT.acciones, bloques: [], leidos: new Set(), firma: "" };
    this.medir();
  },
  medir() {   // (re)parte el texto en bloques; se llama otra vez si la IA agrega partes mientras lees
    const L = this.activa; if (!L) return;
    const firma = L.el.childElementCount + ":" + L.el.textContent.length;
    if (firma === L.firma) return; L.firma = firma;
    const sel = "p, li, h1, h2, h3, h4, tr, pre, blockquote";
    const nodos = $$(sel, L.el).filter((n) => !n.parentElement.closest(sel));   // sin contar dos veces lo anidado
    L.bloques = nodos.map((n, i) => {
      const formulas = $$(".katex", n).filter((k) => !k.parentElement.closest(".katex")).length;
      const copia = n.cloneNode(true); $$(".katex, .hablar", copia).forEach((k) => k.remove());
      const txt = copia.textContent.trim();
      const cat = formulas && contarPalabras(txt, "es") < 8 * formulas ? "formulas" : idiomaBloque(txt, L.idioma);
      return { n, i, cat, palabras: contarPalabras(txt, cat), formulas, seg: 0 };
    }).filter((b) => b.palabras || b.formulas);
    L.total = L.bloques.reduce((a, b) => a + b.palabras + b.formulas * 12, 0) || 1;
  },
  palabrasEnPantalla() {
    const L = this.activa; if (!L || !L.el.isConnected) return 0;
    return this.visibles().reduce((a, b) => a + b.palabras + b.formulas * 12, 0);
  },
  visibles() {
    const arriba = innerHeight * 0.1, abajo = innerHeight * 0.9;
    return this.activa.bloques.filter((b) => { const r = b.n.getBoundingClientRect(); return r.bottom > arriba && r.top < abajo && r.height > 0; });
  },
  tick(s) {
    const L = this.activa; if (!L) return;
    if (!L.el.isConnected) return this.terminar();
    this.medir();
    const vis = this.visibles(); if (!vis.length) return;
    const peso = vis.reduce((a, b) => a + b.palabras + b.formulas * 12, 0) || 1;
    const wpm = E.wpm || 180;
    vis.forEach((b) => {
      const parte = s * (b.palabras + b.formulas * 12) / peso;
      b.seg += parte; L.seg += parte;
      const c = L.cats[b.cat] || (L.cats[b.cat] = { seg: 0, palabras: 0, formulas: 0 });
      c.seg += parte;
      if (!L.leidos.has(b.i) && b.seg >= ((b.palabras + b.formulas * 12) / (wpm * 3)) * 60) {
        L.leidos.add(b.i); c.palabras += b.palabras; c.formulas += b.formulas;
      }
    });
    if (hablando()) ACT.audio++;
    if (Date.now() - (L.enviado || 0) > 60000) this.enviar();
  },
  avance() {
    const L = this.activa;
    const leido = L.bloques.filter((b) => L.leidos.has(b.i)).reduce((a, b) => a + b.palabras + b.formulas * 12, 0);
    return Math.min(1, leido / L.total);
  },
  enviar() {
    const L = this.activa; if (!L || L.seg < 20) return;
    L.enviado = Date.now();
    api("lectura/sesion", { id: L.id, tema: L.tema, area: L.area, metodo: L.metodo, idioma: L.idioma, inicio: L.inicio,
      segundos: Math.round(L.seg), avance: this.avance(), palabras: L.bloques.reduce((a, b) => a + b.palabras, 0),
      formulas: L.bloques.reduce((a, b) => a + b.formulas, 0), cats: L.cats,
      acciones: ACT.acciones - L.acciones0, audio: ACT.audio }).catch(() => {});
  },
  terminar() { if (this.activa) { this.enviar(); this.activa = null; } },
};

/* ---------- enrutado ---------- */
const VISTAS = {};
function ir(r) { location.hash = "#/" + r; }
$$("[data-ir]").forEach((b) => b.addEventListener("click", () => ir(b.dataset.ir)));
// En el celular la barra muestra solo lo más usado; «⋯» abre el resto con su nombre
$("#masAtajos").addEventListener("click", () => modal(`<h2>Más</h2><div class="fila" style="flex-direction:column;align-items:stretch">
  ${$$(".atajos .extra").map((b) => `<button class="btn" data-mas="${b.dataset.ir}" style="justify-content:flex-start">${b.textContent} ${esc(b.title.split(/[:(]/)[0])}</button>`).join("")}</div>`,
  (c) => $$("[data-mas]", c).forEach((b) => (b.onclick = () => { cerrarModal(); ir(b.dataset.mas); }))));
window.addEventListener("hashchange", () => enrutar());
// Refresco automático (algo terminó de prepararse): redibuja la vista SIN el ícono de carga y SIN subir al inicio,
// para que no parezca que la página entera se recargó (se notaba mucho en iPhone).
const refrescar = () => enrutar({ suave: true });

async function enrutar(op = {}) {
  const h = decodeURIComponent(location.hash.replace(/^#\/?/, "")) || "hoy";
  const [ruta, qs] = h.split("?");
  const partes = ruta.split("/");
  const q = Object.fromEntries(new URLSearchParams(qs || ""));
  $$("[data-ir]").forEach((b) => b.classList.toggle("activo", b.dataset.ir === partes[0]));
  E.estudiando = ["tema", "repasar", "cuaderno", "tutor", "noticias", "noticia", "chequeo", "tarea", "paper", "verificar"].includes(partes[0]);
  E.metodo = { tema: "leccion", repasar: "repaso", cuaderno: "cuaderno", tutor: "tutor", noticias: "noticias", noticia: "noticias", chequeo: "chequeo", tarea: "practica", paper: "investigacion", verificar: "investigacion" }[partes[0]] || null;
  enviarTiempo(); LECT.terminar();
  E.idiomaActual = null; E.areaActual = null; E.temaActual = null;
  vista.classList.toggle("ancho", ["cuaderno", "noticias", "noticia", "acciones", "accion"].includes(partes[0]));
  if (E.salir) { try { E.salir(); } catch (e) {} E.salir = null; }
  const fn = VISTAS[partes[0]] || VISTAS.hoy;
  const y = window.scrollY;
  if (!op.suave) { vista.innerHTML = `<p class="vacio"><span class="cargando"></span></p>`; window.scrollTo(0, 0); }
  else vista.style.minHeight = vista.offsetHeight + "px";   // que la página no se encoja mientras se redibuja
  try {
    await fn(partes.slice(1), q);
    if (op.suave) window.scrollTo(0, y);
  } catch (e) {
    vista.innerHTML = `<div class="tarjeta"><h2>Algo falló</h2><p>${esc(e.message)}</p><button class="btn" onclick="location.reload()">Recargar</button></div>`;
  } finally { vista.style.minHeight = ""; }
}

/* ---------- estado de la IA en la barra ---------- */
async function refrescarIA() {
  try {
    const s = await api("ia");
    E.permitirInterrumpir = s.permitir_interrumpir;
    const el = $("#estadoIA");
    if (s.actual) el.innerHTML = `<span class="cargando"></span> IA: ${esc(s.actual.fase || s.actual.tipo)}${s.en_cola ? ` (+${s.en_cola})` : ""}`;
    else if (s.ocupado_pc) el.textContent = "🎮 PC ocupado: la IA de fondo espera";
    else if (s.cargados.length) el.textContent = "IA cargada: " + s.cargados.join(", ");
    else el.textContent = "";
    const r = await api("repaso?n=0");
    const n = r.vencidas + r.nuevas; const g = $("#globoRepaso");
    g.hidden = !n; g.textContent = n > 99 ? "99+" : n;
  } catch (e) { /* servidor caído: se reintenta */ }
}
setInterval(refrescarIA, 15000);

/* =============================== COLA DE LA IA =============================== */
// Qué hace la IA para la Academia, qué viene después y cuánto consume. Se refresca cada 10 s.
// Las tareas de otras personas solo se ven como «otra persona» (sin tema): cada perfil es privado.
const hhmm = (t) => new Date(t * 1000).toLocaleTimeString(LOC, { hour: "2-digit", minute: "2-digit" });
// Recursos en la vista Cola: el PC completo (CPU, RAM, GPU) y cada modelo de IA cargado (el de la Academia y los
// de otras apps, p. ej. Hermes) con su CPU, RAM, VRAM y % de GPU.
const tamGB = (mb) => mb == null ? "—" : mb >= 1024 ? (mb / 1024).toFixed(1) + " GB" : mb + " MB";
const medidor = (titulo, valor, pctBarra, sub = "") => `<div class="tarjeta" style="margin:0"><div class="suave peq">${titulo}</div>
  <b style="font-size:1.3rem">${valor}</b>${pctBarra != null ? `<div class="barra-prog" style="margin:.3rem 0"><i style="width:${Math.max(0, Math.min(100, pctBarra))}%;${pctBarra >= 90 ? "background:var(--mal)" : pctBarra >= 70 ? "background:var(--medio)" : ""}"></i></div>` : ""}
  ${sub ? `<span class="peq">${sub}</span>` : ""}</div>`;
function recursosHtml(r, d, pct, uso) {
  const s = r.sistema, g = s?.gpu, mods = r.modelos || [];
  let h = "";
  if (s && (s.cpu != null || s.ram_total)) {
    h += `<h2>🖥️ PC completo</h2><div class="rejilla">
      ${medidor("CPU", s.cpu == null ? "…" : s.cpu + " %", s.cpu, `${d.nucleos} núcleos`)}
      ${s.ram_total ? medidor("RAM", `${s.ram_usada} / ${s.ram_total} GB`, s.ram_usada / s.ram_total * 100, s.swap_usada ? `swap ${s.swap_usada} GB` : "") : ""}
      ${g ? medidor("GPU", g.uso + " %", g.uso, `${g.temp} °C`) : ""}
      ${g ? medidor("Memoria de video (VRAM)", `${g.vram} / ${g.vram_total} GB`, g.vram / g.vram_total * 100) : ""}</div>`;
  }
  if (mods.length) {
    h += `<h2>🧠 Modelos de IA cargados</h2><div class="rejilla">${mods.map((m) => `<div class="tarjeta" style="margin:0">
      <div class="fila entre"><b>${esc(m.modelo)}</b><span class="etq ${m.nuestro ? "bien" : ""}">${m.nuestro ? "Academia" : "otra app"}</span></div>
      <div class="suave peq" style="margin-top:.3rem">CPU ${m.cpu == null ? "…" : pct(m.cpu) + " % del PC"}</div>
      <div class="barra-prog" style="margin:.2rem 0"><i style="width:${pct(m.cpu) || 0}%"></i></div>
      <span class="peq">RAM ${tamGB(m.ram_mb)} · VRAM ${tamGB(m.vram_mb)} · GPU ${m.gpu == null ? "—" : m.gpu + " %"}</span></div>`).join("")}</div>`;
  } else if (s) h += `<p class="suave peq">🧠 Ningún modelo cargado ahora (se cargan al necesitarlos y se descargan a los 5 min sin uso).</p>`;
  if (r.academia) h += `<div class="rejilla" style="margin-top:.6rem">${uso(r.academia, "🎓 Servidor de la Academia")}</div>`;
  if (h) h += `<p class="suave peq">% de CPU sobre el procesador completo (100 % = los ${d.nucleos} núcleos llenos).</p>`;
  return h;
}

VISTAS.cola = async () => {
  const pintar = async () => {
    const d = await api("cola");
    if (location.hash.replace(/^#\/?/, "").split("/")[0] !== "cola") return;
    const ia = d.ia, r = d.recursos || {};
    const estado = ia.actual ? ["bien", "▶ Trabajando"] : ia.ocupado_pc ? ["medio", "🎮 PC ocupado: lo de fondo espera"]
      : ia.otros?.length ? ["medio", `⏸ Otra app usa la IA (${ia.otros.join(", ")}): la cola espera sin interrumpirla`]
      : d.trabajos.length ? ["medio", "⏳ Esperando para empezar"] : ["", "💤 Libre"];
    const pct = (cpu) => cpu == null ? null : Math.min(100, Math.round(cpu / (d.nucleos || 1)));   // % de TODO el PC (máx. 100)
    const uso = (x, nombre) => x ? `<div class="tarjeta" style="margin:0"><div class="suave peq">${nombre}</div>
      <b style="font-size:1.3rem">${x.cpu == null ? "…" : pct(x.cpu) + " %"}</b> <span class="suave peq">del procesador</span>
      <div class="barra-prog" style="margin:.3rem 0"><i style="width:${pct(x.cpu) || 0}%"></i></div>
      <span class="peq">${x.ram_mb >= 1024 ? (x.ram_mb / 1024).toFixed(1) + " GB" : x.ram_mb + " MB"} de RAM</span></div>` : "";
    const fila = (t) => `<li style="cursor:default;${t.mio ? "border-left:3px solid var(--acento);padding-left:.5rem" : ""}">
      <span class="etq ${t.estado === "corriendo" ? "bien" : t.estado === "conflicto" ? "medio" : ""}">${t.estado === "corriendo" ? "▶ ahora" : t.estado === "conflicto" ? "⏸ espera" : "#" + t.pos}</span>
      <span style="flex:1;min-width:0"><b>${esc(t.tipo)}</b>${t.detalle ? ` · ${esc(t.detalle)}` : ""}${t.mio ? ` <span class="etq">tuya</span>` : ""}
      ${t.fase && t.estado === "corriendo" ? `<br><span class="suave peq">${esc(t.fase)}</span>` : ""}
      ${t.espera_hasta ? `<br><span class="suave peq">reintenta a las ${hhmm(t.espera_hasta)} (la IA estaba ocupada)</span>` : ""}</span>
      <span class="suave peq">${t.fondo ? "de fondo" : "te espera"}</span></li>`;
    const html = `<h1>⏳ Cola de la IA</h1>
      <p class="suave peq">Lo que la IA está haciendo para la Academia y lo que sigue: ${ia.paralelos > 1 ? `hasta ${ia.paralelos} tareas a la vez` : "una tarea a la vez"}; lo que pides tú va antes que lo de fondo.
        Si otra app (Hermes, Open WebUI…) usa la IA, todo espera sin interrumpirla. Se actualiza cada 10 s · última: ${hhmm(d.hora)}</p>
      <div class="tarjeta"><div class="fila entre"><b>🤖 ${esc(ia.modelo)}</b><span class="etq ${estado[0]}">${esc(estado[1])}</span></div>
        <div class="suave peq">${ia.modo === "remoto" ? "IA en otro PC del tailnet" : "IA en este PC"} · cargado ahora: ${esc(ia.cargados.join(", ") || "ninguno")}</div></div>
      ${recursosHtml(r, d, pct, uso)}
      <h2>📋 Ahora y en cola (${d.trabajos.length})</h2>
      ${d.trabajos.length ? `<ul class="temas">${d.trabajos.map(fila).join("")}</ul>` : `<p class="vacio">Nada en cola: la IA está libre.</p>`}
      ${d.fallidos?.length ? `<h2>❌ Fallaron (${d.fallidos.length})</h2>
        <p class="suave peq">Se guardan 24 h. Al reintentar vuelven a la cola y la IA las hace de nuevo desde el principio.
          ${d.fallidos.length > 1 ? `<button class="btn peq pri" onclick='reintentarTrabajos(${JSON.stringify(d.fallidos.map((t) => t.id))})'>🔄 Reintentar todas</button>` : ""}</p>
        <ul class="temas">${d.fallidos.map((t) => `<li style="cursor:default">
        <span class="etq mal">error</span><span style="flex:1;min-width:0"><b>${esc(t.tipo)}</b>${t.detalle ? ` · ${esc(t.detalle)}` : ""}
          <br><span class="suave peq">${esc((t.error || "").slice(0, 160))} · ${hhmm(t.terminado)}${t.reintentos ? ` · ${t.reintentos} reintento(s)` : ""}</span></span>
        <button class="btn peq" onclick='reintentarTrabajos(["${t.id}"])'>🔄 Reintentar</button></li>`).join("")}</ul>` : ""}
      ${d.recientes.length ? `<h2>✅ Lo tuyo terminado hace poco</h2><ul class="temas">${d.recientes.map((t) => `<li style="cursor:default">
        <span class="etq ${t.error ? "mal" : "bien"}">${t.error ? "error" : "listo"}</span><span style="flex:1"><b>${esc(t.tipo)}</b>${t.detalle ? ` · ${esc(t.detalle)}` : ""}</span>
        <span class="suave peq">${hhmm(t.terminado)}</span></li>`).join("")}</ul>` : ""}`;
    if (html !== E.colaHtml) { E.colaHtml = html; const y = window.scrollY; vista.innerHTML = html; window.scrollTo(0, y); }
  };
  E.colaHtml = null;
  await pintar();
  const id = setInterval(() => pintar().catch(() => {}), 10000);
  E.salir = () => clearInterval(id);
};

/* =============================== HOY =============================== */
VISTAS.hoy = async () => {
  const [yo, d] = await Promise.all([api("yo"), api("hoy")]);
  E.yo = yo; E.misAreas = yo.areas ? new Set(yo.areas) : null;
  const nombre = yo.perfil.nombre ? ", " + esc(yo.perfil.nombre) : "";
  const hora = new Date().getHours();
  const saludo = hora < 12 ? "Buenos días" : hora < 19 ? "Buenas tardes" : "Buenas noches";
  const pctMin = Math.min(100, Math.round((d.minutos_hoy / d.meta_minutos) * 100));
  vista.innerHTML = `
    ${!d.configurado ? `<div class="tarjeta" style="border-color:var(--acento)"><b>Primeros pasos:</b> 1) cuéntale a la IA quién eres y qué quieres lograr en tu perfil; 2) crea tu primera meta de aprendizaje en 🎯 Objetivos: la IA arma las áreas y los temas que necesitas. La IA usa todo esto para adaptar lo demás.
      <div class="fila" style="margin-top:.6rem"><button class="btn pri" onclick="ir('ajustes')">Mi perfil</button><button class="btn" onclick="ir('objetivos')">🎯 Crear una meta</button></div></div>` : ""}
    <div class="saludo"><div><h1>${saludo}${nombre} 👋</h1>
      <div class="suave peq">${new Date().toLocaleDateString(LOC, { weekday: "long", day: "numeric", month: "long" })}</div></div></div>
    ${d.siguiente ? `<div class="tarjeta" id="sigPaso" style="border-color:var(--acento);${d.siguiente.ir ? "cursor:pointer" : ""}"><div class="suave peq">👉 Tu siguiente paso</div>
      <h2 style="margin:.2rem 0">${esc(d.siguiente.titulo)}</h2><div class="suave peq">${esc(d.siguiente.por_que)}</div></div>` : ""}
    ${typeof sesionCortaHtml === "function" ? sesionCortaHtml(d) : ""}
    <div class="stats">
      <div class="stat"><b>🔥 ${d.racha}</b><span>días seguidos</span></div>
      <div class="stat"><b>${d.minutos_hoy}<small class="suave">/${d.meta_minutos}</small></b><span>minutos hoy</span>
        <div class="barra-prog" style="margin-top:.3rem"><i style="width:${pctMin}%"></i></div></div>
      <div class="stat"><b>${d.repaso.vencidas + d.repaso.nuevas}</b><span>tarjetas por repasar</span></div>
      <div class="stat"><b>${d.lecciones_hoy}</b><span>lecciones hoy</span></div>
    </div>
    ${d.pruebas_listas ? `<div class="tarjeta" style="border-color:var(--acento);cursor:pointer" onclick="ir('pruebas')"><b>📝 Tienes ${d.pruebas_listas} prueba(s) de nivel lista(s)</b><div class="suave peq">Se guardaron: retómalas donde ibas.</div></div>` : ""}
    ${d.chequeo ? `<div class="tarjeta" style="border-color:var(--acento);cursor:pointer" onclick="ir('chequeo/${d.chequeo.id}')"><b>🧪 Tu chequeo semanal está listo</b><div class="suave peq">10-15 min: descubre qué recuerdas y qué olvidaste de lo que estudiaste.</div></div>` : ""}
    ${d.repaso.vencidas + d.repaso.nuevas ? `<button class="btn pri" style="width:100%;margin-bottom:1rem" onclick="ir('repasar')">🔁 Repasar ahora: ${d.repaso.vencidas} pendientes + ${d.repaso.nuevas} nuevas</button>` : ""}
    ${!d.pulso_hecho && d.hay_tarjetas ? `<div class="tarjeta" id="pulsoCaja" style="border-color:var(--medio)"><div class="fila entre"><div><b>⚡ Pulso diario</b>
      <div class="suave peq">1-2 min · 5 tarjetas: lo de los últimos días (corto plazo) y lo más antiguo (largo plazo).</div></div>
      <button class="btn pri" id="pulsoBtn">Empezar</button></div><div id="pulsoZona"></div></div>` : ""}
    ${d.adaptacion.ajustes.length ? `<details class="tarjeta" ${d.adaptacion.ajustes.length ? "open" : ""}><summary><b>🧭 Hoy se adapta a ti</b> <span class="suave peq">(según tus datos)</span></summary>
      <ul class="consejos">${d.adaptacion.ajustes.map((a) => `<li>${esc(a)}</li>`).join("")}</ul></details>` : ""}
    <div class="fila entre"><h2>📚 Tu sesión de hoy</h2><span class="suave peq">${d.temas.filter((t) => t.hecho).length}/${d.temas.length} hechos</span></div>
    <p class="suave peq">Elegidas intercalando áreas según tu prioridad, lo que hace más tiempo no tocas, tus objetivos y tus datos (lo olvidado va primero). Se preparan solas a la hora de la actualización diaria.</p>
    ${d.temas.length && d.temas.every((t) => t.hecho) ? `<div class="tarjeta" style="border-color:var(--bien)">🎉 <b>Terminaste lo de hoy.</b> Si te sobra energía, agrega otra sesión; si no, descansa: dormir también consolida lo aprendido.</div>` : ""}
    <div id="temasHoy">${d.temas.map(tarjetaTema).join("") || `<p class="vacio">${(yo.areas || []).length ? "No hay temas abiertos con las prioridades actuales. Sube alguna área en Ajustes." : SIN_AREAS}</p>`}</div>
    <div class="fila" style="margin-bottom:.6rem">
      ${d.temas.some((t) => !t.lista && !t.preparando) ? `<button class="btn" id="prepTodo">⚡ Preparar ya todas las lecciones de hoy</button>` : ""}
      <button class="btn" id="extraSesion">➕ Otra sesión (+3 temas)</button>
      <button class="btn fantasma" id="extraDia">📅 Adelantar un día (+${d.adaptacion.base})</button></div>
    <div class="tarjeta" style="cursor:pointer" onclick="ir('horizonte')"><div class="fila entre"><b>🔭 Tu horizonte</b><span class="suave peq">ver →</span></div>
      <div class="suave peq">Cuánto te falta para cada nivel a tu ritmo real, y cuánto antes llegas si te enfocas.</div></div>
    ${d.objetivos.length ? `<h2>🎯 Objetivos</h2>${d.objetivos.map((o) => `
      <div class="tarjeta" style="cursor:pointer" onclick="ir('objetivos/${o.id}')"><div class="fila entre"><b>${esc(o.titulo)}</b><span>${Math.round(o.progreso * 100)}%</span></div>
      <div class="barra-prog" style="margin-top:.4rem"><i style="width:${o.progreso * 100}%"></i></div></div>`).join("")}` : ""}
    <h2>⏱️ Bloque de concentración</h2>
    <div class="tarjeta"><div class="reloj" id="reloj">25:00</div>
      <div class="fila" style="justify-content:center"><button class="btn" id="pomo25">Enfoque 25</button><button class="btn" id="pomo50">Profundo 50</button><button class="btn fantasma" id="pomoParar">Parar</button></div>
      <p class="suave peq" style="text-align:center;margin:.5rem 0 0">Teléfono boca abajo, una sola tarea. Al terminar: 5 min de descanso real (sin pantalla).</p></div>
    <div id="hoyAcciones"></div>
    ${d.noticias.length ? `<h2>🌍 Lo más importante hoy</h2>${d.noticias.map(tarjetaNoticia).join("")}
      <button class="btn fantasma" onclick="ir('noticias')">Ver todas las noticias →</button>` : ""}`;
  $$("[data-tema]", vista).forEach((c) => (c.onclick = () => ir("tema/" + c.dataset.tema)));
  if (typeof acHoy === "function") acHoy($("#hoyAcciones"));   // web/acciones.js (lo guardado, sin esperar a internet)
  pomodoro(d.adaptacion.bloque);
  if ($("#sigPaso") && d.siguiente.ir) $("#sigPaso").onclick = () => {
    if (d.siguiente.ir === "pulso") { const b = $("#pulsoBtn"); if (b) { b.scrollIntoView({ behavior: "smooth", block: "center" }); b.click(); } }
    else ir(d.siguiente.ir);
  };
  if ($("#prepTodo")) $("#prepTodo").onclick = async () => { const r = await api("hoy/preparar", {}); aviso(`⚡ ${r.encoladas} lecciones en preparación (cada una tarda ~6 min)`); enrutar(); };
  const extra = async (cantidad) => { const r = await api("hoy/extra", { cantidad }); aviso(r.agregados ? `➕ ${r.agregados} temas agregados; se están preparando` : "No hay más temas abiertos ahora"); enrutar(); };
  $("#extraSesion").onclick = () => extra(3);
  $("#extraDia").onclick = () => extra(d.adaptacion.base);
  if ($("#pulsoBtn")) $("#pulsoBtn").onclick = async () => {
    $("#pulsoBtn").remove();
    const p = await api("pulso?n=5");
    miniRepaso($("#pulsoZona"), p.tarjetas, "pulso", async (bien, total) => {
      await api("pulso", { bien, total, modo: "diario" });
      $("#pulsoZona").innerHTML = `<p><b>${bien}/${total}</b> recordadas. ${bien / total >= 0.8 ? "🎉 Memoria en forma." : "Lo fallado ya volvió a tu repaso y entra en el plan de recuperación."}</p>`;
    });
  };
};
/* mini repaso (pulso diario y «antes de seguir»): destapar y decir si lo recordabas */
function miniRepaso(zona, tarjetas, origen, alTerminar) {
  if (!tarjetas.length) { zona.innerHTML = `<p class="suave peq">No hay tarjetas para evaluar todavía.</p>`; return; }
  let i = 0, bien = 0;
  const pintar = () => {
    const t = tarjetas[i];
    if (!t) return alTerminar(bien, tarjetas.length);
    zona.innerHTML = `<div class="mini"><div class="suave peq">${i + 1}/${tarjetas.length} · ${esc(t.etiqueta || "")}${t.edad_dias >= 1 ? ` · aprendida hace ${Math.round(t.edad_dias)} d` : ""}</div>
      <div class="fr"></div><div class="rv" hidden></div><div class="fila" style="margin-top:.5rem"><button class="btn peq" id="miniVer">Mostrar respuesta</button></div></div>`;
    pintarMd($(".fr", zona), t.frente, t.idioma); const t0 = Date.now();
    $("#miniVer").onclick = () => {
      const rv = $(".rv", zona); rv.hidden = false; pintarMd(rv, t.reverso, t.idioma);
      $("#miniVer").parentNode.innerHTML = `<button class="btn peq" data-r="1">✗ No lo recordaba</button><button class="btn peq pri" data-r="3">✓ Lo recordaba</button>`;
      $$("[data-r]", zona).forEach((b) => (b.onclick = () => {
        const nota = +b.dataset.r; if (nota === 3) bien++;
        api("repaso", { id: t.id, nota, segundos: (Date.now() - t0) / 1000, origen: "pulso" }).catch(() => {});
        i++; pintar();
      }));
    };
  };
  pintar();
}
function tarjetaTema(t) {
  return `<div class="tarjeta tema-card" data-tema="${t.id}" style="${t.hecho ? "opacity:.6" : ""}">
    <div class="ico" style="background:${t.color || "#888"}">${esc(t.icono || "•")}</div>
    <div style="flex:1;min-width:0"><div class="suave peq">${esc(t.area)} › ${esc(t.modulo)}</div>
      <h3>${esc(t.t)}</h3><div class="suave peq">${esc(t.d)}</div>
      <div class="fila" style="margin-top:.35rem"><span class="etq">${esc(t.nivel_nombre)}</span>
      ${t.tipo === "recuperar" ? `<span class="etq mal" title="${esc(t.motivo || "")}">♻️ ${esc(t.motivo ? "reforzar: " + t.motivo : "recuperar (lo olvidaste)")}</span>` : t.tipo === "extra" ? `<span class="etq">➕ extra</span>` : ""}
      ${t.hecho ? `<span class="etq bien">✓ hecho hoy</span>` : t.lista ? `<span class="etq bien">lección lista</span>` : t.preparando ? `<span class="etq medio">preparándose…</span>` : `<span class="etq">se prepara al abrir</span>`}</div></div></div>`;
}
let pomoT = null;
function pomodoro(bloque) {
  const reloj = $("#reloj"); if (!reloj) return;
  if (bloque === 50) { $("#pomo50").classList.add("pri"); reloj.textContent = "50:00"; } else $("#pomo25").classList.add("pri");
  const fin = Number(localStorage.getItem("pomoFin") || 0);
  const pintar = () => {
    const f = Number(localStorage.getItem("pomoFin") || 0); const s = Math.max(0, Math.round((f - Date.now()) / 1000));
    if (!$("#reloj")) return clearInterval(pomoT);
    $("#reloj").textContent = `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
    if (f && s === 0) { localStorage.removeItem("pomoFin"); aviso("⏰ ¡Bloque terminado! Descansa 5 minutos.", 6000); try { navigator.vibrate && navigator.vibrate([300, 100, 300]); } catch (e) {} }
  };
  const iniciar = (m) => { try { localStorage.setItem("pomoFin", Date.now() + m * 60000); } catch (e) {} clearInterval(pomoT); pomoT = setInterval(pintar, 1000); pintar(); };
  $("#pomo25").onclick = () => iniciar(25); $("#pomo50").onclick = () => iniciar(50);
  $("#pomoParar").onclick = () => { localStorage.removeItem("pomoFin"); clearInterval(pomoT); reloj.textContent = "25:00"; };
  if (fin > Date.now()) { clearInterval(pomoT); pomoT = setInterval(pintar, 1000); pintar(); }
}

/* =============================== RUTA =============================== */
// Áreas de ESTE perfil (las calcula el servidor: Ajustes, áreas propias, metas y lo ya estudiado).
// No hay catálogo: las áreas aparecen a medida que crea metas o áreas en 🎯 Objetivos.
const esMia = (a, yo) => (yo.areas || []).includes(a.id);
const SIN_AREAS = `Aún no tienes áreas. Crea una meta de aprendizaje o un área completa en <a href="#/objetivos">🎯 Objetivos</a>: la IA arma lo que necesitas y aparecerá aquí.`;
const porGrupo = (as) => { const g = {}; as.forEach((a) => (g[a.grupo] = g[a.grupo] || []).push(a)); return g; };

VISTAS.ruta = async ([areaId]) => {
  const [d, yo] = await Promise.all([api("mapa"), api("yo")]);
  E.mapa = d.areas; d.areas.forEach((a) => (AREA_ES[a.id] = a));
  if (!areaId) {
    const mias = d.areas.filter((a) => esMia(a, yo));
    const tarjetas = (grupos) => Object.entries(grupos).map(([g, as]) => `<h2>${esc(g)}</h2><div class="rejilla">${as.map((a) => `
        <div class="tarjeta" style="cursor:pointer" onclick="ir('ruta/${a.id}')">
          <div class="area-cab"><div class="ico" style="background:${a.color}">${esc(a.icono)}</div>
          <div style="min-width:0"><b>${esc(a.nombre)}</b><div class="suave peq">${a.modulos.length} módulos · ${a.modulos.reduce((s, m) => s + m.temas.length, 0)} temas</div></div></div>
          <div class="barra-prog" style="margin-top:.7rem"><i style="width:${a.dominio * 100}%;background:${a.color}"></i></div>
          <div class="suave peq" style="margin-top:.2rem">${Math.round(a.dominio * 100)}% dominado</div></div>`).join("")}</div>`).join("");
    vista.innerHTML = `<h1>🗺️ Tu ruta</h1>
      <p class="suave">De lo más básico a la frontera del conocimiento (horizonte). Cada módulo se desbloquea al dominar sus prerrequisitos al 60 %; si ya sabes algo, haz la <b>prueba de nivel</b> y sáltalo.</p>
      <div class="fila" style="margin-bottom:.6rem"><button class="btn peq" onclick="ir('pruebas')">📝 Mis pruebas de nivel</button></div>
      <details class="tarjeta" id="extCaja"><summary><b>📥 Ya estudié cosas fuera de la Academia</b> <span class="suave peq">(Coursera, Platzi, DataCamp, universidad, trabajo…)</span></summary>
        <p class="suave peq">Pega la lista de cursos, certificados o materias que terminaste (con el nivel o la nota si la tienes). La IA los relaciona con tu ruta y te propone una prueba de nivel corta por módulo: lo que ya sabes no lo vuelves a estudiar, pero se verifica.</p>
        <textarea id="extTexto" placeholder="Ej.: Coursera — Machine Learning Specialization (Stanford), terminada&#10;Platzi — Curso de Python intermedio&#10;Universidad — Cálculo diferencial (4,2/5)"></textarea>
        <div class="fila" style="margin-top:.4rem"><button class="btn pri" id="extBtn">Relacionar con mi ruta</button></div><div id="extRes"></div></details>
      ${mias.length ? tarjetas(porGrupo(mias)) : `<div class="tarjeta">${SIN_AREAS}</div>`}`;
    montarExterno();
    return;
  }
  const a = d.areas.find((x) => x.id === areaId);
  if (!a) return ir("ruta");
  const porNivel = {};
  a.modulos.forEach((m) => (porNivel[m.nivel] = porNivel[m.nivel] || []).push(m));
  vista.innerHTML = `<button class="btn fantasma peq" onclick="ir('ruta')">← Todas las áreas</button>
    <div class="area-cab" style="margin:.6rem 0"><div class="ico" style="background:${a.color}">${esc(a.icono)}</div>
      <div><h1 style="margin:0">${esc(a.nombre)}</h1><div class="suave peq">${Math.round(a.dominio * 100)}% dominado</div></div></div>
    <p>${esc(a.descripcion || "")}</p>
    ${a.objetivo ? `<p class="peq">Ruta propia de tu objetivo · <a href="#/objetivos/${a.objetivo}">ver el objetivo y sus requisitos</a></p>` : ""}
    <div id="rutaViva"></div>
    ${a.modulos.some((m) => m.dominio < 0.8) ? `<div class="tarjeta"><div class="fila entre"><div><b>🎯 Ubícame en esta área</b><div class="suave peq">3-4 pruebas de nivel en búsqueda binaria: lo que ya sabes se salta, empiezas donde de verdad estás.</div></div><button class="btn pri peq" id="ubicarme">Empezar</button></div></div>` : ""}
    ${a.personal && a.id.startsWith("p_") ? `<div class="fila" style="margin-bottom:.6rem"><span class="etq">área creada por ti</span><button class="btn peq fantasma" id="quitarArea">🗑 Quitar esta área</button></div>` : ""}
    ${a.recursos.length ? `<details class="tarjeta"><summary><b>📚 Recursos verificados y gratuitos</b></summary><ul>${a.recursos.map((r) => `<li><a href="${escUrl(r.u)}" target="_blank" rel="noopener">${esc(r.t)}</a></li>`).join("")}</ul></details>` : ""}
    ${Object.entries(porNivel).map(([n, ms]) => `<div class="nivel-tit">Nivel ${n} · ${NIVELES[n]}</div>${ms.map((m) => `
      <details class="tarjeta modulo ${m.abierto ? "" : "cerrado"}" ${m.abierto && m.dominio < 0.8 && m.dominio > 0 ? "open" : ""}>
        <summary><div class="fila entre"><b>${m.abierto ? "" : "🔒 "}${esc(m.t)}</b><span class="suave peq">${Math.round(m.dominio * 100)}%</span></div>
          <div class="barra-prog" style="margin-top:.4rem"><i style="width:${m.dominio * 100}%;background:${a.color}"></i></div>
          ${m.pre.length ? `<div class="suave peq" style="margin-top:.3rem">Requiere: ${m.pre.map(nombreModulo).join(", ")}</div>` : ""}</summary>
        <ul class="temas">${m.temas.map((t) => `<li data-tema="${t.id}"><span class="punto ${t.estado}"></span><span style="flex:1">${esc(t.t)}<br><span class="suave peq">${esc(t.d)}</span></span>${t.memoria != null && t.memoria < 0.7 ? `<span class="etq medio" title="Memoria actual de sus tarjetas: ${Math.round(t.memoria * 100)} %">🧠 ${Math.round(t.memoria * 100)} %</span>` : ""}</li>`).join("")}</ul>
        <div class="fila" style="margin-top:.6rem">
          ${m.dominio < 1 ? `<button class="btn peq" data-prueba="${m.ref}">⚡ Prueba de nivel (saltar módulo)</button>` : `<span class="etq bien">✓ Completo</span>`}
          ${a.idioma ? "" : `<button class="btn peq fantasma" data-ciencia="${m.ref}" data-titulo="${esc(m.t)}">🔬 Investigación científica</button>`}</div>
        <div class="fila" style="margin-top:.4rem">
          <button class="btn peq" data-preparar-mod="${m.ref}">📥 Preparar todo el módulo</button>
          ${a.idioma ? "" : `<button class="btn peq" data-maxima-mod="${m.ref}">🔬 Todo a máxima profundidad</button>`}
          <span class="suave peq" data-estado-mod="${m.ref}"></span></div>
      </details>`).join("")}`).join("")}`;
  const pintarEstadoMods = async () => {
    const em = await api("modulo/estado?area=" + encodeURIComponent(a.id)).catch(() => null);
    if (!em || !em.modulos) return;
    Object.entries(em.modulos).forEach(([ref, x]) => {
      const el = $(`[data-estado-mod="${ref}"]`, vista); if (!el) return;
      el.textContent = `Lecciones: ${x.listas}/${x.temas} listas` + (x.maximas ? ` · ${x.maximas} a máxima profundidad` : "") + (x.en_cola ? ` · ⏳ ${x.en_cola} en cola` : "");
    });
  };
  pintarEstadoMods();
  $$("[data-preparar-mod]", vista).forEach((b) => (b.onclick = async (e) => {
    e.preventDefault();
    const r = await api("modulo/preparar", { ref: b.dataset.prepararMod });
    aviso(r.encoladas ? `📥 ${r.encoladas} lecciones en cola (de fondo; ~30 min cada una, 2 a la vez)` : "Todas las lecciones de este módulo ya están listas o en cola");
    pintarEstadoMods();
  }));
  $$("[data-maxima-mod]", vista).forEach((b) => (b.onclick = async (e) => {
    e.preventDefault();
    if (!confirm("¿Reescribir todas las lecciones de este módulo a máxima profundidad? Cada una tarda 1-1.5 h de fondo; las actuales quedan como versión anterior.")) return;
    const r = await api("modulo/preparar", { ref: b.dataset.maximaMod, maxima: true });
    aviso(r.encoladas ? `🔬 ${r.encoladas} lecciones en cola a máxima profundidad (mira el avance en ⏳)` : "Todas ya están a máxima profundidad o en cola");
    pintarEstadoMods();
  }));
  $$("[data-tema]", vista).forEach((li) => (li.onclick = () => ir("tema/" + li.dataset.tema)));
  $$("[data-prueba]", vista).forEach((b) => (b.onclick = (e) => { e.preventDefault(); pruebaNivel(b.dataset.prueba); }));
  $$("[data-ciencia]", vista).forEach((b) => (b.onclick = (e) => { e.preventDefault(); verCiencia(b.dataset.ciencia, b.dataset.titulo); }));
  if ($("#ubicarme")) $("#ubicarme").onclick = () => ubicarme(a);
  montarRutaViva($("#rutaViva"), a.objetivo ? { objetivo: a.objetivo } : { area: a.id });
  if ($("#quitarArea")) $("#quitarArea").onclick = async () => {
    if (!confirm("¿Quitar esta área de tu ruta? Tu avance en sus temas se conserva por si la vuelves a crear con el mismo nombre.")) return;
    await api("area/borrar", { id: a.id }); E.mapa = null; ir("ruta");
  };
};
function nombreModulo(ref) {
  const [a, m] = ref.split(".");
  const area = (E.mapa || []).find((x) => x.id === a);
  const mod = area && area.modulos.find((x) => x.ref === ref);
  return mod ? `${area.icono} ${mod.t}` : ref;
}

async function pruebaNivel(ref, alTerminar, titulo, nueva) {
  // La prueba vive en el servidor: se puede cerrar la ventana, cambiar de equipo y retomarla (📝 Mis pruebas).
  modal(`<h2>⚡ Prueba de nivel${titulo ? ` <span class="suave peq">· ${esc(titulo)}</span>` : ""}</h2><p class="suave peq">${esc(nombreModulo(ref))}</p><p id="pnEstado"><span class="cargando"></span> Buscando tu prueba…</p><div id="pnCuerpo" data-ref="${esc(ref)}"></div>`);
  try {
    const r0 = await api("prueba", { ref, nueva: !!nueva });
    if (r0.error) throw new Error(r0.error);
    let pid = r0.prueba;
    if (!pid) {
      $("#pnEstado").innerHTML = `<span class="cargando"></span> Preparando preguntas nuevas, 2 por cada tema que te falta (2-5 min). <b>Puedes cerrar esta ventana</b>: se prepara igual y la encuentras en 📝 Mis pruebas, en «Hoy» y en este módulo.`;
      const r = await esperarTrabajo(r0.trabajo, (t) => { const e = $("#pnEstado"); if (e) e.innerHTML = `<span class="cargando"></span> ${esc(textoEstado(t))} · <b>puedes cerrar</b>: queda guardada.`; });
      pid = r.id;
    }
    if (!$("#pnCuerpo") || $("#pnCuerpo").dataset.ref !== ref || $("#modal").hidden) return;   // la cerró: queda en 📝 Mis pruebas
    const x = await api("prueba?id=" + pid);
    if (x.estado === "terminada") return mostrarResultadoPrueba(x.resultado, alTerminar, ref);
    const r = x.datos, resp = {}; Object.entries(x.respuestas).forEach(([i, v]) => (resp[i] = v));
    const total = r.preguntas.length, minimo = Math.ceil(total * (r.aprobar || 0.95));
    const hechas = () => Object.keys(resp).length;
    $("#pnEstado").innerHTML = `${r.intento > 1 ? `<span class="etq">Intento ${r.intento} · preguntas nuevas</span> ` : ""}${r.ya_sabidos && r.ya_sabidos.length ? `<span class="etq bien">Ya superados, no se repiten: ${r.ya_sabidos.map(esc).join(", ")}</span><br>` : ""}Responde sin consultar nada. <b>${minimo} de ${total}</b> (${Math.round((r.aprobar || 0.95) * 100)} %) = módulo superado.
      Si no llegas, igual quedan marcados como sabidos los temas en los que aciertes <b>todas</b> sus preguntas. <span class="suave">Cada respuesta se guarda: puedes cerrar y seguir luego, aquí o en otro equipo.</span> <span id="pnCuenta" class="etq">0/${total}</span>`;
    const c = $("#pnCuerpo");
    let html = "", ultimo = null;
    r.preguntas.forEach((p, i) => {
      if (p.tema !== ultimo) { ultimo = p.tema; const t = (r.temas || []).find((y) => y.i === p.tema); html += `<div class="nivel-tit">${esc(t ? t.t : "Tema " + (p.tema + 1))}</div>`; }
      html += `<div class="pregunta" data-i="${i}"><div class="pq"></div>${p.opciones.map(() => `<button class="opcion"></button>`).join("")}<div class="exp suave peq"></div></div>`;
    });
    c.innerHTML = html + `<div class="fila" style="margin-top:1rem"><button class="btn pri" id="pnFin" disabled>Ver resultado</button><button class="btn fantasma" onclick="cerrarModal()">Seguir luego</button></div>`;
    const cuenta = () => { $("#pnCuenta").textContent = `${hechas()}/${total} · ${Object.values(resp).filter((v) => v.ok).length} bien`; $("#pnFin").disabled = hechas() < total; };
    const marcar = (caja, p, j) => { $$(".opcion", caja)[p.correcta].classList.add("ok"); if (j !== p.correcta) $$(".opcion", caja)[j]?.classList.add("no"); pintarMd($(".exp", caja), p.explicacion); };
    r.preguntas.forEach((p, i) => {
      const caja = $(`[data-i="${i}"]`, c);
      pintarMd($(".pq", caja), `**${i + 1}.** ${p.pregunta}`);
      $$(".opcion", caja).forEach((b, j) => { pintarMd(b, p.opciones[j]); b.onclick = async () => {
        if (resp[i] !== undefined) return;
        resp[i] = { j, ok: j === p.correcta, tema: p.tema }; marcar(caja, p, j); cuenta();
        api("prueba/respuesta", { id: pid, i, j }).catch(() => aviso("No se pudo guardar la respuesta; revisa la conexión"));
      }; });
      if (resp[i] !== undefined) marcar(caja, p, resp[i].j);
    });
    cuenta();
    $("#pnFin").onclick = async () => mostrarResultadoPrueba(await api("prueba/resultado", { id: pid, ref }), alTerminar, ref);
  } catch (e) { const z = $("#pnEstado"); if (z) z.textContent = "Error: " + e.message; }
}
function mostrarResultadoPrueba(res, alTerminar, ref) {
  modal(`<h2>${res.aprobado ? "🎉 ¡Módulo superado!" : "Resultado de la prueba"}</h2>
    <p><b>${res.bien}/${res.total}</b> correctas (${Math.round(res.porcentaje * 100)} %; se necesita ${Math.round(res.minimo * 100)} %).
    ${res.aprobado ? "Todo el módulo queda como dominado y se abren los siguientes." : ""}</p>
    ${res.pasados.length ? `<p>✅ <b>Marcados como sabidos (${res.pasados.length}):</b></p><ul class="temas">${res.pasados.map((t) => `<li style="cursor:default"><span class="punto probado"></span>${esc(t.t)}</li>`).join("")}</ul>` : ""}
    ${res.pendientes.length ? `<p>⬜ <b>Te faltan (${res.pendientes.length})</b> — quedan pendientes en tu ruta:</p><ul class="temas">${res.pendientes.map((t) => `<li data-tema="${t.id}"><span class="punto"></span><span style="flex:1">${esc(t.t)}</span><span class="etq">${t.bien}/${t.total}</span></li>`).join("")}</ul>` : ""}
    <div class="fila" style="margin-top:.8rem">${alTerminar ? `<button class="btn pri" id="pnSeguirUb">Continuar la ubicación →</button>` : `<button class="btn pri" onclick="cerrarModal();enrutar()">Seguir</button>`}
      ${!res.aprobado && !alTerminar ? `<button class="btn" id="pnOtra">🔄 Otra prueba con preguntas nuevas</button>` : ""}</div>`, (cx) => {
    if (alTerminar) $("#pnSeguirUb", cx).onclick = () => alTerminar(res);
    if ($("#pnOtra", cx)) $("#pnOtra", cx).onclick = () => pruebaNivel(ref, null, null, true);
    $$("[data-tema]", cx).forEach((li) => (li.onclick = () => { cerrarModal(); ir("tema/" + li.dataset.tema); }));
  });
}
VISTAS.pruebas = async () => {
  if (!E.mapa) { const m = await api("mapa"); E.mapa = m.areas; }
  const d = await api("pruebas");
  vista.innerHTML = `<h1>📝 Mis pruebas de nivel</h1><p class="suave">Las pruebas viven en el servidor: si cierras la ventana o cambias de equipo, las retomas aquí donde ibas.</p>
    ${d.preparando.map((x) => `<div class="tarjeta"><span class="cargando"></span> <b>${esc(x.modulo)}</b> · ${esc(textoEstado(x.trabajo))}</div>`).join("")}
    ${d.listas.length ? `<h2>Para responder</h2>${d.listas.map((x) => `<div class="tarjeta"><div class="fila entre"><div><b>${esc(x.modulo)}</b><div class="suave peq">${esc(x.area)} · ${x.respondidas}/${x.total} respondidas · ${new Date(x.creada * 1000).toLocaleDateString(LOC)}</div></div><button class="btn pri peq" data-seguir="${esc(x.ref)}">${x.respondidas ? "Continuar" : "Empezar"}</button></div></div>`).join("")}` : ""}
    ${d.terminadas.length ? `<h2>Terminadas</h2>${d.terminadas.map((x) => `<div class="tarjeta"><div class="fila entre"><div><b>${esc(x.modulo)}</b> ${x.aprobado ? `<span class="etq bien">superado</span>` : `<span class="etq">${Math.round((x.porcentaje || 0) * 100)} %</span>`}<div class="suave peq">${esc(x.area)} · ${x.pasados} temas sabidos · ${x.pendientes} pendientes · ${new Date(x.terminada * 1000).toLocaleDateString(LOC)}</div></div><button class="btn peq fantasma" data-ver="${x.id}">Ver resultado</button></div></div>`).join("")}` : ""}
    ${!d.preparando.length && !d.listas.length && !d.terminadas.length ? `<p class="vacio">Aún no has hecho pruebas de nivel. Están en cada módulo de 🗺️ Ruta (⚡) y en 🎯 Ubícame.</p>` : ""}`;
  $$("[data-seguir]").forEach((b) => (b.onclick = () => pruebaNivel(b.dataset.seguir)));
  $$("[data-ver]").forEach((b) => (b.onclick = async () => { const x = await api("prueba?id=" + b.dataset.ver); mostrarResultadoPrueba(x.resultado, null, x.ref); }));
  if (d.preparando.length) setTimeout(() => location.hash === "#/pruebas" && refrescar(), 15000);
};

/* =============================== TEMA / LECCIÓN =============================== */
VISTAS.tema = async ([tid]) => {
  const [d, yo] = await Promise.all([api("tema?id=" + encodeURIComponent(tid)), E.yo ? E.yo : api("yo")]);
  if (d.error) throw new Error(d.error);
  E.yo = yo; E.parteActual = null;
  E.areaActual = d.area.id; E.temaActual = tid; E.idiomaActual = d.area.idioma;
  const av = d.avance || {};
  vista.innerHTML = `<button class="btn fantasma peq" onclick="ir('ruta/${d.area.id}')">← ${esc(d.area.icono)} ${esc(d.area.nombre)}</button>
    <div class="suave peq" style="margin-top:.5rem">${esc(d.modulo.t)} · Nivel ${d.modulo.nivel} ${NIVELES[d.modulo.nivel] || ""} · tema ${d.tema.i + 1}/${d.modulo.temas.length}</div>
    <h1>${esc(d.tema.t)}</h1><p class="suave" style="margin-top:-.5rem">${esc(d.tema.d)}</p>
    <div class="fila" style="margin-bottom:.8rem">${av.estado ? `<span class="etq ${av.estado === "dominado" || av.estado === "probado" ? "bien" : "medio"}">${esc(av.estado)}</span>` : ""}
      ${av.quiz != null ? `<span class="etq">quiz ${Math.round(av.quiz * 100)}%</span>` : ""}${av.feynman != null ? `<span class="etq">Feynman ${Math.round(av.feynman * 100)}%</span>` : ""}
      ${d.tarjetas ? `<span class="etq">${d.tarjetas} tarjetas</span>` : ""}</div>
    <div id="cuerpoLeccion"></div>
    <button id="leerSel" class="btn pri" style="position:fixed;right:1rem;bottom:calc(var(--menu-alto) + 1rem);z-index:30" hidden>🔊 Leer selección</button>`;
  $("#leerSel").onclick = () => hablar(String(getSelection()), E.idiomaActual);
  if (d.leccion) return pintarLeccion(d);
  const c = $("#cuerpoLeccion");
  c.innerHTML = `<div class="tarjeta"><p id="genEstado"><span class="cargando"></span> Preparando la lección…</p>
    <p class="suave peq">La IA local busca fuentes web y documentos científicos, planea el tema en 4-6 partes y escribe cada una a fondo (teoría, derivaciones, ejemplos, casos límite), luego un caso integrador y la práctica. En total tarda 25-35 minutos, pero <b>puedes empezar a leer apenas termine la parte 1</b> (~8 min). Puedes salir: queda guardada.</p>
    <div class="escribiendo" id="genTexto"></div></div>`;
  try {
    const job = d.trabajo ? { trabajo: d.trabajo.id } : await api("leccion", { tema: tid });
    let mostrada = false;
    await esperarTrabajo(job.trabajo, (t) => {
      const e = $("#genEstado"); if (!e) return;
      if (!mostrada && /^(Buscando fuentes de la parte [2-9]|Escribiendo parte [2-9]|Escribiendo el cierre|Creando ejercicios)/.test(t.fase || "") && E.temaActual === tid) { mostrada = true; refrescar(); return; }
      e.innerHTML = `<span class="cargando"></span> ${esc(textoEstado(t))}`;
      if (t.texto) { const g = $("#genTexto"); g.textContent = t.texto; g.scrollTop = g.scrollHeight; }
    });
    if (E.temaActual === tid) refrescar();
  } catch (e) { const g = $("#genEstado"); if (g) g.innerHTML = `❌ ${esc(e.message)} <button class="btn peq" onclick="enrutar()">Reintentar</button>`; }
};

function pintarLeccion(d) {
  const c = $("#cuerpoLeccion");
  const L = d.leccion; const ej = L.ejercicios || { quiz: [], tarjetas: [] };
  const preparando = !L.ejercicios;
  const webs = L.fuentes.filter((f) => f.tipo !== "paper"), papers = L.fuentes.filter((f) => f.tipo === "paper");
  const objetivos = objetivosLeccion(L.contenido);
  const fecha = new Date(L.creado * 1000).toLocaleDateString(LOC);
  c.innerHTML = `${L.version < 2 && !d.area.idioma ? `<div class="tarjeta" style="border-color:var(--medio)"><b>📄 Esta es la versión corta de la lección.</b>
      <p class="suave peq" style="margin:.3rem 0">La versión a fondo divide el tema en 4-6 partes con teoría, derivaciones, ejemplos resueltos, casos límite, documentos científicos y un caso integrador. Tu avance y tus tarjetas se conservan.</p>
      <button class="btn pri peq" id="btnAFondo">🔬 Reescribirla a fondo</button></div>` : ""}
    ${!L.completa || d.trabajo ? `<div class="tarjeta" id="escribiendoBanner" style="border-color:var(--acento)"><span class="cargando"></span> <b>La IA sigue escribiendo esta lección.</b> <span class="suave peq" id="escribiendoFase">Las partes nuevas aparecen abajo solas mientras lees.</span></div>` : ""}
    <div id="diagCaja"></div><div id="barraLectura"></div>
    <article class="tarjeta leccion" id="textoLeccion"></article>
    <div class="suave peq">Lección escrita por la IA local el ${fecha}${webs.length ? ` con ${webs.length} fuentes web` : ""}${papers.length ? ` y ${papers.length} documentos científicos` : ""}. Contrasta con los recursos del área si algo no cuadra.</div>
    ${papers.length ? `<details class="tarjeta" style="margin-top:.6rem" open><summary><b>🔬 Documentos científicos usados (OpenAlex)</b></summary><ol>${papers.map((f) => `<li><b>[${esc(f.n || "")}]</b> ${esc(f.autores || "")} (${esc(f.anio || "")}). <a href="${escUrl(f.url)}" target="_blank" rel="noopener">${esc(f.titulo)}</a>. <i>${esc(f.revista || "")}</i> · ${f.citas} citas${f.abierto ? ` · <a href="${escUrl(f.abierto)}" target="_blank" rel="noopener">texto libre</a>` : ""}</li>`).join("")}</ol></details>` : ""}
    ${webs.length ? `<details class="tarjeta" style="margin-top:.6rem"><summary><b>🔎 Fuentes web consultadas</b></summary><ol>${webs.map((f) => `<li>${fiab(f)} <a href="${escUrl(f.url)}" target="_blank" rel="noopener">${esc(f.titulo || f.url)}</a></li>`).join("")}</ol></details>` : ""}
    <div id="verifLeccion"></div>
    <div class="tarjeta"><h2 style="margin-top:0">1️⃣ ¿Lo leíste con calma?</h2>
      <p class="suave peq">${preparando ? "La IA está creando las tarjetas y el quiz (1-3 min); mientras tanto, lee." : `Al marcarlo se agregan ${ej.tarjetas.length} tarjetas a tu repaso espaciado (FSRS): te las pregunta justo antes de que las olvides.`}</p>
      <button class="btn pri" id="btnVisto" ${preparando ? "disabled" : ""}>✅ Estudiado: agregar tarjetas</button></div>
    <div class="tarjeta"><h2 style="margin-top:0">2️⃣ Ponte a prueba</h2><p class="suave peq">Recuperar de memoria es lo que fija el aprendizaje (más que releer). 80 % o más = tema dominado.</p><div id="quiz"></div></div>
    <div class="tarjeta" id="practica"><h2 style="margin-top:0">3️⃣ Práctica: entrega tus ejercicios</h2>
      <p class="suave peq">Los enunciados están arriba, en la sección <b>«🏋️ Practica tú»</b> de la lección. Resuélvelos <b>sin abrir la solución</b> y entrégalos aquí: escrito, con una foto de tu cuaderno de papel, o a mano con el S Pen. La IA corrige paso a paso. Puedes entregar cada ejercicio las veces que quieras: cada entrega queda guardada como una versión nueva.</p>
      <div id="practicaCuerpo"><span class="cargando"></span></div></div>
    <div class="tarjeta"><h2 style="margin-top:0">4️⃣ Técnica Feynman: explícalo como profesor</h2>
      <p class="peq" style="margin-top:0">Cierra la lección y explica <b>el tema completo</b> («${esc(d.tema.t)}») con tus palabras, como si se lo enseñaras a alguien de 12 años que no sabe nada. No copies: si te trabas en una parte, ese es el hueco que hay que repasar.</p>
      <div class="guia-feynman"><b>Tu explicación debe responder:</b><ol class="peq">
        <li><b>¿Qué es?</b> En una sola frase sencilla.</li><li><b>¿Por qué funciona / de dónde sale?</b> La idea de fondo, no solo la fórmula.</li>
        <li><b>Un ejemplo tuyo</b> (distinto a los de la lección).</li><li><b>Una analogía</b> con algo cotidiano.</li>
        <li><b>¿Dónde se usa?</b> En ingeniería, negocios o la vida diaria, y <b>un error común</b> que hay que evitar.</li></ol>
        ${objetivos.length ? `<b class="peq">Y cubrir los objetivos de esta lección:</b><ul class="peq">${objetivos.map((o) => `<li>${esc(o)}</li>`).join("")}</ul>` : ""}</div>
      <div class="fila" style="margin:.4rem 0"><button class="btn peq" id="plantillaF">📝 Usar plantilla con estas preguntas</button></div>
      <textarea id="feynman" style="min-height:220px" placeholder="Explícalo aquí con tus palabras…"></textarea>
      <div class="fila" style="margin-top:.5rem"><button class="btn pri" id="btnFeynman">Corregir mi explicación</button>
      <button class="btn" onclick="ir('cuaderno/nueva?tema=${d.tema.id}')">✍️ Explicarlo a mano (S Pen)</button></div><div id="feynmanRes"></div></div>
    ${!d.area.idioma && L.completa ? (L.version >= 3
      ? `<div class="tarjeta"><span class="etq bien">🔬 Máxima profundidad</span> <span class="suave peq">Esta lección ya está en su versión más profunda.</span></div>`
      : `<div class="tarjeta"><b>🔬 ¿Quieres más profundidad?</b><p class="suave peq">La IA la reescribe en 6-8 partes, con más fuentes y documentos científicos, la demostración o derivación completa de cada resultado, de dónde viene cada idea y 8 ejercicios. Tarda 1-1.5 h (de fondo); la actual queda como versión anterior.</p>
        <button class="btn peq" id="btnMaxima">🔬 Cargar a máxima profundidad</button></div>`) : ""}
    <div class="fila" style="margin:1rem 0">
      ${d.anterior ? `<button class="btn" onclick="ir('tema/${d.anterior}')">← Anterior</button>` : ""}
      <button class="btn" onclick="ir('tutor?hilo=${encodeURIComponent(d.tema.id)}&tema=${d.tema.id}')">💬 Preguntar al tutor</button>
      ${d.siguiente ? `<button class="btn pri" onclick="ir('tema/${d.siguiente}')">Siguiente →</button>` : ""}</div>
    <details class="tarjeta"><summary class="suave">Más opciones</summary><div class="fila" style="margin-top:.6rem">
      <button class="btn peq" id="btnDomino">Ya lo domino (marcar)</button>
      <button class="btn peq" id="btnRegenerar">🔄 Reescribir la lección (con fuentes nuevas)</button>
      ${L.anteriores ? `<button class="btn peq fantasma" id="btnAnterior">📜 Ver la versión anterior</button>` : ""}</div></details>`;
  E.lecActual = d;
  repintarLeccion(d, L.contenido);
  LECT.iniciar($("#textoLeccion"), { tema: d.tema.id, area: d.area.id, metodo: "leccion", idioma: d.area.idioma || "es" });
  if (!preparando) ofrecerDiagnostico(d, ej.quiz || []);
  if (L.completa && !d.area.idioma) { montarVerificacionLeccion(d); montarAportadas(d); }
  $("#btnVisto").onclick = async () => {
    const r = await api("visto", { tema: d.tema.id });
    aviso(`✅ Guardado. ${r.tarjetas} tarjetas nuevas en tu repaso.`); $("#btnVisto").disabled = true; refrescarIA();
    const p = await api(`pulso?n=2&modo=sesion&tema=${encodeURIComponent(d.tema.id)}`);
    if (p.tarjetas.length) {
      const z = document.createElement("div"); z.className = "tarjeta"; z.style.borderColor = "var(--medio)";
      z.innerHTML = `<b>⚡ Antes de seguir: 2 preguntas de otros temas</b><p class="suave peq">Intercalar lo viejo con lo nuevo fija mejor ambos (y mide tu memoria a corto plazo).</p><div class="zona"></div>`;
      $("#btnVisto").closest(".tarjeta").after(z);
      miniRepaso($(".zona", z), p.tarjetas, "pulso", (bien, total) => {
        api("pulso", { bien, total, modo: "sesion" }); $(".zona", z).innerHTML = `<p>${bien}/${total} recordadas. Sigue con el quiz 👇</p>`; });
    }
  };
  $("#btnDomino").onclick = async () => { await api("dominado", { tema: d.tema.id }); aviso("Marcado como dominado"); enrutar(); };
  const reescribir = async (preguntar) => {
    if (preguntar && !confirm("¿Reescribir la lección a fondo? La actual se guarda como versión anterior.")) return;
    await api("leccion", { tema: d.tema.id, forzar: true });
    enrutar();
  };
  $("#btnRegenerar").onclick = () => reescribir(true);
  if ($("#btnMaxima")) $("#btnMaxima").onclick = async () => {
    await api("leccion", { tema: d.tema.id, maxima: true });
    aviso("🔬 En cola a máxima profundidad. Puedes seguir leyendo esta; mira el avance en ⏳"); refrescar();
  };
  if ($("#btnAFondo")) $("#btnAFondo").onclick = () => reescribir(false);
  if ($("#btnAnterior")) $("#btnAnterior").onclick = async () => {
    const r = await api("leccion/anterior?tema=" + encodeURIComponent(d.tema.id));
    modal(`<h2>📜 Versión anterior</h2><p class="suave peq">Escrita el ${new Date(r.creado * 1000).toLocaleDateString(LOC)}</p><div class="leccion" id="lecAnt"></div>`, () => pintarMd($("#lecAnt"), r.contenido, d.area.idioma));
  };
  if (!L.completa || d.trabajo) {   // sigue escribiendo: se agregan las partes nuevas sin mover lo que estás leyendo
    let largo = L.contenido.length;
    const revisar = async () => {
      if (E.temaActual !== d.tema.id || !$("#textoLeccion")) return;
      const n = await api("tema?id=" + encodeURIComponent(d.tema.id));
      if (!n.leccion) return;
      if (n.leccion.completa && !n.trabajo) return refrescar();
      if (n.leccion.contenido.length !== largo) { largo = n.leccion.contenido.length; repintarLeccion(d, n.leccion.contenido); }
      if (n.trabajo && $("#escribiendoFase")) $("#escribiendoFase").textContent = textoEstado(n.trabajo);
      setTimeout(revisar, 15000);
    };
    setTimeout(revisar, 15000);
  }
  if (preparando) {
    $("#quiz").innerHTML = `<p id="quizEspera"><span class="cargando"></span> Preparando quiz y tarjetas…</p>`;
    const jobQ = d.trabajo ? Promise.resolve({ trabajo: d.trabajo.id }) : api("leccion", { tema: d.tema.id });
    jobQ.then((j) => esperarTrabajo(j.trabajo, (t) => { const q = $("#quizEspera"); if (q) q.innerHTML = `<span class="cargando"></span> ${esc(textoEstado(t))}`; }))
      .then(() => { if (E.temaActual === d.tema.id) refrescar(); }).catch((e) => { const q = $("#quizEspera"); if (q) q.textContent = "Error: " + e.message; });
  } else pintarQuiz(d, ej.quiz || []);
  $("#btnFeynman").onclick = async () => {
    const txt = $("#feynman").value.trim(); if (txt.length < 40) return aviso("Escribe un poco más (al menos un párrafo)");
    const out = $("#feynmanRes"); out.innerHTML = `<p><span class="cargando"></span> Corrigiendo…</p>`;
    try {
      const j = await api("corregir", { tema: d.tema.id, pregunta: "Explica el tema «" + d.tema.t + "»" + (objetivos.length ? ". Objetivos a cubrir: " + objetivos.join("; ") : ""), respuesta: txt, modo: "feynman" });
      const r = await esperarTrabajo(j.trabajo, (t) => (out.innerHTML = `<p><span class="cargando"></span> ${esc(textoEstado(t))}</p>`));
      out.innerHTML = notaIA(r);
      await api("resultado", { tema: d.tema.id, feynman: r.puntaje / 100 });
    } catch (e) { out.textContent = "Error: " + e.message; }
  };
  $("#plantillaF").onclick = () => {
    const f = $("#feynman"); if (f.value.trim() && !confirm("¿Reemplazar lo que escribiste por la plantilla?")) return;
    f.value = "1. ¿Qué es? (una frase)\n\n\n2. ¿Por qué funciona / de dónde sale?\n\n\n3. Mi propio ejemplo:\n\n\n4. Una analogía:\n\n\n5. ¿Dónde se usa? Un error común:\n\n";
    f.focus(); f.setSelectionRange(26, 26);
  };
  montarPractica(d);
  if (location.hash.includes("#practica") || E.irPractica) { E.irPractica = false; setTimeout(() => $("#practica").scrollIntoView({ behavior: "smooth" }), 300); }
}
function objetivosLeccion(md_) {
  const m = /^##[^\n]*Objetivo[^\n]*\n([\s\S]*?)(?=^## |$(?![\s\S]))/m.exec(md_ || "");
  if (!m) return [];
  return [...m[1].matchAll(/^\s*(?:\d+[.)]|[-*])\s+(.+)$/gm)].map((x) => x[1].replace(/\*\*|__|`/g, "").replace(/\$([^$]+)\$/g, "$1").trim()).slice(0, 6);
}

/* ---------- lectura adaptativa (2026-10-27) ----------
   Las lecciones a fondo son largas (10-15 mil palabras) y casi nadie las termina. Aquí cada persona lee a su medida:
   📗 Esencial pliega lo opcional («más a fondo», matices, investigación, horizonte); 👣 Paso a paso muestra una parte a
   la vez; al final de cada parte, «¿lo entendiste?» guarda la señal y, si no, la IA la explica de otra forma. */
const CAPA_OPCIONAL = /m[aá]s a fondo|matices|casos l[ií]mite|errores t[ií]picos/i;
const CIERRE_OPCIONAL = /investigaci[oó]n|horizonte|conexiones|para seguir|lecturas/i;
const EST_PARTE = { sabido: ["✅", "Lo entendí", "bien"], dudoso: ["🤔", "Más o menos", "medio"], no: ["❌", "No lo entendí", "mal"] };
const ESTILOS_REEX = { simple: "🪶 Más simple", ejemplo: "🔧 Con un ejemplo", esquema: "🗺️ En un esquema" };
const minLeer = (el) => Math.max(1, Math.round(contarPalabras(el.textContent || "") / ((E.yo && E.yo.wpm) || 180)));
function pasoAPaso(d) {
  if (E.pasoLect != null) return E.pasoLect;
  const p = (E.yo && E.yo.perfil) || {};
  if (p.paso_a_paso != null) return !!p.paso_a_paso;
  return !!(d && d.formato && d.formato.recomendado === "esencial");   // no termina las lecciones: una parte a la vez
}
function modoLectura(d) {
  if (E.modoLect) return E.modoLect;
  const m = (E.yo && E.yo.perfil.modo_lectura) || "auto";
  // Automático: la lección COMPLETA (la meta es dominar, no resumir); a quien no termina se le parte en pasos
  return m === "auto" ? "completo" : m;
}
function repintarLeccion(d, contenido) {
  pintarMd($("#textoLeccion"), contenido, d.area.idioma);
  if (!d.area.idioma) adaptarLectura(d);
  // botón «entregar» al final de la sección de ejercicios de la lección
  const hPract = $$("#textoLeccion h2").find((h) => /🏋|pr[aá]ctica t[uú]/i.test(h.textContent)) || $$("#textoLeccion h2").find((h) => /pr[aá]ctica/i.test(h.textContent));
  if (hPract) {
    let fin = hPract.nextElementSibling;
    while (fin && fin.nextElementSibling && fin.nextElementSibling.tagName !== "H2") fin = fin.nextElementSibling;
    const b = document.createElement("button"); b.className = "btn pri"; b.style.margin = ".6rem 0";
    b.textContent = "📤 Entregar mis soluciones (escrito, foto o a mano)";
    b.onclick = () => $("#practica").scrollIntoView({ behavior: "smooth" });
    (fin || hPract).after(b);
  }
}
function plegar(titulo, nodos, abierto) {
  const det = document.createElement("details"); det.className = "capa"; if (abierto) det.open = true;
  const tmp = document.createElement("div"); nodos.forEach((n) => tmp.append(n));
  det.innerHTML = `<summary>${esc(titulo)} <span class="suave peq">· opcional · ~${minLeer(tmp)} min</span></summary>`;
  nodos.forEach((n) => det.append(n));
  return det;
}
function adaptarLectura(d) {
  const art = $("#textoLeccion"); if (!art) return;
  const modo = modoLectura(d), esencial = modo === "esencial" || modo === "rapida";
  pintarRapida(d, modo === "rapida");
  const paso = pasoAPaso(d);
  const P = d.partes || { estados: {}, reexplicaciones: [] };
  const flojas = new Set(((P.diagnostico && P.diagnostico.flojas) || []).map(Number));
  // 1) secciones por título de nivel 2
  const kids = [...art.childNodes]; art.innerHTML = "";
  let sec = null; let hayParte = false;
  kids.forEach((el) => {
    if (!sec || el.tagName === "H2") {
      sec = document.createElement("section"); sec.className = "sec-lec";
      const m = el.tagName === "H2" && /^\s*Parte\s+(\d+)/i.exec(el.textContent);
      if (m) { sec.dataset.parte = m[1]; hayParte = true; } else sec.dataset.tipo = hayParte ? "cierre" : "intro";
      art.append(sec);
    }
    sec.append(el);
  });
  const partes = $$("section[data-parte]", art);
  // 2) en modo esencial se pliega lo opcional de cada parte y del cierre
  $$("section", art).forEach((s) => {
    const h2 = $("h2", s);
    if (esencial && s.dataset.tipo === "cierre" && h2 && CIERRE_OPCIONAL.test(h2.textContent)) {
      const resto = [...s.childNodes].filter((n) => n !== h2); s.append(plegar(h2.textContent, resto)); return;
    }
    if (!s.dataset.parte) return;
    const hijos = [...s.children]; let i = 0;
    while (i < hijos.length) {
      const h = hijos[i];
      if (h.tagName === "H3" && esencial && CAPA_OPCIONAL.test(h.textContent)) {
        const bloque = []; let j = i + 1;
        while (j < hijos.length && !/^H[23]$/.test(hijos[j].tagName)) bloque.push(hijos[j++]);
        h.replaceWith(plegar(h.textContent, bloque)); i = j;
      } else if (h.tagName === "H3" && esencial && /ejemplos? resuelto/i.test(h.textContent)) {
        // el primer ejemplo resuelto se queda (efecto del ejemplo resuelto); los demás, plegados
        const bloque = []; let j = i + 1;
        while (j < hijos.length && !/^H[23]$/.test(hijos[j].tagName)) bloque.push(hijos[j++]);
        const h4 = bloque.filter((x) => x.tagName === "H4");
        if (h4.length > 1) { const desde = bloque.indexOf(h4[1]); const extra = bloque.slice(desde); const ancla = bloque[desde - 1]; const det = plegar(`Más ejemplos resueltos (${h4.length - 1})`, extra); ancla.after(det); }
        i = j;
      } else i++;
    }
    if (flojas.has(+s.dataset.parte) && h2) h2.insertAdjacentHTML("beforeend", ` <span class="etq medio">📌 enfócate aquí</span>`);
    // 3) «¿lo entendiste?» al final de cada parte
    const n = +s.dataset.parte, est = P.estados[n];
    const caja = document.createElement("div"); caja.className = "control-parte"; caja.dataset.p = n;
    caja.innerHTML = `<div class="fila entre"><b class="peq">¿Cómo te fue con la parte ${n}?</b>${est ? `<span class="etq ${EST_PARTE[est][2]}">${EST_PARTE[est][0]} ${EST_PARTE[est][1]}</span>` : ""}</div>
      <div class="fila" style="margin-top:.4rem">${Object.entries(EST_PARTE).map(([k, [ic, tx]]) => `<button class="btn peq ${est === k ? "pri" : ""}" data-est="${k}">${ic} ${tx}</button>`).join("")}</div>
      <div class="ayuda-parte" ${est && est !== "sabido" ? "" : "hidden"}>${opcionesReex(d, n)}</div>
      <div class="reex">${P.reexplicaciones.filter((r) => r.parte === n).map(htmlReex).join("")}</div>`;
    s.append(caja);
  });
  $$(".reex .rx-cuerpo", art).forEach((el) => pintarMd(el, el.dataset.md));
  $$(".control-parte", art).forEach((c) => montarControlParte(d, c));
  // 4) barra: modo, paso a paso, avance por partes y tiempo estimado
  const total = minLeer(art), visibles = Math.max(1, total - $$("details.capa", art).reduce((s, x) => s + minLeer(x), 0));
  const barra = $("#barraLectura");
  if (barra) {
    barra.innerHTML = partes.length ? `<div class="tarjeta barra-lectura"><div class="fila entre">
        <div class="chips"><button class="chip ${modo === "rapida" ? "activo" : ""}" data-modo-lect="rapida">🗺️ Vista previa</button><button class="chip ${modo === "esencial" ? "activo" : ""}" data-modo-lect="esencial">📗 Esencial</button><button class="chip ${esencial ? "" : "activo"}" data-modo-lect="completo">📚 Completo</button>
          ${modo === "rapida" ? "" : `<button class="chip ${paso ? "activo" : ""}" id="pasoLect">👣 Paso a paso</button>`}</div>
        <span class="suave peq">≈ ${modo === "rapida" ? `${d.partes && d.partes.rapida ? Math.max(3, Math.round(contarPalabras(d.partes.rapida) / ((E.yo && E.yo.wpm) || 180))) : "10-15"} min (completa ${total})` : esencial ? `${visibles} min (completo ${total})` : `${total} min`} a tu ritmo</span></div>
      ${d.formato && d.formato.razon && !(E.yo.perfil.modo_lectura && E.yo.perfil.modo_lectura !== "auto") ? `<div class="suave peq" style="margin-top:.3rem">🧭 ${esc(d.formato.razon)}</div>` : ""}
      <div class="chips" style="margin-top:.4rem" ${modo === "rapida" ? "hidden" : ""}>${partes.map((s) => { const n = +s.dataset.parte, e = P.estados[n];
        return `<button class="chip" data-ir-parte="${n}">${e ? EST_PARTE[e][0] : flojas.has(n) ? "📌" : "○"} Parte ${n}</button>`; }).join("")}</div></div>` : "";
    $$("[data-modo-lect]", barra).forEach((b) => (b.onclick = () => { E.modoLect = b.dataset.modoLect; repintarLeccion(d, d.leccion.contenido); }));
    if ($("#pasoLect", barra)) $("#pasoLect", barra).onclick = () => { E.pasoLect = !paso; repintarLeccion(d, d.leccion.contenido); };
    $$("[data-ir-parte]", barra).forEach((b) => (b.onclick = () => { E.parteActual = +b.dataset.irParte; aplicarPaso(d); const s = $(`section[data-parte="${b.dataset.irParte}"]`); if (s) s.scrollIntoView({ behavior: "smooth" }); }));
  }
  aplicarPaso(d);
}
function pintarRapida(d, activa) {
  const art = $("#textoLeccion");
  let caja = $("#rapidaCaja");
  if (!caja) { caja = document.createElement("article"); caja.id = "rapidaCaja"; caja.className = "tarjeta leccion"; art.before(caja); }
  caja.hidden = !activa; art.hidden = activa;
  if (!activa) return;
  const txt = d.partes && d.partes.rapida;
  if (txt) {
    caja.innerHTML = `<div class="suave peq" style="margin-bottom:.5rem">🗺️ <b>Vista previa</b>: el mapa de la lección en 10 min (lo esencial de cada parte). Leerla antes ayuda a ubicar cada detalle después; para dominar el tema, sigue con <a href="javascript:void 0" data-a-completa>la lección completa paso a paso</a>. También sirve para repasar.</div><div id="rapidaTexto"></div>
      <div class="fila" style="margin-top:.6rem"><button class="btn pri" data-a-completa>📚 Ahora la lección completa, paso a paso</button><button class="btn" id="rapidaQuiz">Ya la domino: ir al quiz</button></div>`;
    pintarMd($("#rapidaTexto"), txt);
    $("#rapidaQuiz").onclick = () => { const b = $("#btnVisto"); if (b && !b.disabled) b.click(); $("#quiz").scrollIntoView({ behavior: "smooth" }); };
  } else {
    caja.innerHTML = `<b>🗺️ Vista previa (10-15 min)</b><p class="suave peq">La IA condensa esta lección en lo esencial de cada parte, con un ejemplo mínimo y 3 preguntas: el mapa antes de estudiarla a fondo, y el repaso después. Tarda 1-2 min.</p>
      <div class="fila"><button class="btn pri" id="rapidaGen">🗺️ Preparar la vista previa</button><button class="btn" data-a-completa>📚 Ir a la lección completa</button></div><div id="rapidaEstado" class="suave peq"></div>`;
    $("#rapidaGen").onclick = async () => {
      $("#rapidaGen").disabled = true; const est = $("#rapidaEstado"); est.innerHTML = `<span class="cargando"></span> En cola…`;
      try {
        const j = await api("rapida", { tema: d.tema.id });
        const r = j.listo ? j : await esperarTrabajo(j.trabajo, (t) => (est.innerHTML = `<span class="cargando"></span> ${esc(textoEstado(t))}`));
        d.partes.rapida = r.texto; repintarLeccion(d, d.leccion.contenido);
      } catch (e) { est.textContent = "Error: " + e.message; $("#rapidaGen").disabled = false; }
    };
  }
  $$("[data-a-completa]", caja).forEach((b) => (b.onclick = () => { E.modoLect = "completo"; E.pasoLect = true; repintarLeccion(d, d.leccion.contenido); $("#barraLectura").scrollIntoView({ behavior: "smooth" }); }));
}
function aplicarPaso(d) {
  const art = $("#textoLeccion"); if (!art) return;
  const paso = pasoAPaso(d);
  const partes = $$("section[data-parte]", art); const est = (d.partes || {}).estados || {};
  if (!paso || !partes.length) { $$("section", art).forEach((s) => (s.hidden = false)); return; }
  const primeraSin = partes.find((s) => !est[+s.dataset.parte]);
  const actual = E.parteActual || (primeraSin ? +primeraSin.dataset.parte : null);
  partes.forEach((s) => (s.hidden = actual != null && +s.dataset.parte !== actual));
  $$("section[data-tipo=cierre]", art).forEach((s) => (s.hidden = !!primeraSin && actual != null));
}
function opcionesReex(d, n) {
  return `<p class="peq" style="margin:.5rem 0 .3rem">Te la explico de otra forma (la IA, ~1-3 min). Si quieres, di qué no entendiste:</p>
    <input type="text" class="duda-parte" placeholder="(Opcional) ¿Qué parte o qué palabra te trabó?">
    <div class="fila" style="margin-top:.4rem">${Object.entries(ESTILOS_REEX).map(([k, t]) => `<button class="btn peq" data-reex="${k}">${t}</button>`).join("")}
      <button class="btn peq fantasma" onclick="ir('tutor?hilo=${encodeURIComponent(d.tema.id)}&tema=${d.tema.id}')">💬 Tutor</button></div><div class="reex-estado suave peq"></div>`;
}
function htmlReex(r) {
  return `<details class="tarjeta reex-caja" open><summary><b>${esc(ESTILOS_REEX[r.estilo] || r.estilo)}</b> <span class="suave peq">${new Date(r.fecha * 1000).toLocaleDateString(LOC)}${r.duda ? " · tu duda: " + esc(r.duda) : ""}</span></summary>
    <div class="leccion rx-cuerpo" data-md="${esc(r.texto)}"></div></details>`;
}
function montarControlParte(d, caja) {
  const n = +caja.dataset.p; const t0 = Date.now();
  $$("[data-est]", caja).forEach((b) => (b.onclick = async () => {
    const estado = b.dataset.est;
    await api("parte", { tema: d.tema.id, parte: n, estado, segundos: (Date.now() - t0) / 1000 });
    d.partes = d.partes || { estados: {}, reexplicaciones: [] }; d.partes.estados[n] = estado;
    if (estado === "sabido") {
      const paso = pasoAPaso(d);
      E.parteActual = null; repintarLeccion(d, d.leccion.contenido);
      const sig = $(`section[data-parte="${n + 1}"]`) || $("section[data-tipo=cierre]");
      if (paso && sig) sig.scrollIntoView({ behavior: "smooth" });
      aviso(sig && sig.dataset.parte ? `✅ Parte ${n} lista. Sigue la ${n + 1}.` : "✅ Leíste todas las partes: ahora el quiz y la práctica 👇");
    } else {
      repintarLeccion(d, d.leccion.contenido);
      const c2 = $(`.control-parte[data-p="${n}"]`); if (c2) c2.scrollIntoView({ behavior: "smooth", block: "center" });
      aviso(estado === "no" ? "Anotado: vuelve a tu plan hasta que la entiendas" : "Anotado");
    }
  }));
  $$("[data-reex]", caja).forEach((b) => (b.onclick = async () => {
    const est = $(".reex-estado", caja); $$("[data-reex]", caja).forEach((x) => (x.disabled = true));
    est.innerHTML = `<span class="cargando"></span> Pidiendo la explicación…`;
    try {
      const j = await api("reexplicar", { tema: d.tema.id, parte: n, estilo: b.dataset.reex, duda: $(".duda-parte", caja).value });
      const r = await esperarTrabajo(j.trabajo, (t) => (est.innerHTML = `<span class="cargando"></span> ${esc(textoEstado(t))}`));
      const nuevo = { parte: n, estilo: r.estilo, texto: r.texto, duda: $(".duda-parte", caja).value, fecha: Date.now() / 1000 };
      d.partes.reexplicaciones.push(nuevo);
      $(".reex", caja).insertAdjacentHTML("beforeend", htmlReex(nuevo));
      const ult = $$(".reex .rx-cuerpo", caja).pop(); pintarMd(ult, ult.dataset.md);
      est.innerHTML = "Al terminar, vuelve a marcar cómo te fue con la parte 👆";
    } catch (e) { est.textContent = "Error: " + e.message; }
    $$("[data-reex]", caja).forEach((x) => (x.disabled = false));
  }));
}

/* ---------- diagnóstico antes de leer (pretest) ----------
   Mitad del quiz ANTES de leer: si aciertas todo, se confirma con la otra mitad y te ahorras la lectura; si no, cada
   pregunta fallada marca la parte que la explica (📌). Probarse antes también mejora lo que se recuerda después. */
function partesTexto(contenido) {
  const out = {};
  String(contenido || "").split(/^## /m).forEach((b) => { const m = /^\s*Parte\s+(\d+)/i.exec(b); if (m) out[+m[1]] = b; });
  return out;
}
const palabrasClave = (t) => new Set((String(t).toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").match(/[a-zñ0-9]{5,}/g) || []));
function parteDePregunta(p, partes) {
  const q = palabrasClave(p.pregunta + " " + (p.explicacion || "") + " " + ((p.opciones || [])[p.correcta] || ""));
  let mejor = null, max = 0;
  Object.entries(partes).forEach(([n, txt]) => { const w = palabrasClave(txt); let s = 0; q.forEach((x) => w.has(x) && s++); if (s > max) { max = s; mejor = +n; } });
  return mejor;
}
function ofrecerDiagnostico(d, quiz) {
  const caja = $("#diagCaja"); if (!caja || d.area.idioma) return;
  const P = d.partes || {}; const av = d.avance || {};
  const ops = quiz.map((p, i) => ({ ...p, i })).filter((p) => p.tipo === "opcion" && (p.opciones || []).length);
  if (ops.length < 4 || P.diagnostico || Object.keys(P.estados || {}).length || ["dominado", "probado"].includes(av.estado)
      || (E.yo && E.yo.perfil.diagnostico_previo === false)) return;
  const primera = ops.filter((_, k) => k % 2 === 0).slice(0, 4), segunda = ops.filter((p) => !primera.includes(p)).slice(0, 4);
  caja.innerHTML = `<div class="tarjeta" style="border-color:var(--acento)"><b>⚡ Antes de leer: ¿cuánto sabes ya?</b>
    <p class="suave peq" style="margin:.3rem 0">${primera.length} preguntas (~1 min). Si ya lo sabes, te ahorras la lectura${d.formato && d.formato.min_leccion ? ` (~${d.formato.min_leccion} min)` : ""}; si no, verás en qué partes enfocarte. Intentarlo antes de leer ayuda a recordar después, aunque falles.</p>
    <div class="fila"><button class="btn pri" id="diagEmpezar">Empezar</button><button class="btn fantasma" id="diagSaltar">Leer directamente</button></div><div id="diagZona"></div></div>`;
  $("#diagSaltar").onclick = () => { caja.innerHTML = ""; api("diagnostico", { tema: d.tema.id, bien: 0, total: 0, flojas: [] }); };
  $("#diagEmpezar").onclick = () => { $("#diagEmpezar").parentNode.hidden = true; preguntasDiag($("#diagZona"), primera, d, (res) => {
    const partes = partesTexto(d.leccion.contenido);
    const flojas = [...new Set(res.filter((r) => !r.ok).map((r) => parteDePregunta(r.p, partes)).filter((x) => x))];
    const bien = res.filter((r) => r.ok).length;
    api("diagnostico", { tema: d.tema.id, bien, total: res.length, flojas, vistas: primera.map((p) => p.i) }).then((x) => { d.partes = { ...(d.partes || { estados: {}, reexplicaciones: [] }), diagnostico: x.diagnostico }; repintarLeccion(d, d.leccion.contenido); });
    if (bien === res.length && segunda.length) {
      $("#diagZona").insertAdjacentHTML("beforeend", `<p>🎯 <b>${bien}/${res.length}.</b> Parece que ya lo sabes. Confírmalo con ${segunda.length} preguntas más y, si llegas al 80 %, el tema queda dominado sin leer.</p><button class="btn pri" id="diagConf">Confirmar</button> <button class="btn fantasma" id="diagLeer">Prefiero leerlo</button><div id="diagZona2"></div>`);
      $("#diagLeer").onclick = () => (caja.innerHTML = "");
      $("#diagConf").onclick = () => { $("#diagConf").remove(); $("#diagLeer").remove(); preguntasDiag($("#diagZona2"), segunda, d, async (res2) => {
        const todo = res.concat(res2), p = todo.filter((r) => r.ok).length / todo.length;
        api("diagnostico", { tema: d.tema.id, bien: todo.filter((r) => r.ok).length, total: todo.length, flojas: [], vistas: segunda.map((q) => q.i) });
        await api("resultado", { tema: d.tema.id, quiz: p });
        if (p >= 0.8) {
          const v = await api("visto", { tema: d.tema.id });
          $("#diagZona2").innerHTML = `<p>🎉 <b>${Math.round(p * 100)} %: tema dominado sin leer.</b> ${v.tarjetas} tarjetas a tu repaso para que no se olvide. Ahorraste ~${(d.formato && d.formato.min_leccion) || 20} min.</p>${d.siguiente ? `<button class="btn pri" onclick="ir('tema/${d.siguiente}')">Siguiente tema →</button>` : ""}`;
        } else $("#diagZona2").innerHTML = `<p>${Math.round(p * 100)} %: casi. Lee las partes marcadas 📌 y haz el quiz al final.</p>`;
      }); };
    } else {
      $("#diagZona").insertAdjacentHTML("beforeend", `<p><b>${bien}/${res.length}.</b> ${flojas.length ? `Enfócate en ${flojas.map((n) => `<a href="javascript:void 0" data-ir-p="${n}">parte ${n}</a>`).join(", ")} (marcadas 📌); lo demás puedes leerlo más rápido.` : "Lee la lección y haz el quiz al final."}</p>`);
      $$("[data-ir-p]", caja).forEach((a) => (a.onclick = () => { const s = $(`section[data-parte="${a.dataset.irP}"]`); if (s) { E.parteActual = +a.dataset.irP; aplicarPaso(d); s.scrollIntoView({ behavior: "smooth" }); } }));
    }
  }); };
}
function preguntasDiag(zona, preguntas, d, alTerminar) {
  const res = [];
  zona.innerHTML = preguntas.map((p, i) => `<div class="pregunta" data-dq="${i}"><div class="pq"></div>${p.opciones.map((o, j) => `<button class="opcion" data-j="${j}"></button>`).join("")}<div class="exp"></div></div>`).join("");
  preguntas.forEach((p, i) => {
    const caja = $(`[data-dq="${i}"]`, zona);
    pintarMd($(".pq", caja), `**${i + 1}.** ${p.pregunta}`);
    $$(".opcion", caja).forEach((b, j) => { pintarMd(b, p.opciones[j] || ""); b.onclick = () => {
      if (res[i]) return;
      res[i] = { p, ok: j === p.correcta };
      $$(".opcion", caja)[p.correcta]?.classList.add("ok"); if (j !== p.correcta) b.classList.add("no");
      pintarMd($(".exp", caja), "💡 " + p.explicacion);
      if (res.filter((x) => x).length === preguntas.length) alTerminar(res);
    }; });
  });
}

/* =============================== HORIZONTE ===============================
   Hay más por aprender que vida: cuánto falta para cada nivel a tu ritmo REAL, repartido vs. enfocado. */
function plazo(dias) {
  if (dias == null) return "—";
  if (dias < 60) return `${dias} días`;
  if (dias < 730) return `${Math.round(dias / 30)} meses`;
  return `${(dias / 365).toFixed(1).replace(".0", "")} años`;
}
VISTAS.horizonte = async () => {
  const h = await api("horizonte");
  const foco = new Set(h.enfoque);
  vista.innerHTML = `<h1>🔭 Tu horizonte</h1>
    <p class="suave">No hay vida para aprenderlo todo, así que la Academia mide cuánto te cuesta de verdad cada meta y te muestra dónde rinde más tu tiempo. Los plazos son según tu ruta en la Academia y se recalculan solos con cada tema que haces.</p>
    <div class="stats">
      <div class="stat"><b>${h.ritmo.min_por_tema}<small class="suave"> min</small></b><span>por tema ${h.ritmo.medido ? "(medido)" : "(estimado)"}</span></div>
      <div class="stat"><b>${Math.round(h.minutos_meta)}</b><span>min/día de meta</span></div>
      <div class="stat"><b>${h.minutos_real ?? "—"}</b><span>min/día reales</span></div>
      <div class="stat"><b>${h.anios_junior_todo}<small class="suave"> años</small></b><span>todo a «profesional junior» a tu meta</span></div></div>
    ${h.consejo.length ? `<div class="tarjeta" style="border-color:var(--medio)"><b>🧭 Lo que dicen tus números</b><ul class="consejos">${h.consejo.map((c) => `<li>${esc(c)}</li>`).join("")}</ul></div>` : ""}
    <div class="tarjeta"><b>🎯 Enfocarte</b><p class="suave peq">Marca las áreas en las que quieres avanzar rápido (sugeridas: las de más prioridad). Quedan en prioridad 3; las demás, en mantenimiento (sin temas nuevos; sus tarjetas se siguen repasando para que no se olviden) o de fondo (avanzan poco). Lo puedes deshacer en Ajustes.</p>
      <div class="chips" style="flex-wrap:wrap">${h.areas.map((a) => `<button class="chip ${foco.has(a.id) ? "activo" : ""}" data-foco="${a.id}">${esc(a.icono || "")} ${esc(a.nombre)}</button>`).join("")}</div>
      <div class="fila" style="margin-top:.5rem"><select id="focoResto" style="width:auto"><option value="0">Las demás: mantenimiento (prioridad 0, solo repaso)</option><option value="1">Las demás: de fondo (prioridad 1)</option></select>
      <button class="btn pri" id="focoAplicar">Aplicar enfoque</button></div></div>
    <h2>Cuánto falta, área por área</h2>
    <p class="suave peq">Horas = temas que faltan × tus minutos por tema. «Repartido» = con tu prioridad actual y tu meta diaria; «enfocado» = si te dedicas solo a las ${h.enfoque_n} marcadas; «a tu ritmo real» = con los minutos que de verdad estudias. El ${Math.round(h.fraccion_nuevo * 100)} % del tiempo va a temas nuevos; el resto, a repasar.</p>
    ${h.areas.sort((a, b) => b.peso - a.peso).map((a) => `<div class="tarjeta"><div class="fila entre"><b>${esc(a.icono || "")} ${esc(a.nombre)}</b><span class="suave peq">prioridad ${a.peso}${a.meta ? " · de tus metas" : ""} · hoy: ${esc(a.nivel_nombre)}</span></div>
      ${a.niveles.length ? `<div class="tabla-h"><table><thead><tr><th>Nivel</th><th>Horas</th><th>Repartido</th><th>Enfocado</th><th>A tu ritmo real</th></tr></thead><tbody>
        ${a.niveles.map((n) => `<tr><td>${esc(n.etiqueta)}</td><td>${n.horas}</td><td>${plazo(n.dias_repartido)}</td><td>${n.dias_enfoque != null ? `<b>${plazo(n.dias_enfoque)}</b>` : "—"}</td><td>${plazo(n.dias_real)}</td></tr>`).join("")}</tbody></table></div>`
        : `<p class="suave peq">🎉 Ya alcanzaste el nivel más alto de esta ruta.</p>`}</div>`).join("") || `<p class="vacio">${SIN_AREAS}</p>`}`;
  $$("[data-foco]").forEach((b) => (b.onclick = () => b.classList.toggle("activo")));
  $("#focoAplicar").onclick = async () => {
    const areas = $$("[data-foco].activo").map((b) => b.dataset.foco);
    if (!areas.length) return aviso("Marca al menos un área");
    if (!confirm(`¿Poner ${areas.length} área(s) en prioridad 3 y las demás en ${$("#focoResto").value === "1" ? "prioridad 1 (de fondo)" : "mantenimiento (prioridad 0, solo repaso)"}?`)) return;
    await api("enfoque", { areas, resto: +$("#focoResto").value }); E.yo = null;
    aviso("🎯 Enfoque aplicado: el plan de hoy se rehace si aún no empezaste"); enrutar();
  };
};

/* ---------- ubícame en un área: búsqueda binaria con pruebas de nivel ----------
   En vez de una prueba por módulo, prueba el del medio: si lo superas, sus requisitos de esa área se dan por sabidos y
   sigue más arriba; si no, más abajo. 3-4 pruebas bastan para ubicarte en un área de 10-15 módulos. */
function ubicarme(a, todas = false, clave = null) {
  // El estado de la búsqueda binaria se guarda en el servidor: se retoma al volver, también desde otro equipo.
  clave = clave || (todas ? "meta" : "area") + ":" + (a.id || a.nombre).toString().toLowerCase().replace(/[^a-z0-9_.]/g, "_");
  const todos = a.modulos.filter((m) => m.dominio < 0.8).sort((x, y) => x.nivel - y.nivel);
  if (!todos.length) return aviso("Ya dominas todos los módulos de esta ruta");
  let st = null;
  const guardar = () => api("ubicacion/estado", { clave, estado: st }).catch(() => {});
  const siguiente = () => {
    if (st.lo > st.hi) {
      const alto = st.alto; st = null; guardar();
      modal(`<h2>🎯 Ubicación lista</h2><p>${alto ? `Llegas al menos hasta <b>${esc(alto.t)}</b> (nivel ${alto.nivel} · ${NIVELES[alto.nivel]}): lo anterior quedó como sabido y tus lecciones nuevas empiezan desde ahí.` : "Lo mejor es empezar desde los fundamentos: ahí te espera tu ruta."}</p>
        <p class="suave peq">Si algo marcado como sabido no lo recuerdas, el chequeo semanal y el pulso lo detectan y lo devuelven al plan.</p><button class="btn pri" onclick="cerrarModal();enrutar()">Ver mi ruta</button>`);
      return;
    }
    const mid = Math.floor((st.lo + st.hi) / 2), m = st.mods[mid];
    st.actual = m.ref; guardar();
    pruebaNivel(m.ref, async (res) => {
      st.hechas++;
      if (res.aprobado) { await api("ubicacion/inferir", { ref: m.ref, todas }); st.alto = m; st.lo = mid + 1; } else st.hi = mid - 1;
      st.actual = null; guardar(); siguiente();
    }, `Ubicación en ${a.nombre} · prueba ${st.hechas + 1} (quedan ~${Math.max(1, Math.ceil(Math.log2(st.hi - st.lo + 2)))})`);
  };
  api("ubicacion/estado?clave=" + encodeURIComponent(clave)).then((g) => {
    if (g.estado && g.estado.mods) {
      modal(`<h2>🎯 Ubícame en ${esc(a.nombre)}</h2><p>Tienes una ubicación a medias (${g.estado.hechas} prueba(s) hechas${g.estado.alto ? `; llegas al menos hasta «${esc(g.estado.alto.t)}»` : ""}).</p>
        <div class="fila"><button class="btn pri" id="ubSeguir">Continuar donde iba</button><button class="btn" id="ubOtra">Empezar de nuevo</button></div>`, () => {
        $("#ubSeguir").onclick = () => { st = g.estado; siguiente(); };
        $("#ubOtra").onclick = () => { st = { mods: todos.map((m) => ({ ref: m.ref, t: m.t, nivel: m.nivel })), lo: 0, hi: todos.length - 1, hechas: 0, alto: null }; siguiente(); };
      });
      return;
    }
    modal(`<h2>🎯 Ubícame en ${esc(a.nombre)}</h2><p>Te pongo ~${Math.ceil(Math.log2(todos.length + 1))} pruebas de nivel cortas, empezando por un módulo del medio: si lo superas, lo anterior queda como sabido y subo; si no, bajo. Así no estudias lo que ya sabes.</p>
      <p class="suave peq">Cada prueba tarda 2-5 min en prepararse. Todo se guarda: si cierras, la ubicación y cada prueba se retoman donde ibas (también desde otro equipo).</p>
      <div class="fila"><button class="btn pri" id="ubEmpezar">Empezar</button><button class="btn fantasma" onclick="cerrarModal()">Ahora no</button></div>`, () => ($("#ubEmpezar").onclick = () => {
      st = { mods: todos.map((m) => ({ ref: m.ref, t: m.t, nivel: m.nivel })), lo: 0, hi: todos.length - 1, hechas: 0, alto: null }; siguiente(); }));
  });
}

/* ---------- lo que ya estudiaste fuera (Coursera, Platzi, DataCamp, universidad…) ---------- */
function htmlExterno(x) {
  if (!x || !x.equivalencias) return "";
  if (!x.equivalencias.length) return `<p class="suave peq">La IA no encontró módulos de tu ruta que eso cubra.</p>`;
  return `<p class="suave peq">Verifica cada módulo con una prueba corta: si la pasas, no lo vuelves a estudiar.</p>${x.equivalencias.map((e) => `
    <div class="fila entre" style="border-top:1px solid var(--borde);padding:.4rem 0"><div style="min-width:0"><b>${esc(e.area)} › ${esc(e.modulo)}</b> <span class="etq">${"★".repeat(e.confianza)}${"☆".repeat(3 - e.confianza)}</span>
      <div class="suave peq">${esc(e.curso)} — ${esc(e.nota)}</div></div><button class="btn peq" data-verif="${esc(e.ref)}">⚡ Verificar</button></div>`).join("")}`;
}
async function montarExterno() {
  const z = $("#extCaja"); if (!z) return;
  const r = await api("externo").catch(() => ({}));
  if (r.externo) { $("#extTexto").value = r.externo.texto; $("#extRes").innerHTML = htmlExterno(r.externo); }
  const enlazar = () => $$("[data-verif]", z).forEach((b) => (b.onclick = () => pruebaNivel(b.dataset.verif)));
  enlazar();
  $("#extBtn").onclick = async () => {
    const texto = $("#extTexto").value.trim(); if (texto.length < 5) return aviso("Cuenta qué estudiaste");
    const est = $("#extRes"); est.innerHTML = `<span class="cargando"></span> Relacionando con tu ruta…`;
    try {
      const j = await api("externo", { texto });
      const x = await esperarTrabajo(j.trabajo, (t) => (est.innerHTML = `<span class="cargando"></span> ${esc(textoEstado(t))}`));
      est.innerHTML = htmlExterno(x); enlazar();
    } catch (e) { est.textContent = "Error: " + e.message; }
  };
}

/* ---------- práctica: entregas por ejercicio, con versiones y corrección ---------- */
async function montarPractica(d, tarea) {
  const c = $("#practicaCuerpo"); if (!c) return;
  const r = await api(tarea ? "entregas?tarea=" + tarea : "entregas?tema=" + encodeURIComponent(d.tema.id));
  const ejs = r.ejercicios;
  const versiones = {}; r.entregas.forEach((e) => (versiones[e.ejercicio] = (versiones[e.ejercicio] || 0) + 1));
  c.innerHTML = `<label>¿Qué ejercicio entregas?</label>
    <select id="ejSel">${ejs.map((e) => `<option value="${e.n}">${esc(e.titulo)}${versiones[e.n] ? ` (${versiones[e.n]} entrega${versiones[e.n] > 1 ? "s" : ""})` : ""} — ${esc(e.enunciado.slice(0, 70))}…</option>`).join("")}
      <option value="otro">Otro / todo junto…</option></select>
    <input type="text" id="ejOtro" placeholder="¿Qué entregas? (ej.: «ejercicios 1 y 2», «reto final»)" hidden style="margin-top:.4rem">
    <div class="chips" style="margin:.7rem 0 .4rem"><button class="chip activo" data-modo="texto">✍️ Escribir</button><button class="chip" data-modo="foto">📷 Foto o imagen</button><button class="chip" data-modo="mano">🖊️ A mano (S Pen)</button></div>
    <div data-panel="texto"><textarea id="entTexto" placeholder="Tu solución: planteamiento, procedimiento y resultado (con unidades)…"></textarea></div>
    <div data-panel="foto" hidden><input type="file" id="entFoto" accept="image/*" style="min-height:auto"><img id="entPrev" hidden style="max-width:100%;margin-top:.5rem;border-radius:8px;border:1px solid var(--borde)" alt="">
      <textarea id="entNota" placeholder="(Opcional) algo que quieras aclarar" style="min-height:60px;margin-top:.4rem"></textarea></div>
    <div data-panel="mano" hidden><p class="peq">Se abre el cuaderno ligado a este ejercicio; al terminar pulsa <b>«📤 Guardar y entregar»</b>.</p>
      <button class="btn" id="entMano">✍️ Abrir el cuaderno para este ejercicio</button></div>
    <div class="fila" style="margin-top:.6rem" id="entBotonFila"><button class="btn pri" id="entEnviar">📤 Entregar y corregir</button><span id="entEstado" class="suave peq"></span></div>
    <h3 style="margin-bottom:.3rem">Tus entregas</h3><div id="entLista">${listaEntregas(r.entregas, ejs)}</div>`;
  let modo = "texto", fotoData = null;
  const ejercicio = () => ($("#ejSel").value === "otro" ? ($("#ejOtro").value.trim() || "otro") : $("#ejSel").value);
  $("#ejSel").onchange = () => ($("#ejOtro").hidden = $("#ejSel").value !== "otro");
  $$("[data-modo]", c).forEach((b) => (b.onclick = () => {
    modo = b.dataset.modo; $$("[data-modo]", c).forEach((x) => x.classList.toggle("activo", x === b));
    $$("[data-panel]", c).forEach((p) => (p.hidden = p.dataset.panel !== modo)); $("#entBotonFila").hidden = modo === "mano";
  }));
  $("#entFoto").onchange = async (ev) => {
    const f = ev.target.files[0]; if (!f) return;
    fotoData = await reducirImagen(f); const im = $("#entPrev"); im.src = fotoData; im.hidden = false;
  };
  $("#entMano").onclick = () => ir(`cuaderno/nueva?tema=${d.tema.id}&ejercicio=${encodeURIComponent(ejercicio())}${tarea ? "&tarea=" + tarea : ""}`);
  $("#entEnviar").onclick = async () => {
    const datos = { tema: d.tema.id, ejercicio: ejercicio(), tarea: tarea || null };
    if (modo === "texto") { datos.texto = $("#entTexto").value.trim(); if (datos.texto.length < 3) return aviso("Escribe tu solución"); }
    if (modo === "foto") { if (!fotoData) return aviso("Elige o toma una foto"); datos.imagen = fotoData; datos.texto = $("#entNota").value.trim(); }
    $("#entEnviar").disabled = true; $("#entEstado").innerHTML = `<span class="cargando"></span> Enviando…`;
    try {
      const j = await api("entrega", datos);
      aviso(`📤 Entregado: ${tituloEj(datos.ejercicio, ejs)} · versión ${j.version}`);
      await montarPractica(d, tarea);
      seguirCorreccion(j.trabajo, d, tarea);
    } catch (e) { $("#entEstado").textContent = "Error: " + e.message; $("#entEnviar").disabled = false; }
  };
  $$("[data-recorregir]", c).forEach((b) => (b.onclick = async () => { const j = await api("entrega/corregir", { id: +b.dataset.recorregir }); await montarPractica(d, tarea); seguirCorreccion(j.trabajo, d, tarea); }));
  $$("[data-borrar-ent]", c).forEach((b) => (b.onclick = async () => { if (confirm("¿Borrar esta entrega?")) { await api("entrega/borrar", { id: +b.dataset.borrarEnt }); montarPractica(d, tarea); } }));
  $$("[data-nueva-version]", c).forEach((b) => (b.onclick = () => {
    const v = b.dataset.nuevaVersion; const opt = [...$("#ejSel").options].find((o) => o.value === v);
    if (opt) $("#ejSel").value = v; else { $("#ejSel").value = "otro"; $("#ejOtro").hidden = false; $("#ejOtro").value = v; }
    $("#ejSel").scrollIntoView({ behavior: "smooth", block: "center" }); aviso("Entrega la versión corregida de este ejercicio");
  }));
  const pend = r.entregas.find((e) => e.corrigiendo);
  if (pend) setTimeout(() => { if ($("#practicaCuerpo")) montarPractica(d, tarea); }, 8000);
  $$("[data-img-ent]", c).forEach((im) => (im.onclick = () => window.open(im.src, "_blank")));
  $$(".ent-eval", c).forEach((el) => renderMath(el));
}
function tituloEj(n, ejs) { const e = ejs.find((x) => String(x.n) === String(n)); return e ? e.titulo : (/^\d+$/.test(n) ? "Ejercicio " + n : n); }
function listaEntregas(lista, ejs) {
  if (!lista.length) return `<p class="suave peq">Aún no has entregado nada de esta lección.</p>`;
  return lista.map((e) => {
    const ev = e.evaluacion; const p = e.puntaje;
    const cls = p == null ? "" : p >= 80 ? "bien" : p >= 55 ? "medio" : "mal";
    const icono = { texto: "✍️ escrito", imagen: "📷 foto", cuaderno: "🖊️ a mano" }[e.tipo] || e.tipo;
    return `<details class="entrega"><summary><div class="fila entre"><span><b>${esc(tituloEj(e.ejercicio, ejs))}</b> · versión ${e.version}<br>
      <span class="suave peq">${new Date(e.creado * 1000).toLocaleString(LOC, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })} · ${icono}</span></span>
      ${e.corrigiendo ? `<span class="etq medio"><span class="cargando"></span> corrigiendo</span>` : p == null ? `<span class="etq">sin corregir</span>` : `<span class="etq ${cls}">${Math.round(p)}/100 · ${esc(ev.veredicto)}</span>`}</div></summary>
      ${e.tiene_imagen ? `<img data-img-ent src="api/entrega/img/${e.id}?v=${Math.round(e.creado)}" style="max-width:100%;border-radius:8px;border:1px solid var(--borde);margin-top:.5rem;cursor:zoom-in;background:#fff" alt="Tu entrega">` : ""}
      ${e.texto ? `<div class="peq" style="white-space:pre-wrap;background:var(--panel2);padding:.5rem .7rem;border-radius:8px;margin-top:.5rem">${esc(e.texto)}</div>` : ""}
      ${ev ? `<div class="ent-eval nota-ia">${ev.bien.length ? `<p>✅ ${ev.bien.map(esc).join("<br>✅ ")}</p>` : ""}${ev.errores.length ? `<p>❌ ${ev.errores.map(esc).join("<br>❌ ")}</p>` : ""}
        <details><summary class="peq"><b>Corrección paso a paso</b></summary><div class="leccion peq">${md(ev.correccion)}</div></details>
        ${e.tipo !== "texto" ? `<details><summary class="peq">Lo que la IA leyó de tu entrega</summary><div class="leccion peq">${md(ev.transcripcion)}</div></details>` : ""}
        ${ev.siguiente ? `<p>👉 ${esc(ev.siguiente)}</p>` : ""}</div>` : ""}
      <div class="fila" style="margin-top:.5rem"><button class="btn peq" data-nueva-version="${esc(e.ejercicio)}">📤 Entregar nueva versión</button>
        <button class="btn peq fantasma" data-recorregir="${e.id}">🔄 Corregir de nuevo</button><button class="btn peq fantasma" data-borrar-ent="${e.id}">🗑</button></div></details>`;
  }).join("");
}
async function seguirCorreccion(trabajo, d, tarea) {
  try {
    await esperarTrabajo(trabajo, (t) => { const e = $("#entEstado"); if (e) e.innerHTML = `<span class="cargando"></span> ${esc(textoEstado(t))} (≈1-2 min)`; });
  } catch (e) { aviso("Error al corregir: " + e.message); }
  if (E.temaActual === d.tema.id && $("#practicaCuerpo")) { await montarPractica(d, tarea); const pr = $("#entLista details"); if (pr) pr.open = true; }
}
function reducirImagen(archivo, max = 1600) {
  // fotos del celular (12-200 MP) → JPEG de ≤1600 px: suficiente para leer la letra, liviano para subir
  return new Promise((ok, mal) => {
    const url = URL.createObjectURL(archivo); const im = new Image();
    im.onload = () => {
      const k = Math.min(1, max / Math.max(im.width, im.height));
      const c = document.createElement("canvas"); c.width = Math.round(im.width * k); c.height = Math.round(im.height * k);
      const g = c.getContext("2d"); g.fillStyle = "#fff"; g.fillRect(0, 0, c.width, c.height); g.drawImage(im, 0, 0, c.width, c.height);
      URL.revokeObjectURL(url); ok(c.toDataURL("image/jpeg", 0.85));
    };
    im.onerror = () => mal(new Error("No pude leer la imagen"));
    im.src = url;
  });
}
function notaIA(r) {
  const cls = r.puntaje >= 80 ? "bien" : r.puntaje >= 55 ? "medio" : "mal";
  return `<div class="nota-ia"><b class="p" style="color:var(--${cls})">${r.puntaje}/100</b>
    ${r.bien ? `<p>✅ ${esc(r.bien)}</p>` : ""}${r.mal ? `<p>❌ ${esc(r.mal)}</p>` : ""}${r.falto ? `<p>➕ ${esc(r.falto)}</p>` : ""}${r.siguiente ? `<p>👉 ${esc(r.siguiente)}</p>` : ""}</div>`;
}
function pintarQuiz(d, quiz) {
  const c = $("#quiz");
  if (!quiz.length) { c.innerHTML = `<p class="suave">Esta lección no trae quiz. Usa el tutor para que te pregunte.</p>`; return; }
  const res = [];
  // las que se respondieron en el diagnóstico antes de leer ya se conocen: no cuentan (si quedan al menos 3 nuevas)
  const vistas = new Set(((d.partes && d.partes.diagnostico) || {}).vistas || []);
  const cuentan = quiz.map((_, i) => !vistas.has(i));
  const nuevas = cuentan.filter(Boolean).length;
  if (nuevas < 3) cuentan.fill(true);
  c.innerHTML = (vistas.size ? `<p class="suave peq">${nuevas >= 3 ? `Las ${vistas.size} preguntas que respondiste antes de leer están marcadas y <b>no cuentan</b> en la nota (ya viste su respuesta).` : `Ya viste casi todas estas preguntas en el diagnóstico: la nota sale inflada. Para medirte de verdad crea una <b>🏋️ tarea de quiz</b> con preguntas nuevas (🔁 Repasar).`}</p>` : "") +
    quiz.map((p, i) => `<div class="pregunta" data-i="${i}">${vistas.has(i) && nuevas >= 3 ? `<span class="etq">vista antes de leer · no cuenta</span>` : ""}<div class="pq"></div>
    ${p.tipo === "opcion" && p.opciones.length ? p.opciones.map((o, j) => `<button class="opcion" data-j="${j}"></button>`).join("")
      : `<textarea placeholder="Tu respuesta…"></textarea><button class="btn peq" style="margin-top:.4rem" data-corregir>Corregir</button>`}
    <div class="exp"></div></div>`).join("") + `<div id="quizFin" class="nota-ia" hidden></div>`;
  const cerrar = () => {
    if (res.filter((x) => x != null).length < quiz.length) return;
    const idx = quiz.map((_, i) => i).filter((i) => cuentan[i]);
    const p = idx.reduce((s, i) => s + res[i], 0) / idx.length;
    const f = $("#quizFin"); f.hidden = false;
    f.innerHTML = `<b class="p">${Math.round(p * 100)}%</b> ${p >= 0.8 ? "🎉 ¡Tema dominado!" : "Repasa las que fallaste y vuelve a intentarlo mañana (el olvido parcial ayuda)."}`;
    api("resultado", { tema: d.tema.id, quiz: p });
    const fallos = res.map((x, i) => (x < 0.6 ? i : null)).filter((i) => i != null);
    if (fallos.length) api("quiz/fallos", { tema: d.tema.id, fallos }).then((r) => { if (r.agregadas) f.insertAdjacentHTML("beforeend", `<div class="suave peq" style="margin-top:.3rem">🃏 ${r.agregadas} pregunta(s) que fallaste quedaron como tarjetas: vuelven a tu repaso hasta que las domines.</div>`); }).catch(() => {});
  };
  quiz.forEach((p, i) => {
    const caja = $(`[data-i="${i}"]`, c);
    pintarMd($(".pq", caja), `**${i + 1}.** ${p.pregunta}`, d.area.idioma);
    if (p.tipo === "opcion" && p.opciones.length) {
      $$(".opcion", caja).forEach((b, j) => { pintarMd(b, p.opciones[j] || ""); b.onclick = () => {
        if (res[i] != null) return;
        res[i] = j === p.correcta ? 1 : 0;
        $$(".opcion", caja)[p.correcta]?.classList.add("ok"); if (j !== p.correcta) b.classList.add("no");
        pintarMd($(".exp", caja), "💡 " + p.explicacion); cerrar();
      }; });
    } else {
      $("[data-corregir]", caja).onclick = async (ev) => {
        const txt = $("textarea", caja).value.trim(); if (!txt) return;
        ev.target.disabled = true; const ex = $(".exp", caja); ex.innerHTML = `<span class="cargando"></span> Corrigiendo…`;
        try {
          const j = await api("corregir", { tema: d.tema.id, pregunta: p.pregunta, modelo: p.explicacion, respuesta: txt });
          const r = await esperarTrabajo(j.trabajo, (t) => (ex.innerHTML = `<span class="cargando"></span> ${esc(textoEstado(t))}`));
          ex.innerHTML = notaIA(r) + `<details><summary class="suave peq">Respuesta modelo</summary><div class="rm"></div></details>`;
          pintarMd($(".rm", ex), p.explicacion);
          res[i] = r.puntaje / 100; cerrar();
        } catch (e) { ex.textContent = "Error: " + e.message; ev.target.disabled = false; }
      };
    }
  });
}

/* =============================== REPASAR =============================== */
VISTAS.repasar = async () => {
  const d = await api("repaso?n=200");
  let i = 0, t0 = Date.now(), hechas = 0;
  if (!d.tarjetas.length) {
    vista.innerHTML = `<h1>🔁 Repasar</h1>${barraPractica()}<div class="tarjeta vacio">🎉 Nada pendiente por ahora.<br>Las tarjetas vuelven justo antes de que las olvides.
      <div style="margin-top:1rem"><button class="btn" id="nuevaT">➕ Crear tarjeta</button></div></div>`;
    $("#nuevaT").onclick = crearTarjeta; activarBarraPractica(); return;
  }
  const pintar = () => {
    const t = d.tarjetas[i];
    if (!t) { vista.innerHTML = `<h1>🔁 Repasar</h1><div class="tarjeta vacio">✅ ¡Sesión terminada! ${hechas} tarjetas.<br><button class="btn pri" style="margin-top:1rem" onclick="enrutar()">Ver si quedan más</button></div>`; refrescarIA(); return; }
    E.areaActual = t.area; E.idiomaActual = t.idioma;
    const a = AREA_ES[t.area];
    vista.innerHTML = `<div class="fila entre"><h1 style="margin:0">🔁 Repasar</h1><span class="suave">${i + 1} / ${d.tarjetas.length}</span></div>${barraPractica()}
      <div class="barra-prog" style="margin:.5rem 0 1rem"><i style="width:${(i / d.tarjetas.length) * 100}%"></i></div>
      <div class="tarjeta flash"><div class="suave peq" style="margin-bottom:.6rem">${t.nueva ? "🆕 nueva · " : ""}${esc(a ? a.nombre : t.area || "")}</div>
        <div class="frente" id="frente"></div><div class="reverso" id="reverso" hidden></div></div>
      <div id="acciones"><button class="btn pri" style="width:100%;min-height:56px" id="mostrar">Mostrar respuesta <span class="suave peq">(espacio)</span></button></div>
      <div class="fila" style="margin-top:.8rem"><button class="btn fantasma peq" id="editar">✏️ Editar</button><button class="btn fantasma peq" id="suspender">🚫 Suspender</button>
        ${t.tema ? `<button class="btn fantasma peq" onclick="ir('tema/${t.tema}')">📖 Ver lección</button>` : ""}<button class="btn fantasma peq" id="nuevaT">➕ Nueva</button></div>`;
    pintarMd($("#frente"), t.frente);
    if (t.idioma) { const b = document.createElement("button"); b.className = "hablar"; b.textContent = "🔊"; b.onclick = () => hablar(soloIdioma(t.frente, NO_LATINO.test(t.frente) ? NO_LATINO : null), t.idioma); $("#frente").appendChild(b); }
    t0 = Date.now();
    const mostrar = () => {
      const r = $("#reverso"); r.hidden = false; pintarMd(r, t.reverso, t.idioma);
      $("#acciones").innerHTML = `<div class="notas4">${[["n1", 1, "Otra vez"], ["n2", 2, "Difícil"], ["n3", 3, "Bien"], ["n4", 4, "Fácil"]].map(([c, n, l]) =>
        `<button class="${c}" data-n="${n}">${l}<small>${t.botones[n]}</small></button>`).join("")}</div>
        <p class="suave peq" style="text-align:center">Sé honesto: "Bien" = lo recordaste con esfuerzo normal. Teclas 1-4.</p>`;
      $$("[data-n]").forEach((b) => (b.onclick = () => calificar(+b.dataset.n)));
    };
    const calificar = async (n) => {
      api("repaso", { id: t.id, nota: n, segundos: (Date.now() - t0) / 1000 }).catch((e) => aviso(e.message));
      hechas++;
      if (n === 1) d.tarjetas.splice(Math.min(d.tarjetas.length, i + 6), 0, Object.assign({}, t, { nueva: false, botones: t.botones }));
      i++; pintar();
    };
    $("#mostrar").onclick = mostrar;
    $("#editar").onclick = () => editarTarjeta(t, pintar);
    $("#suspender").onclick = async () => { await api("tarjeta/suspender", { id: t.id }); d.tarjetas.splice(i, 1); pintar(); };
    $("#nuevaT").onclick = crearTarjeta; activarBarraPractica();
    E.teclas = (e) => {
      if (e.target.tagName === "TEXTAREA" || e.target.tagName === "INPUT") return;
      if (e.code === "Space") { e.preventDefault(); if (!$("#reverso").hidden) return; mostrar(); }
      if (/^[1-4]$/.test(e.key) && !$("#reverso").hidden) calificar(+e.key);
    };
  };
  if (!Object.keys(AREA_ES).length) (await api("mapa")).areas.forEach((a) => (AREA_ES[a.id] = a));
  document.addEventListener("keydown", (e) => E.teclas && E.teclas(e));
  E.salir = () => (E.teclas = null);
  pintar();
};
/* ---------- tareas de práctica (desde Repasar) ---------- */
function barraPractica() {
  return `<div class="fila" style="margin:.5rem 0"><button class="btn pri peq" id="nuevaTarea">🏋️ Crear tarea de práctica</button><button class="btn peq" onclick="ir('tareas')">📋 Mis tareas</button></div>`;
}
function activarBarraPractica() { const b = $("#nuevaTarea"); if (b) b.onclick = () => crearTarea(E.temaActual); }
async function crearTarea(temaInicial) {
  const s = await api("tarea/sugerencias");
  if (!s.grupos.length) return modal(`<h2>🏋️ Nueva tarea de práctica</h2><p>Aún no has estudiado ningún tema. Abre una lección en «Hoy» o en la Ruta y vuelve aquí.</p><button class="btn" onclick="cerrarModal()">Cerrar</button>`);
  const elegidos = new Set(temaInicial && s.temas[temaInicial] ? [temaInicial] : []);
  let tipo = "desarrollo", dif = "intermedia";
  let grupo = (temaInicial && s.temas[temaInicial] ? "area:" + s.temas[temaInicial].area : null) || (s.sugeridos.length ? "sugeridos" : s.grupos[0].id);
  const grupos = [...(s.sugeridos.length ? [{ id: "sugeridos", nombre: "⚠️ Se te están olvidando", temas: s.sugeridos }] : []), ...s.grupos,
    { id: "todos", nombre: "📚 Todos los temas vistos", temas: Object.keys(s.temas) }];
  modal(`<h2>🏋️ Nueva tarea de práctica</h2>
    <label>Tipo</label><div class="chips"><button class="chip activo" data-tipo="desarrollo">📝 Desarrollo</button><button class="chip" data-tipo="quiz">✅ Quiz</button></div>
    <p class="suave peq" id="tipoAyuda"></p>
    <label>Área o meta</label><select id="tGrupo">${grupos.map((g) => `<option value="${g.id}" ${g.id === grupo ? "selected" : ""}>${esc(g.nombre)} (${g.temas.length})</option>`).join("")}</select>
    <div class="fila entre" style="margin-top:.5rem"><span class="peq"><b id="tCuenta">0</b> tema(s) elegidos → una tarea por tema</span>
      <span><button class="btn peq fantasma" id="tTodos">Marcar todos</button><button class="btn peq fantasma" id="tNinguno">Ninguno</button></span></div>
    <div class="lista-temas" id="tLista"></div>
    <label>Dificultad</label><div class="chips"><button class="chip" data-dif="basica">🟢 Básica</button><button class="chip activo" data-dif="intermedia">🟡 Intermedia</button><button class="chip" data-dif="reto">🔴 Reto</button></div>
    <label id="tCantLbl">Ejercicios por tarea</label><select id="tCant" style="width:auto"></select>
    <label>Enfoque (opcional)</label><input type="text" id="tEnf" placeholder="Ej.: con motores, en contexto de finanzas personales…">
    <div class="fila" style="margin-top:.8rem"><button class="btn pri" id="tCrear">Crear</button><button class="btn" onclick="cerrarModal()">Cancelar</button><span id="tEstado" class="suave peq"></span></div>`, (c) => {
    const pintarCant = () => {
      const [opc, def] = tipo === "quiz" ? [[3, 5, 8, 10, 15], 5] : [[1, 2, 3, 4, 5, 6], 3];
      $("#tCant", c).innerHTML = opc.map((n) => `<option ${n === def ? "selected" : ""}>${n}</option>`).join("");
      $("#tCantLbl", c).textContent = tipo === "quiz" ? "Preguntas por quiz" : "Ejercicios por tarea";
      $("#tipoAyuda", c).textContent = tipo === "quiz"
        ? "Preguntas de opción múltiple que respondes aquí y se califican al instante, con explicación. Puedes repetirlo cuando quieras."
        : "Ejercicios para resolver en papel, en el cuaderno o escritos, con pista y solución; los entregas (texto, foto o a mano) y la IA los corrige.";
    };
    const pintarLista = () => {
      const g = grupos.find((x) => x.id === grupo) || grupos[0];
      const porArea = {};
      g.temas.forEach((id) => { const t = s.temas[id]; if (t) (porArea[t.area_nombre] = porArea[t.area_nombre] || []).push(t); });
      $("#tLista", c).innerHTML = Object.entries(porArea).map(([an, ts]) => `<div class="nivel-tit">${esc(an)}</div>` + ts.map((t) => `
        <label class="tema-check"><input type="checkbox" value="${t.id}" ${elegidos.has(t.id) ? "checked" : ""}>
          <span>${esc(t.t)}<br><span class="suave peq">${esc(t.modulo)}${t.olvido != null ? ` · <span style="color:var(--medio)">se te olvida (${Math.round(t.olvido * 100)} %)</span>` : ""}${t.estado === "dominado" || t.estado === "probado" ? " · ✓ dominado" : ""}</span></span></label>`).join("")).join("") || `<p class="suave">Sin temas aquí.</p>`;
      $$("#tLista input", c).forEach((i) => (i.onchange = () => { i.checked ? elegidos.add(i.value) : elegidos.delete(i.value); $("#tCuenta").textContent = elegidos.size; }));
      $("#tCuenta").textContent = elegidos.size;
    };
    $$("[data-tipo]", c).forEach((b) => (b.onclick = () => { tipo = b.dataset.tipo; $$("[data-tipo]", c).forEach((x) => x.classList.toggle("activo", x === b)); pintarCant(); }));
    $$("[data-dif]", c).forEach((b) => (b.onclick = () => { dif = b.dataset.dif; $$("[data-dif]", c).forEach((x) => x.classList.toggle("activo", x === b)); }));
    $("#tGrupo", c).onchange = (e) => { grupo = e.target.value; pintarLista(); };
    $("#tTodos", c).onclick = () => { $$("#tLista input", c).forEach((i) => elegidos.add(i.value)); pintarLista(); };
    $("#tNinguno", c).onclick = () => { elegidos.clear(); pintarLista(); };
    pintarCant(); pintarLista();
    $("#tCrear", c).onclick = async () => {
      if (!elegidos.size) return aviso("Marca al menos un tema");
      if (elegidos.size > 20) return aviso("Máximo 20 temas a la vez");
      $("#tCrear").disabled = true;
      try {
        const j = await api("tarea/nueva", { temas: [...elegidos], tipo, dificultad: dif, cantidad: +$("#tCant").value, enfoque: $("#tEnf").value });
        if (j.trabajos.length > 1) { cerrarModal(); aviso(`🏋️ ${j.trabajos.length} ${tipo === "quiz" ? "quizzes" : "tareas"} en preparación (≈2-4 min cada uno)`); return ir("tareas"); }
        const r = await esperarTrabajo(j.trabajo, (t) => { const e = $("#tEstado"); if (e) e.innerHTML = `<span class="cargando"></span> ${esc(textoEstado(t))} (1-4 min)`; });
        cerrarModal(); ir("tarea/" + r.tarea);
      } catch (e) { $("#tEstado").textContent = "Error: " + e.message; $("#tCrear").disabled = false; }
    };
  });
}
const DIF_TXT = { basica: "🟢 Básica", intermedia: "🟡 Intermedia", reto: "🔴 Reto" };
VISTAS.tareas = async (_, q) => {
  const d = await api("tareas");
  vista.innerHTML = `<div class="fila entre"><h1 style="margin:0">📋 Mis tareas de práctica</h1><button class="btn pri" id="nuevaTarea">🏋️ Nueva tarea</button></div>
    <p class="suave">📝 Desarrollo: un ejercicio cuenta como aprobado con 80/100 o más. ✅ Quiz: se califica al instante; tu mejor intento cuenta.</p>
    ${d.pendientes.map((p) => `<div class="tarjeta"><span class="cargando"></span> Creando tarea… ${esc(textoEstado(p))}</div>`).join("")}
    ${d.tareas.map((t) => {
      const quiz = t.tipo === "quiz";
      const prog = quiz ? (t.mejor || 0) : t.aprobados / t.n;
      const etq = quiz ? (t.intentos ? `mejor: ${Math.round(t.mejor * 100)} % · ${t.intentos} intento${t.intentos > 1 ? "s" : ""}` : "sin hacer") : `${t.aprobados}/${t.n} aprobados`;
      return `<div class="tarjeta" style="cursor:pointer" onclick="ir('tarea/${t.id}')"><div class="fila entre"><b>${quiz ? "✅" : "📝"} ${esc(t.titulo)}</b><span class="etq ${prog >= 0.8 ? "bien" : prog > 0 ? "medio" : ""}">${etq}</span></div>
      <div class="suave peq">${esc(t.tema_t)} · ${quiz ? `quiz de ${t.n} preguntas` : `desarrollo · ${t.entregados}/${t.n} entregados`} · ${DIF_TXT[t.dificultad] || esc(t.dificultad)} · ${new Date(t.creado * 1000).toLocaleDateString(LOC)}</div>
      <div class="barra-prog" style="margin-top:.4rem"><i style="width:${prog * 100}%"></i></div></div>`; }).join("") || (d.pendientes.length ? "" : `<p class="vacio">Aún no hay tareas. Crea la primera con «🏋️ Nueva tarea».</p>`)}`;
  $("#nuevaTarea").onclick = () => crearTarea();
  if (q && q.nueva) { history.replaceState(null, "", "#/tareas"); crearTarea(); }
  if (d.pendientes.length) setTimeout(() => location.hash === "#/tareas" && refrescar(), 6000);
};
VISTAS.tarea = async ([id]) => {
  const t = await api("tarea?id=" + id);
  if (t.error) throw new Error(t.error);
  E.temaActual = t.tema; E.areaActual = t.area; E.idiomaActual = t.idioma;
  if (t.tipo === "quiz") return quizTarea(t, id);
  vista.innerHTML = `<div class="fila entre"><button class="btn fantasma peq" onclick="ir('tareas')">← Mis tareas</button><button class="btn fantasma peq" id="borrarTarea">🗑</button></div>
    <h1>🏋️ ${esc(t.titulo)}</h1>
    <p class="suave">${esc(t.area_nombre)} › <a href="#/tema/${t.tema}">${esc(t.tema_t)}</a> · ${DIF_TXT[t.dificultad] || esc(t.dificultad)}${t.enfoque ? " · enfoque: " + esc(t.enfoque) : ""}</p>
    <p class="peq">Resuélvelos en papel, en el cuaderno o aquí. Usa la pista si te trabas; mira la solución <b>solo después</b> de entregar.</p>
    <div id="ejsTarea">${t.ejercicios.map((e, i) => `<div class="tarjeta leccion"><h3 style="margin-top:0">Ejercicio ${i + 1}: ${esc(e.titulo)}</h3><div class="enun"></div>
      <details><summary>💡 Pista</summary><div class="pis"></div></details><details><summary>✅ Solución</summary><div class="sol"></div></details></div>`).join("")}</div>
    <div class="tarjeta" id="practica"><h2 style="margin-top:0">📤 Entrega tus soluciones</h2><div id="practicaCuerpo"><span class="cargando"></span></div></div>`;
  $$("#ejsTarea .tarjeta").forEach((c, i) => {
    const e = t.ejercicios[i];
    pintarMd($(".enun", c), e.enunciado, t.idioma); pintarMd($(".pis", c), e.pista); pintarMd($(".sol", c), e.solucion, t.idioma);
  });
  $("#borrarTarea").onclick = async () => { if (confirm("¿Borrar esta tarea y sus entregas?")) { await api("tarea/borrar", { id: +id }); ir("tareas"); } };
  montarPractica({ tema: { id: t.tema } }, +id);
  if (E.irPractica) { E.irPractica = false; setTimeout(() => $("#practica").scrollIntoView({ behavior: "smooth" }), 400); }
};

function quizTarea(t, id) {
  const resp = [];
  const mejor = t.intentos.length ? Math.max(...t.intentos.map((i) => i.bien / i.total)) : null;
  vista.innerHTML = `<div class="fila entre"><button class="btn fantasma peq" onclick="ir('tareas')">← Mis tareas</button><button class="btn fantasma peq" id="borrarTarea">🗑</button></div>
    <h1>✅ ${esc(t.titulo)}</h1>
    <p class="suave">${esc(t.area_nombre)} › <a href="#/tema/${t.tema}">${esc(t.tema_t)}</a> · ${DIF_TXT[t.dificultad] || esc(t.dificultad)} · ${t.ejercicios.length} preguntas
      ${t.intentos.length ? ` · <span class="etq ${mejor >= 0.8 ? "bien" : "medio"}">mejor: ${Math.round(mejor * 100)} % (${t.intentos.length} intento${t.intentos.length > 1 ? "s" : ""})</span>` : ""}</p>
    <div class="tarjeta" id="quizTarea"></div>
    <div id="quizFinTarea" class="tarjeta" hidden></div>`;
  const c = $("#quizTarea");
  c.innerHTML = t.ejercicios.map((p, i) => `<div class="pregunta" data-i="${i}"><div class="pq"></div>${p.opciones.map((o, j) => `<button class="opcion" data-j="${j}"></button>`).join("")}<div class="exp suave peq"></div></div>`).join("");
  t.ejercicios.forEach((p, i) => {
    const caja = $(`[data-i="${i}"]`, c);
    pintarMd($(".pq", caja), `**${i + 1}.** ${p.pregunta}`, t.idioma);
    $$(".opcion", caja).forEach((b, j) => { pintarMd(b, p.opciones[j]); b.onclick = async () => {
      if (resp[i] !== undefined) return;
      resp[i] = j;
      $$(".opcion", caja)[p.correcta].classList.add("ok"); if (j !== p.correcta) b.classList.add("no");
      pintarMd($(".exp", caja), "💡 " + p.explicacion);
      if (resp.filter((x) => x !== undefined).length === t.ejercicios.length) {
        const r = await api("tarea/quiz", { id: +id, respuestas: resp });
        const f = $("#quizFinTarea"); f.hidden = false;
        const pc = r.bien / r.total;
        f.innerHTML = `<b style="font-size:1.4rem;color:var(--${pc >= 0.8 ? "bien" : pc >= 0.55 ? "medio" : "mal"})">${r.bien}/${r.total} (${Math.round(pc * 100)} %)</b>
          <p>${pc >= 0.8 ? "🎉 ¡Muy bien!" : "Repasa las explicaciones de las que fallaste y vuelve a intentarlo."}</p>
          <div class="fila"><button class="btn" onclick="enrutar()">🔄 Repetir este quiz</button><button class="btn pri" id="otroQuiz">✨ Quiz nuevo de este tema</button></div>`;
        $("#otroQuiz").onclick = () => crearTarea(t.tema);
        f.scrollIntoView({ behavior: "smooth" });
      }
    }; });
  });
  $("#borrarTarea").onclick = async () => { if (confirm("¿Borrar este quiz?")) { await api("tarea/borrar", { id: +id }); ir("tareas"); } };
}

function editarTarjeta(t, luego) {
  modal(`<h2>Editar tarjeta</h2><label>Frente</label><textarea id="ef">${esc(t.frente)}</textarea><label>Reverso</label><textarea id="er">${esc(t.reverso)}</textarea>
    <div class="fila" style="margin-top:.8rem"><button class="btn pri" id="eg">Guardar</button><button class="btn" onclick="cerrarModal()">Cancelar</button></div>`, (c) => {
    $("#eg", c).onclick = async () => { t.frente = $("#ef").value; t.reverso = $("#er").value; await api("tarjeta/editar", { id: t.id, frente: t.frente, reverso: t.reverso }); cerrarModal(); luego(); };
  });
}
function crearTarjeta() {
  modal(`<h2>➕ Nueva tarjeta</h2><label>Frente (pregunta)</label><textarea id="nf"></textarea><label>Reverso (respuesta)</label><textarea id="nr"></textarea>
    <label>Idioma para leer en voz alta (opcional)</label><select id="ni"><option value="">—</option><option value="en-US">Inglés</option><option value="zh-CN">Chino</option><option value="ko-KR">Coreano</option><option value="ja-JP">Japonés</option><option value="ru-RU">Ruso</option><option value="de-DE">Alemán</option></select>
    <div class="fila" style="margin-top:.8rem"><button class="btn pri" id="ng">Agregar</button><button class="btn" onclick="cerrarModal()">Cancelar</button></div>`, (c) => {
    $("#ng", c).onclick = async () => {
      const idi = $("#ni").value; const area = { "en-US": "ingles", "zh-CN": "chino", "ko-KR": "coreano", "ja-JP": "japones", "ru-RU": "ruso", "de-DE": "aleman" }[idi] || null;
      await api("tarjeta", { frente: $("#nf").value, reverso: $("#nr").value, idioma: idi || null, area });
      cerrarModal(); aviso("Tarjeta agregada");
    };
  });
}

/* =============================== TUTOR =============================== */
VISTAS.tutor = async (_, q) => {
  const hilo = q.hilo || "general"; const tema = q.tema || null;
  const [chat, hilos] = await Promise.all([api("chat?hilo=" + encodeURIComponent(hilo)), api("hilos")]);
  let titulo = "General";
  if (tema) { try { const t = await api("tema?id=" + tema); titulo = t.tema.t; E.areaActual = t.area.id; E.idiomaActual = t.area.idioma; } catch (e) {} }
  vista.innerHTML = `<div class="fila entre"><h1 style="margin:0">💬 Tutor</h1>
      <select id="hilos" style="width:auto;max-width:55%"><option value="general">Conversación general</option>
      ${hilos.hilos.filter((h) => h.hilo !== "general").map((h) => `<option value="${esc(h.hilo)}" ${h.hilo === hilo ? "selected" : ""}>${esc(h.hilo)}</option>`).join("")}</select></div>
    <p class="suave peq">${tema ? `Sobre: <b>${esc(titulo)}</b> (el tutor ve tu lección). ` : ""}Pídele que te explique distinto, que te haga preguntas, que te ponga un ejercicio o que te examine. Modo socrático: primero te guía.</p>
    <div class="chat" id="chat">${chat.mensajes.length ? "" : `<div class="suave peq">Ideas: «hazme 5 preguntas difíciles», «explícamelo con una analogía de motores», «¿cómo se usa esto en un brazo robótico?», «corrígeme esta frase en coreano: …»</div>`}</div>
    <div class="entrada-chat"><textarea id="msg" placeholder="Escribe tu pregunta…"></textarea>
      <div style="display:flex;flex-direction:column;gap:.3rem"><button class="btn pri" id="enviar">➤</button><button class="btn peq" id="web" title="Buscar en la web antes de responder">🌐</button></div></div>
    <div class="fila"><button class="btn fantasma peq" id="borrar">🗑 Borrar conversación</button></div>`;
  const cc = $("#chat");
  const agregar = (rol, texto) => { const m = document.createElement("div"); m.className = "msg " + rol; if (rol === "tutor") pintarMd(m, texto, E.idiomaActual); else m.textContent = texto; cc.appendChild(m); return m; };
  chat.mensajes.forEach((m) => agregar(m.rol, m.texto));
  window.scrollTo(0, document.body.scrollHeight);
  let web = false;
  $("#web").onclick = () => { web = !web; $("#web").classList.toggle("pri", web); aviso(web ? "Buscará en la web (SearXNG local) antes de responder" : "Sin búsqueda web"); };
  $("#hilos").onchange = (e) => ir("tutor?hilo=" + encodeURIComponent(e.target.value) + (e.target.value.includes(".") ? "&tema=" + e.target.value : ""));
  $("#borrar").onclick = async () => { if (confirm("¿Borrar esta conversación?")) { await api("chat/borrar", { hilo }); enrutar(); } };
  const enviar = async () => {
    const txt = $("#msg").value.trim(); if (!txt) return;
    $("#msg").value = ""; agregar("usuario", txt);
    const m = agregar("tutor", "…"); m.innerHTML = `<span class="cargando"></span>`;
    window.scrollTo(0, document.body.scrollHeight);
    try {
      const j = await api("tutor", { hilo, mensaje: txt, tema, web });
      const r = await esperarTrabajo(j.trabajo, (t) => {
        if (t.texto) pintarMd(m, t.texto); else m.innerHTML = `<span class="cargando"></span> <span class="suave peq">${esc(textoEstado(t))}</span>`;
      });
      pintarMd(m, r.texto, E.idiomaActual);
    } catch (e) { m.textContent = "Error: " + e.message; }
  };
  $("#enviar").onclick = enviar;
  $("#msg").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey && matchMedia("(pointer:fine)").matches) { e.preventDefault(); enviar(); } });
};

/* =============================== NOTICIAS =============================== */
const PERIODOS = { dia: "Hoy", semana: "Semana", mes: "Mes", anio: "Año" };
function colorImp(n) { return n >= 8 ? "var(--mal)" : n >= 6 ? "var(--medio)" : n >= 4 ? "var(--acento)" : "var(--suave)"; }
// En las noticias solo se nombran las áreas de quien las ve (E.misAreas sale de /api/yo).
const miaN = (x) => !E.misAreas || E.misAreas.has(x);
async function cargarMisAreas() { if (E.misAreas === undefined) { const y = await api("yo"); E.misAreas = y.areas ? new Set(y.areas) : null; } }
const REGIONES = {};   // id → {nombre, icono}; se llena al arrancar
const regionesTxt = (rs) => (rs || []).filter((r) => r !== "global" && REGIONES[r])
  .map((r) => `<span title="${esc(REGIONES[r].nombre)}">${esc(REGIONES[r].icono)}</span> `).join("");
function tarjetaNoticia(n) {
  const a = n.analisis ? { ...n.analisis, impactos: n.analisis.impactos.filter((i) => miaN(i.area)) } : null;
  const imp = a ? a.importancia : null;
  return `<div class="tarjeta noticia"><div class="fila" style="align-items:flex-start;flex-wrap:nowrap">
    <span class="imp" style="background:${imp ? colorImp(imp) : "var(--panel2)"};color:${imp ? "#fff" : "var(--suave)"}" title="Importancia (IA)">${imp ?? "·"}</span>
    <div style="min-width:0;flex:1"><h3><a href="${escUrl(n.url)}" target="_blank" rel="noopener">${esc(a ? a.titulo_es : n.titulo)}</a></h3>
    <div class="suave peq">${regionesTxt(n.regiones)}${esc(n.fuente)}${n.cobertura > 1 ? ` · <b>${n.cobertura} fuentes</b>` : ""} · ${new Date(n.publicada * 1000).toLocaleString(LOC, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}${a ? ` · ${esc(a.tipo_hecho)} · impacto: ${esc(a.plazo)}` : ""}</div>
    <p style="margin:.35rem 0">${esc(a ? a.resumen_es : n.resumen.slice(0, 240))}</p>
    ${a ? `<div class="impactos">${a.impactos.map((i) => `<span class="chip" title="${esc(i.como)}">${esc(AREA_ES[i.area]?.icono || "")} ${esc(AREA_ES[i.area]?.nombre || i.area)} ${"●".repeat(i.nivel)}</span>`).join("")}</div>
      ${a.impactos.length ? `<details><summary class="suave peq">¿Cómo afecta a cada área?</summary><ul class="peq">${a.impactos.map((i) => `<li><b>${esc(AREA_ES[i.area]?.nombre || i.area)} (${i.nivel}/5):</b> ${esc(i.como)}</li>`).join("")}</ul>
      ${a.organizaciones.length ? `<p class="peq"><b>Actores:</b> ${a.organizaciones.map(esc).join(", ")}</p>` : ""}</details>` : ""}
      ${a.contexto ? `<details><summary class="suave peq">🕰️ Contexto, conceptos y consecuencias</summary><div class="peq">
        <p><b>Contexto:</b> ${esc(a.contexto)}</p>${a.por_que_importa ? `<p><b>Por qué importa:</b> ${esc(a.por_que_importa)}</p>` : ""}
        ${(a.conceptos || []).length ? `<b>Conceptos para entenderla:</b><ul>${a.conceptos.map((c) => `<li><b>${esc(c.concepto)}:</b> ${esc(c.explicacion)}</li>`).join("")}</ul>` : ""}
        ${(a.consecuencias || []).length ? `<p><b>Cadena de consecuencias:</b> ${a.consecuencias.map(esc).join(" → ")}</p>` : ""}
        ${(a.preguntas || []).length ? `<b>Para pensar:</b><ul>${a.preguntas.map((q) => `<li>${esc(q)}</li>`).join("")}</ul>` : ""}</div></details>` : ""}
      <div class="fila" style="margin-top:.3rem"><button class="btn peq pri" onclick="ir('noticia/${n.id}')">🔎 A fondo${n.cobertura > 1 ? ` · comparar ${n.cobertura} fuentes` : ""}${n.tiene && (n.tiene.explicacion || n.tiene.comparacion) ? " ✓" : ""}</button>
      ${n.estudiar && miaN(n.estudiar.ref.split(".")[0]) ? `<button class="btn peq fantasma" onclick="ir('ruta/${n.estudiar.ref.split(".")[0]}')">📚 Para entenderla: ${esc(n.estudiar.t)}</button>` : ""}
      ${(n.extra || []).filter((x) => miaN(x.ref.split(".")[0])).map((x) => `<button class="btn peq fantasma" onclick="ir('ruta/${x.ref.split(".")[0]}')">📚 ${esc(x.t)}</button>`).join("")}</div>`
      : `<div class="impactos">${n.areas.filter(miaN).map((x) => `<span class="chip">${esc(AREA_ES[x]?.icono || "")} ${esc(AREA_ES[x]?.nombre || x)}</span>`).join("")}</div>
      <button class="btn peq" style="margin-top:.3rem" onclick="ir('noticia/${n.id}')">🔎 A fondo${n.cobertura > 1 ? ` · comparar ${n.cobertura} fuentes` : ""}</button>`}
    </div></div></div>`;
}
VISTAS.noticias = async ([periodo = "dia"], q) => {
  if (!Object.keys(AREA_ES).length) (await api("mapa")).areas.forEach((a) => (AREA_ES[a.id] = a));
  await cargarMisAreas();
  const area = q.area || "";
  const [d, l] = await Promise.all([api(`noticias?periodo=${periodo}&area=${area}`), api("lecturas")]);
  const ult = d.ultima ? new Date(d.ultima.fecha * 1000).toLocaleString(LOC, { hour: "2-digit", minute: "2-digit", day: "numeric", month: "short" }) : "nunca";
  const areasN = d.mis_areas || [];   // solo las áreas de este perfil: sin áreas no hay noticias que mostrar
  const lect = l.lecturas || [];
  vista.innerHTML = `<h1>🌍 Noticias del mundo para tus áreas</h1>
    ${!areasN.length ? `<div class="tarjeta">${SIN_AREAS.replace("Aún no tienes áreas.", "Aquí verás solo las noticias de tus áreas y metas.")}</div>` : `
    <div class="chips" style="margin-bottom:.5rem">${Object.entries(PERIODOS).map(([k, v]) => `<button class="chip ${k === periodo ? "activo" : ""}" onclick="ir('noticias/${k}${area ? "?area=" + area : ""}')">${v}</button>`).join("")}</div>
    <div class="chips">${["", ...areasN].map((x) => `<button class="chip ${x === area ? "activo" : ""}" onclick="ir('noticias/${periodo}${x ? "?area=" + x : ""}')">${x ? esc(AREA_ES[x].icono + " " + AREA_ES[x].nombre) : "Todas"}</button>`).join("")}</div>
    <p class="suave peq">De ~65 medios y organismos verificados (BBC, Nature, IEEE, FT, bancos centrales, ONU…). Todo se actualiza
      <b>una vez al día, a las ${esc(d.hora_diaria || "06:00")}</b> (la hora de la actualización diaria). Solo ves noticias ya
      procesadas a máxima profundidad: el artículo completo analizado, comparado entre medios y explicado a fondo. Última descarga: ${ult}.
      ${d.preparando ? `<br>⏳ ${d.preparando} noticias preparándose a fondo ahora (aparecen al terminar; mira ⏳).` : ""}</p>
    <div class="tarjeta" style="margin-top:1rem"><h2 style="margin:0">🧭 Síntesis ${{ dia: "del día", semana: "de la semana", mes: "del mes", anio: "del año" }[periodo]}</h2>
      <div id="sintTexto" class="leccion"></div></div>
    <h2>🏆 Top ${PERIODOS[periodo].toLowerCase()}</h2><div id="ranking">${d.ranking.map(tarjetaNoticia).join("") || `<p class="vacio">${areasN.length ? "Sin noticias de tus áreas en este periodo." : SIN_AREAS.replace("Aún no tienes áreas.", "Aquí verás las noticias de tus áreas.")}</p>`}</div>
    <h2>📊 Dónde pega: impacto por área</h2>
    <p class="suave peq">Para cada área, las noticias que más la afectan (nivel de impacto × importancia). Áreas ordenadas por presión total.</p>
    <div class="matriz">${d.impacto.filter((x) => x.top.length).map((x) => `<div class="tarjeta"><div class="fila entre"><b>${esc(x.icono)} ${esc(x.nombre)}</b><span class="suave peq">${x.total} noticias</span></div>
      <ol>${x.top.map((t) => `<li><a href="${escUrl(t.url)}" target="_blank" rel="noopener">${esc(t.titulo)}</a> <span class="etq">${"●".repeat(t.nivel)}</span><br><span class="suave peq">${esc(t.como)}</span></li>`).join("")}</ol></div>`).join("") || `<p class="suave">Aparece cuando la IA haya analizado noticias del periodo.</p>`}</div>
    <h2>🏛️ Organizaciones y actores clave</h2>
    <div class="tarjeta">${d.organizaciones.length ? `<ol>${d.organizaciones.map((o) => `<li><b>${esc(o.nombre)}</b> — ${o.menciones} noticia${o.menciones > 1 ? "s" : ""} ${o.areas.some(miaN) ? ` · afecta: ${o.areas.filter(miaN).map((a) => esc(AREA_ES[a]?.nombre || a)).join(", ")}` : ""}</li>`).join("")}</ol>` : `<p class="suave">Aparece cuando la IA haya analizado noticias del periodo.</p>`}</div>`}
    ${lect.length ? `<h2>🈶 Lectura real en tus idiomas</h2><p class="suave peq">Titulares de hoy en los idiomas que estudias. «Estudiar» arma una lectura guiada con traducción, vocabulario y tarjetas.</p>
    <div id="lecturas"></div>` : ""}`;
  if (lect.length) {
    const porArea = {}; lect.forEach((x) => (porArea[x.area] = porArea[x.area] || []).push(x));
    $("#lecturas").innerHTML = Object.entries(porArea).map(([a, xs]) => `<div class="tarjeta"><b>${esc(AREA_ES[a]?.icono || "")} ${esc(AREA_ES[a]?.nombre || a)}</b>
    <ul class="temas">${xs.slice(0, 4).map((x) => `<li style="cursor:default"><span lang="${esc(x.idioma)}" style="flex:1">${esc(x.titulo)} <span class="suave peq">· ${esc(x.fuente)}</span></span>
    <button class="btn peq" data-lect="${x.id}">Estudiar</button></li>`).join("")}</ul></div>`).join("");
    $$("[data-lect]").forEach((b) => (b.onclick = () => estudiarLectura(b.dataset.lect)));
  }
  if (!areasN.length) return;
  if (d.sintesis) pintarMd($("#sintTexto"), d.sintesis.texto); else $("#sintTexto").innerHTML = `<p class="suave">Aún no hay síntesis para este periodo: se escribe sola en la actualización diaria, después de procesar las noticias a fondo.</p>`;
};
async function trabajoNoticias(ruta, datos) {
  const e = $("#notEstado");
  try {
    const j = await api(ruta, datos);
    await esperarTrabajo(j.trabajo, (t) => { if ($("#notEstado")) $("#notEstado").innerHTML = `<span class="cargando"></span> ${esc(textoEstado(t))}`; });
    refrescar();
  } catch (x) { if (e) e.textContent = "Error: " + x.message; }
}
/* ---------- una noticia a fondo: cómo la cuenta cada medio + explicación ---------- */
const NIVEL_AF = { todas: ["🟢 Lo dicen todas las fuentes", "bien"], varias: ["🟡 Lo dicen varias", "medio"], una: ["🔴 Solo una fuente", "mal"] };
VISTAS.noticia = async ([id]) => {
  if (!Object.keys(AREA_ES).length) (await api("mapa")).areas.forEach((a) => (AREA_ES[a.id] = a));
  await cargarMisAreas();
  const n = await api("noticia?id=" + id);
  const a = n.analisis, pr = n.profundo || {}, cmp = pr.comparacion, ex = pr.explicacion;
  vista.innerHTML = `<button class="btn fantasma peq" onclick="history.back()">← Noticias</button>
    ${tarjetaNoticia(n)}
    <div class="tarjeta"><div class="fila entre"><h2 style="margin:0">🔍 Cómo la cuenta cada fuente</h2>
      <button class="btn peq" id="btnComparar">${cmp ? "Rehacer" : "Comparar fuentes"}</button></div>
      <p class="suave peq">La IA lee el artículo de cada medio que cuenta esta historia (si hay menos de 3, busca la misma historia en otros medios) y separa lo que todos dicen de lo que solo dice uno. Lo que repiten todas es lo mejor establecido; lo que cuenta una sola hay que tomarlo con más cuidado.</p>
      <div id="cmpCuerpo"></div></div>
    <div class="tarjeta"><div class="fila entre"><h2 style="margin:0">📖 Entenderla a fondo</h2>
      <button class="btn peq" id="btnExplicar">${ex ? "Rehacer" : "Explicármela a fondo"}</button></div>
      <p class="suave peq">Antecedentes, conceptos, mecanismo causa-efecto, perspectivas, qué significa para tus áreas y qué vigilar, con fuentes web y documentos científicos.</p>
      <div id="expCuerpo"></div></div>`;
  pintarComparacion(cmp);
  pintarExplicacion(ex);
  const lanzar = async (que, zona) => {
    $(zona).innerHTML = `<p><span class="cargando"></span> En cola…</p><div class="escribiendo" id="${que}Txt"></div>`;
    try {
      const j = await api("noticia/profundo", { id: n.id, que });
      await esperarTrabajo(j.trabajo, (t) => { const z = $(zona + " p"); if (z) z.innerHTML = `<span class="cargando"></span> ${esc(textoEstado(t))}`;
        const w = $("#" + que + "Txt"); if (w && t.texto) { w.textContent = t.texto; w.scrollTop = w.scrollHeight; } });
      refrescar();
    } catch (e) { $(zona).innerHTML = `<p>❌ ${esc(e.message)}</p>`; }
  };
  $("#btnComparar").onclick = () => lanzar("comparacion", "#cmpCuerpo");
  $("#btnExplicar").onclick = () => lanzar("explicacion", "#expCuerpo");
  if (n.trabajo) lanzar(n.trabajo.tipo === "comparar" ? "comparacion" : "explicacion", n.trabajo.tipo === "comparar" ? "#cmpCuerpo" : "#expCuerpo");
};
function pintarComparacion(c) {
  const z = $("#cmpCuerpo");
  if (!c) { z.innerHTML = `<p class="suave">Aún no se ha comparado.</p>`; return; }
  if (c.solo_una) { z.innerHTML = `<p class="suave">Solo se encontró una fuente para esta historia: no hay con qué comparar.</p>`; return; }
  const F = c.fuentes;
  const chipF = (i) => `<span class="chip peq" title="${esc(F[i]?.titulo || "")}">${F[i] && F[i].fiabilidad ? NIV_FIAB[F[i].fiabilidad.nivel][0] + " " : ""}${esc(F[i]?.fuente || "?")}</span>`;
  const grupos = { todas: [], varias: [], una: [] };
  c.afirmaciones.forEach((x) => grupos[x.nivel].push(x));
  z.innerHTML = `<p class="peq"><b>Fuentes leídas (${F.length}):</b> ${F.map((f, i) => `${fiab(f)} <a href="${escUrl(f.url)}" target="_blank" rel="noopener">${esc(f.fuente)}</a>${f.origen === "web" ? " <span class='suave'>(búsqueda)</span>" : ""}${f.leido ? "" : " <span class='suave'>(solo resumen)</span>"}`).join(" · ")}</p>
    <h3>De lo más común a lo menos común</h3>
    ${Object.entries(grupos).filter(([, xs]) => xs.length).map(([k, xs]) => `<div class="nivel-tit">${NIVEL_AF[k][0]} (${xs.length})</div>
      <ul class="afirmaciones">${xs.map((x) => `<li><span class="etq ${NIVEL_AF[k][1]}">${x.fuentes.length}/${F.length}</span> <span class="etq">${esc(x.tipo)}</span>${x.respaldo ? ` <span class="etq ${x.respaldo === "alto" ? "bien" : x.respaldo === "medio" ? "medio" : "mal"}" title="Según cuántas fuentes y de qué fiabilidad">respaldo ${esc(x.respaldo)}</span>` : ""} ${esc(x.texto)}<div style="margin-top:.2rem">${x.fuentes.map(chipF).join(" ")}</div></li>`).join("")}</ul>`).join("")}
    ${c.diferencias.length ? `<h3>⚖️ Dónde no coinciden</h3><ul>${c.diferencias.map((x) => `<li><b>${esc(x.aspecto)}:</b> ${esc(x.detalle)}</li>`).join("")}</ul>` : ""}
    ${c.contradicciones.length ? `<h3>⚠️ Contradicciones</h3><ul>${c.contradicciones.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}
    <h3>🎥 El enfoque de cada medio</h3><div class="matriz">${c.enfoques.map((e) => `<div class="tarjeta peq"><b>${esc(F[e.fuente]?.fuente || "?")}</b> <span class="etq">${esc(e.tono)}</span><p style="margin:.3rem 0">${esc(e.angulo)}</p>${e.omite ? `<span class="suave">Omite: ${esc(e.omite)}</span>` : ""}</div>`).join("")}</div>
    <p><b>Conclusión:</b> ${esc(c.conclusion)}</p>
    <p class="suave peq">Comparado el ${new Date(c.creado * 1000).toLocaleString(LOC)}. La IA puede equivocarse al atribuir: abre los artículos si algo importa.</p>`;
}
function pintarExplicacion(x) {
  const z = $("#expCuerpo");
  if (!x) { z.innerHTML = `<p class="suave">Aún no hay explicación a fondo.</p>`; return; }
  z.innerHTML = `<div class="leccion" id="expTexto"></div>
    ${x.papers.length ? `<details><summary><b>🔬 Documentos científicos relacionados</b></summary><ol class="peq">${x.papers.map((p) => `<li>${esc(p.autores)} (${esc(p.anio)}). <a href="${escUrl(p.url)}" target="_blank" rel="noopener">${esc(p.titulo)}</a>. <i>${esc(p.revista || "")}</i> · ${p.citas} citas</li>`).join("")}</ol></details>` : ""}
    ${x.tarjetas.length ? `<button class="btn" id="expTarjetas">🃏 Agregar ${x.tarjetas.length} tarjetas a mi repaso</button>` : ""}`;
  pintarMd($("#expTexto"), x.texto);
  LECT.iniciar($("#expTexto"), { tema: null, area: null, metodo: "noticias", idioma: "es" });
  if ($("#expTarjetas")) $("#expTarjetas").onclick = async (e) => {
    const r = await api("tarjetas", { tarjetas: x.tarjetas, origen: "noticia" }); e.target.disabled = true; aviso(`${r.agregadas ?? r.n ?? "Tarjetas"} agregadas`);
  };
}
async function verCiencia(ref, titulo) {
  modal(`<h2>🔬 Investigación: ${esc(titulo)}</h2><p class="suave peq">Artículos y revisiones reales de OpenAlex (más de 250 millones de trabajos, arXiv incluido): primero los más citados del tema y luego lo más reciente. Casi todos están en inglés.</p><div id="papCuerpo"><span class="cargando"></span></div>`);
  try {
    let r = await api("ciencia?ref=" + encodeURIComponent(ref));
    if (r.trabajo) { $("#papCuerpo").innerHTML = `<span class="cargando"></span> Preparando las búsquedas científicas del área (solo la primera vez, ~1 min)…`; await esperarTrabajo(r.trabajo); r = await api("ciencia?ref=" + encodeURIComponent(ref)); }
    $("#papCuerpo").innerHTML = r.papers.length ? `<p class="suave peq">Búsqueda: «${esc(r.consulta)}»</p><ol>${r.papers.map((p) => `<li style="margin-bottom:.7rem"><a href="${escUrl(p.url)}" target="_blank" rel="noopener"><b>${esc(p.titulo)}</b></a><br>
      <span class="peq">${esc(p.autores)} · ${esc(p.anio)} · <i>${esc(p.revista || p.tipo)}</i> · ${p.citas} citas ${p.tipo === "review" ? `<span class="etq bien">revisión</span>` : ""}${p.abierto ? ` · <a href="${escUrl(p.abierto)}" target="_blank" rel="noopener">📄 texto libre</a>` : ""}</span>
      ${p.resumen ? `<details><summary class="suave peq">Resumen</summary><p class="peq">${esc(p.resumen)}…</p></details>` : ""}</li>`).join("")}</ol>` : `<p class="suave">No se encontraron documentos (¿sin internet?).</p>`;
  } catch (e) { $("#papCuerpo").textContent = "Error: " + e.message; }
}
async function estudiarLectura(id) {
  modal(`<h2>📖 Lectura guiada</h2><p id="leEstado"><span class="cargando"></span> Preparando…</p><div id="leCuerpo"></div>`);
  try {
    const j = await api("lectura", { id: +id });
    const r = await esperarTrabajo(j.trabajo, (t) => { const e = $("#leEstado"); if (e) e.innerHTML = `<span class="cargando"></span> ${esc(textoEstado(t))}`; });
    $("#leEstado").innerHTML = `<a href="${escUrl(r.url)}" target="_blank" rel="noopener">${esc(r.titulo)}</a>`;
    $("#leCuerpo").innerHTML = `<div class="leccion"><h3>Texto <button class="hablar" id="leVoz">🔊</button></h3><div id="leTexto" lang="${esc(r.idioma)}"></div>
      <details><summary>Traducción</summary><div id="leTrad"></div></details>
      <h3>Vocabulario</h3><table><tr><th>Palabra</th><th>Pronunciación</th><th>Significado</th></tr>${r.vocabulario.map((v) => `<tr><td>${esc(v.palabra)}</td><td>${esc(v.pronunciacion)}</td><td>${esc(v.significado)}</td></tr>`).join("")}</table>
      <h3>Gramática</h3><div id="leGram"></div></div>
      <div class="fila" style="margin-top:1rem"><button class="btn pri" id="leTarj">➕ Vocabulario a mis tarjetas</button><button class="btn" onclick="cerrarModal()">Cerrar</button></div>`;
    LECT.iniciar($("#leCuerpo"), { tema: null, area: r.area, metodo: "lectura", idioma: r.idioma });
    pintarMd($("#leTexto"), r.texto.replace(/\n/g, "  \n")); pintarMd($("#leTrad"), r.traduccion.replace(/\n/g, "  \n")); pintarMd($("#leGram"), r.gramatica);
    ponerVoz($("#leCuerpo table"), r.idioma);
    $("#leVoz").onclick = () => hablar(r.texto.split("\n").filter((x, i) => i % 2 === 0 || !NO_LATINO.test(r.texto)).join(" "), r.idioma);
    $("#leTarj").onclick = async () => {
      const x = await api("tarjetas", { tarjetas: r.vocabulario.map((v) => ({ frente: v.palabra, reverso: `${v.pronunciacion} — ${v.significado}` })), area: r.area, idioma: r.idioma, origen: "noticia" });
      aviso(`${x.agregadas} tarjetas agregadas`);
    };
  } catch (e) { $("#leEstado").textContent = "Error: " + e.message; }
}

/* =============================== OBJETIVOS =============================== */
VISTAS.objetivos = async ([id]) => {
  if (!E.mapa) { const m = await api("mapa"); E.mapa = m.areas; m.areas.forEach((a) => (AREA_ES[a.id] = a)); }
  const d = await api("objetivos");
  if (id) {
    const o = d.objetivos.find((x) => String(x.id) === id);
    if (!o) return ir("objetivos");
    const porNivel = {}; o.pasos.forEach((p) => (porNivel[p.nivel] = porNivel[p.nivel] || []).push(p));
    const faltantes = o.pasos.filter((p) => p.estado !== "completo");
    const sig = faltantes.find((p) => p.abierto && p.faltan.length);
    vista.innerHTML = `<button class="btn fantasma peq" onclick="ir('objetivos')">← Objetivos</button>
      <h1>🎯 ${esc(o.titulo)}</h1>${o.descripcion ? `<p class="suave">${esc(o.descripcion)}</p>` : ""}
      <div class="tarjeta"><p style="margin-top:0">${esc(o.resumen)}</p><div class="fila entre"><b>${o.temas_hechos} / ${o.temas_total} temas</b><b>${Math.round(o.progreso * 100)}%</b></div>
        <div class="barra-prog" style="margin-top:.4rem"><i style="width:${o.progreso * 100}%"></i></div>
        <div class="stats" style="margin-bottom:0"><div class="stat"><b>${o.pasos.filter((p) => p.estado === "completo").length}</b><span>módulos completos</span></div>
        <div class="stat"><b>${o.pasos.filter((p) => p.estado === "en curso").length}</b><span>en curso</span></div>
        <div class="stat"><b>${o.pasos.filter((p) => p.estado === "faltante").length}</b><span>faltantes</span></div></div>
        ${sig ? `<button class="btn pri" style="margin-top:.8rem" onclick="ir('tema/${sig.faltan[0].id}')">▶ Siguiente paso: ${esc(sig.faltan[0].t)}</button>` : ""}</div>
      <div id="dominioCaja"><p class="vacio"><span class="cargando"></span></p></div><div id="rutaVivaMeta"></div>
      <h2>🗺️ La ruta completa</h2>
      <p class="suave peq">Incluye todos los prerrequisitos, en orden. ✓ = dominado. Los módulos marcados ⭐ los eligió la IA para este objetivo; el resto son la base que necesitan.</p>
      ${Object.entries(porNivel).map(([n, ps]) => `<div class="nivel-tit">Nivel ${n} · ${NIVELES[n]}</div>${ps.map((p) => `
        <details class="tarjeta modulo ${p.abierto ? "" : "cerrado"}" ${p.estado === "en curso" ? "open" : ""}><summary>
          <div class="fila entre"><b>${p.directo ? "⭐ " : ""}${p.abierto ? "" : "🔒 "}${esc(p.t)}</b><span class="etq ${p.estado === "completo" ? "bien" : p.estado === "en curso" ? "medio" : ""}">${p.estado}</span></div>
          <div class="suave peq">${esc(p.area)}${p.por_que ? " · " + esc(p.por_que) : ""}</div>
          <div class="barra-prog" style="margin-top:.4rem"><i style="width:${p.dominio * 100}%"></i></div></summary>
          ${p.hechos.length ? `<div class="peq" style="margin-top:.5rem">✅ <b>Completado:</b> ${p.hechos.map(esc).join(" · ")}</div>` : ""}
          ${p.faltan.length ? `<div class="peq" style="margin-top:.4rem">⬜ <b>Falta:</b></div><ul class="temas">${p.faltan.map((t) => `<li data-tema="${t.id}"><span class="punto"></span>${esc(t.t)}</li>`).join("")}</ul>` : ""}
          ${!p.abierto ? `<button class="btn peq" style="margin-top:.5rem" data-prueba="${p.ref}">⚡ Ya lo sé: prueba de nivel</button>` : ""}
        </details>`).join("")}`).join("")}
      <div class="fila" style="margin-top:1rem"><button class="btn" id="pausar">${o.estado === "activo" ? "⏸ Pausar" : "▶ Reactivar"}</button><button class="btn fantasma" id="borrarO">🗑 Borrar</button></div>`;
    $$("[data-tema]").forEach((li) => (li.onclick = () => ir("tema/" + li.dataset.tema)));
    $$("[data-prueba]").forEach((b) => (b.onclick = (e) => { e.preventDefault(); pruebaNivel(b.dataset.prueba); }));
    montarDominio(o); montarRutaViva($("#rutaVivaMeta"), { objetivo: o.id });
    $("#pausar").onclick = async () => { await api("objetivos/estado", { id: o.id, estado: o.estado === "activo" ? "pausado" : "activo" }); enrutar(); };
    $("#borrarO").onclick = async () => { if (confirm("¿Borrar este objetivo?")) { await api("objetivos/estado", { id: o.id, estado: "borrar" }); ir("objetivos"); } };
    return;
  }
  vista.innerHTML = `<h1>🎯 Objetivos y nuevas áreas</h1>
    <div class="chips" style="margin-bottom:.6rem"><button class="chip activo" data-tipo="obj">🎯 Objetivo concreto</button><button class="chip" data-tipo="area">📚 Área o carrera completa</button></div>
    <div class="tarjeta" id="cajaArea" hidden><b>Nueva área completa</b><p class="suave peq" style="margin:.2rem 0 0">Para una disciplina entera que quieres dominar como las demás (por ejemplo «Ingeniería eléctrica», «Diseño industrial», «Economía»).
      La IA arma su currículo de Fundamentos a Horizonte (8-14 módulos), lo enlaza con los prerrequisitos que ya tienes y busca recursos confiables. Aparece en la Ruta y en Ajustes (prioridad) como cualquier área. Tarda unos 5-8 min.</p>
      <label>Nombre del área</label><input type="text" id="aNom" placeholder="Ej.: Ingeniería eléctrica">
      <label>Enfoque (opcional)</label><textarea id="aDes" placeholder="Qué te interesa de esta área, para qué la quieres…"></textarea>
      <div class="fila" style="margin-top:.6rem"><button class="btn pri" id="aCrear">Crear área</button><span id="aEstado" class="suave peq"></span></div></div>
    <div class="tarjeta" id="cajaObj"><b>Nuevo objetivo</b><p class="suave peq" style="margin:.2rem 0 0">Para una meta concreta (un proyecto, un examen, una habilidad). Si es una disciplina entera, usa «📚 Área o carrera completa».
      Escribe lo que quieres lograr. La IA arma la ruta completa —de lo más básico a la frontera— usando tu currículo, agrega módulos propios para lo que falte y un proyecto final. Verás qué requisitos ya cumples y cuáles faltan.</p>
      <label>¿Qué quieres lograr?</label><input type="text" id="oTit" placeholder="Ej.: Diseñar y programar un brazo robótico de 6 ejes con visión">
      <label>Detalles (opcional)</label><textarea id="oDes" placeholder="Para qué, qué ya sabes, hasta dónde quieres llegar (aplicarlo, leer papers, ir a conferencias…)"></textarea>
      <label>¿En cuánto tiempo?</label><select id="oPlazo"><option value="0">Sin plazo</option>${PLAZOS.map(([s, t]) => `<option value="${s}" ${s === 8 ? "selected" : ""}>${t}</option>`).join("")}</select>
      <p class="suave peq" style="margin:.3rem 0 0">Con plazo, sus temas van primero y ves si vas a tiempo. Después de la ruta, la IA mapea la <b>frontera</b> (investigación actual, problemas abiertos, papers y conferencias) y la renueva cada mes.</p>
      <div class="fila" style="margin-top:.6rem"><button class="btn pri" id="oCrear">Crear ruta</button><span id="oEstado" class="suave peq"></span></div></div>
    <div class="chips" style="margin:.4rem 0">${["Construir un robot móvil autónomo con ROS 2", "Pasar el HSK 4", "Invertir mis ahorros con criterio", "Crear y administrar mi empresa de tecnología", "Entender y entrenar modelos de IA", "Trabajar como ingeniero en Alemania"].map((s) => `<button class="chip" data-sug="${esc(s)}">${esc(s)}</button>`).join("")}</div>
    ${d.pendientes.map((p) => `<div class="tarjeta"><span class="cargando"></span> ${p.tipo === "area" ? "Creando el área" : "Diseñando"} «${esc(p.etiqueta)}»… ${esc(textoEstado(p))}</div>`).join("")}
    ${d.objetivos.map((o) => `<div class="tarjeta" style="cursor:pointer" onclick="ir('objetivos/${o.id}')">
      <div class="fila entre"><b>${o.estado !== "activo" ? "⏸ " : ""}${esc(o.titulo)}</b><span>${Math.round(o.progreso * 100)}%</span></div>
      <div class="barra-prog" style="margin:.4rem 0"><i style="width:${o.progreso * 100}%"></i></div>
      <div class="suave peq">${o.pasos.filter((p) => p.estado === "completo").length} de ${o.pasos.length} módulos completos · ${o.temas_total - o.temas_hechos} temas por aprender</div></div>`).join("") || (d.pendientes.length ? "" : `<p class="vacio">Aún no tienes objetivos.</p>`)}`;
  $$("[data-sug]").forEach((b) => (b.onclick = () => ($("#oTit").value = b.dataset.sug)));
  $$("[data-tipo]").forEach((b) => (b.onclick = () => {
    $$("[data-tipo]").forEach((x) => x.classList.toggle("activo", x === b));
    $("#cajaArea").hidden = b.dataset.tipo !== "area"; $("#cajaObj").hidden = b.dataset.tipo === "area";
  }));
  $("#aCrear").onclick = async () => {
    const nombre = $("#aNom").value.trim(); if (!nombre) return aviso("Escribe el nombre del área");
    $("#aCrear").disabled = true;
    try {
      const j = await api("area/nueva", { nombre, descripcion: $("#aDes").value });
      const r = await esperarTrabajo(j.trabajo, (t) => { const e = $("#aEstado"); if (e) e.innerHTML = `<span class="cargando"></span> ${esc(textoEstado(t))}`; });
      E.mapa = null; aviso("📚 Área creada"); ir("ruta/" + r.area);
    } catch (e) { $("#aEstado").textContent = "Error: " + e.message; $("#aCrear").disabled = false; }
  };
  if (d.pendientes.length) setTimeout(() => location.hash.startsWith("#/objetivos") && !location.hash.includes("/objetivos/") && refrescar(), 5000);
  $("#oCrear").onclick = async () => {
    const titulo = $("#oTit").value.trim(); if (!titulo) return aviso("Escribe el objetivo");
    $("#oCrear").disabled = true;
    try {
      const j = await api("objetivos", { titulo, descripcion: $("#oDes").value, semanas: +$("#oPlazo").value });
      const r = await esperarTrabajo(j.trabajo, (t) => { const e = $("#oEstado"); if (e) e.innerHTML = `<span class="cargando"></span> ${esc(textoEstado(t))} (1-3 min)`; });
      ir("objetivos/" + r.objetivo);
    } catch (e) { $("#oEstado").textContent = "Error: " + e.message; $("#oCrear").disabled = false; }
  };
};

/* ---------- fuentes verificadas y comparador (2026-10-27) ---------- */
const NIV_FIAB = { 4: ["🏛️", "bien"], 3: ["📚", "bien"], 2: ["🌐", ""], 1: ["⚠️", "mal"], 0: ["⛔", "mal"] };
const fiab = (f) => f && f.fiabilidad ? `<span class="etq ${NIV_FIAB[f.fiabilidad.nivel][1]}" title="${esc(f.fiabilidad.tipo)} · fiabilidad ${f.fiabilidad.nivel}/4">${NIV_FIAB[f.fiabilidad.nivel][0]} ${esc(f.fiabilidad.tipo)}</span>` : "";
const VERED = { "confirmada": ["🟢", "bien"], "confirmada con matices": ["🟡", "medio"], "en disputa": ["🟠", "medio"], "contradicha": ["🔴", "mal"], "sin evidencia": ["⚪", ""] };
function htmlVerificacion(r) {
  const F = r.fuentes || [];
  const chip = (i) => F[i] ? `<a class="chip peq" href="${escUrl(F[i].url)}" target="_blank" rel="noopener" title="${esc(F[i].titulo)}">${NIV_FIAB[F[i].fiabilidad.nivel][0]} ${esc(F[i].fiabilidad.dominio)}</a>` : "";
  const res = r.resumen || {};
  return `<div class="fila" style="flex-wrap:wrap;gap:.3rem;margin:.3rem 0">${Object.entries(VERED).filter(([k]) => res[k]).map(([k, [ic, cl]]) => `<span class="etq ${cl}">${ic} ${res[k]} ${esc(k)}</span>`).join("")}</div>
    <ul class="afirmaciones">${r.resultados.map((x) => `<li><span class="etq ${VERED[x.veredicto][1]}">${VERED[x.veredicto][0]} ${esc(x.veredicto)}</span> <span class="etq" title="Según cuántas fuentes la respaldan y su fiabilidad">confianza ${esc(x.confianza)}</span> ${esc(x.afirmacion)}
      ${x.matiz ? `<div class="suave peq" style="margin-top:.2rem">${esc(x.matiz)}</div>` : ""}
      <div style="margin-top:.2rem">${x.apoyan.length ? `<span class="peq">apoyan:</span> ${x.apoyan.map(chip).join(" ")}` : ""} ${x.contradicen.length ? `<span class="peq" style="color:var(--mal)">contradicen:</span> ${x.contradicen.map(chip).join(" ")}` : ""}</div></li>`).join("")}</ul>
    ${r.diferencias.length ? `<h3>⚖️ En qué difieren las fuentes</h3><ul>${r.diferencias.map((x) => `<li><b>${esc(x.aspecto)}:</b> ${esc(x.detalle)} ${x.fuentes.map(chip).join(" ")}</li>`).join("")}</ul>` : ""}
    <p><b>Conclusión:</b> ${esc(r.conclusion)}</p>
    <details><summary class="suave peq">Fuentes consultadas (${F.length})</summary><ol class="peq">${F.map((f) => `<li>${fiab(f)} <a href="${escUrl(f.url)}" target="_blank" rel="noopener">${esc(f.titulo)}</a>${f.leido ? "" : " <span class='suave'>(solo resumen)</span>"}</li>`).join("")}</ol></details>
    <p class="suave peq">Verificado el ${new Date(r.creado * 1000).toLocaleString(LOC)}. 🏛️ académica u oficial · 📚 referencia, medio de calidad o verificador · 🌐 general · ⚠️ baja. La fiabilidad es del tipo de fuente: abre el original si algo importa.</p>`;
}
VISTAS.verificar = async (_, q) => {
  const d = await api("verificar" + (q.clave ? "?clave=" + encodeURIComponent(q.clave) : ""));
  if (q.clave) {
    if (d.error) throw new Error(d.error);
    vista.innerHTML = `<button class="btn fantasma peq" onclick="ir('verificar')">← Verificar</button><h1>🔎 ${esc((d.pregunta || "").slice(0, 120))}</h1><div class="tarjeta">${htmlVerificacion(d)}</div>`;
    return;
  }
  vista.innerHTML = `<h1>🔎 Verificar</h1>
    <p class="suave">Pega una afirmación, un dato o una pregunta («¿es cierto que…?»). La Academia busca a fondo en fuentes verificadas (académicas, oficiales, de referencia y verificadores de datos, en español e inglés), las lee y te muestra qué está confirmado, qué está en disputa y en qué difieren las fuentes.</p>
    <div class="tarjeta"><textarea id="vfTexto" placeholder="Ej.: «La relatividad general predice que el tiempo pasa más lento cerca de una masa grande» o «¿Es cierto que solo usamos el 10 % del cerebro?»"></textarea>
      <div class="fila" style="margin-top:.5rem"><button class="btn pri" id="vfBtn">🔎 Verificar (3-8 min)</button><span id="vfEstado" class="suave peq"></span></div></div>
    ${d.pendientes.map((p) => `<div class="tarjeta"><span class="cargando"></span> ${esc(textoEstado(p))}</div>`).join("")}
    ${d.historial.length ? `<h2>Tus verificaciones</h2>${d.historial.map((h) => `<div class="tarjeta" style="cursor:pointer" onclick="ir('verificar?clave=${encodeURIComponent(h.clave)}')"><b>${esc(h.titulo)}</b>
      <div class="fila" style="gap:.3rem;margin-top:.3rem">${Object.entries(VERED).filter(([k]) => h.resumen && h.resumen[k]).map(([k, [ic]]) => `<span class="etq">${ic} ${h.resumen[k]}</span>`).join("")}<span class="suave peq">${new Date(h.creada * 1000).toLocaleDateString(LOC)}</span></div></div>`).join("")}` : ""}`;
  if (d.pendientes.length) setTimeout(() => location.hash === "#/verificar" && refrescar(), 10000);
  $("#vfBtn").onclick = async () => {
    const texto = $("#vfTexto").value.trim(); if (texto.length < 10) return aviso("Escribe la afirmación o la pregunta");
    $("#vfBtn").disabled = true;
    try {
      const j = await api("verificar", { texto });
      const r = await esperarTrabajo(j.trabajo, (t) => ($("#vfEstado").innerHTML = `<span class="cargando"></span> ${esc(textoEstado(t))}`));
      vista.insertAdjacentHTML("beforeend", `<div class="tarjeta">${htmlVerificacion(r)}</div>`); $("#vfBtn").disabled = false; $("#vfEstado").textContent = "";
    } catch (e) { $("#vfEstado").textContent = "Error: " + e.message; $("#vfBtn").disabled = false; }
  };
};
function montarVerificacionLeccion(d) {
  const c = $("#verifLeccion"); if (!c) return;
  if (d.verificacion) {
    c.innerHTML = `<details class="tarjeta"${(d.verificacion.resumen["contradicha"] || d.verificacion.resumen["en disputa"]) ? " open" : ""}><summary><b>🔎 Fuentes contrastadas</b> <span class="suave peq">qué dicen otras fuentes verificadas de lo que afirma esta lección</span></summary>${htmlVerificacion(d.verificacion)}
      <button class="btn peq fantasma" id="verifOtra">🔄 Verificar de nuevo</button></details>`;
  } else if (d.verificando) {
    c.innerHTML = `<div class="tarjeta"><b>🔎 Fuentes contrastadas</b> <span class="etq medio"><span class="cargando"></span> en cola o verificando</span><p class="suave peq" style="margin:.3rem 0 0">La IA extrae las afirmaciones clave de la lección y las contrasta con fuentes académicas, oficiales y de referencia.</p></div>`;
    return;
  } else {
    c.innerHTML = `<div class="tarjeta"><b>🔎 ¿Es todo cierto?</b><p class="suave peq" style="margin:.3rem 0">La IA extrae las afirmaciones clave de la lección (hechos, cifras, definiciones, atribuciones) y las contrasta con fuentes verificadas: qué está confirmado, qué tiene matices, qué está en disputa y en qué difieren las fuentes.</p><button class="btn peq" id="verifOtra">🔎 Contrastar con fuentes (3-8 min)</button></div>`;
  }
  const b = $("#verifOtra"); if (b) b.onclick = async () => {
    b.disabled = true; b.innerHTML = `<span class="cargando"></span> En cola…`;
    try { const j = await api("verificar/leccion", { tema: d.tema.id }); const r = await esperarTrabajo(j.trabajo, (t) => (b.innerHTML = `<span class="cargando"></span> ${esc(textoEstado(t))}`)); d.verificacion = r; d.verificando = false; montarVerificacionLeccion(d); }
    catch (e) { b.textContent = "Error: " + e.message; }
  };
}

/* ---------- fuentes aportadas (2026-10-29): el texto de una página que bloquea a las IA, pegado por la persona ---------- */
async function montarAportadas(d) {
  const base = $("#verifLeccion"); if (!base) return;
  let c = $("#aportadas");
  if (!c) { base.insertAdjacentHTML("afterend", `<div id="aportadas"></div>`); c = $("#aportadas"); }
  const lista = (await api("aportadas?tema=" + encodeURIComponent(d.tema.id)).catch(() => ({ aportadas: [] }))).aportadas;
  const ver = (a) => {
    const r = a.analisis; if (!r) return `<span class="suave peq">sin analizar</span>`;
    const ap = r.aportada || {}, res = r.resumen || {};
    const malas = (r.resultados || []).filter((x) => ["contradicha", "en disputa"].includes(x.veredicto));
    return `<p class="peq" style="margin:.3rem 0">${esc(ap.resumen || "")}</p>
      <p class="peq suave" style="margin:.2rem 0">Contraste con otras fuentes: ✅ ${(res["confirmada"] || 0) + (res["confirmada con matices"] || 0)} confirmadas · ⚖️ ${res["en disputa"] || 0} en disputa · ❌ ${res["contradicha"] || 0} contradichas · ❔ ${res["sin evidencia"] || 0} sin evidencia</p>
      ${malas.length ? `<ul class="peq">${malas.map((x) => `<li><b>${esc(x.veredicto)}:</b> ${esc(x.afirmacion)}<br><span class="suave">${esc(x.matiz || "")}</span></li>`).join("")}</ul>` : ""}
      ${(ap.referencias || []).length ? `<details><summary class="peq">📚 Referencias que cita (${ap.referencias.length})</summary><ul class="peq">${ap.referencias.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></details>` : ""}
      ${(ap.enlaces || []).length ? `<details><summary class="peq">🔗 Enlaces del texto (${ap.enlaces.length})</summary><ul class="peq">${ap.enlaces.map((x) => `<li><a href="${escUrl(x)}" target="_blank" rel="noopener">${esc(x)}</a></li>`).join("")}</ul></details>` : ""}`;
  };
  c.innerHTML = `<details class="tarjeta"${lista.length ? " open" : ""}><summary><b>📎 Aportar una fuente</b> <span class="suave peq">${lista.length ? lista.length + " aportada(s)" : "¿una página bloquea a las IA? pega su texto"}</span></summary>
    <p class="suave peq" style="margin:.4rem 0">Abre la página en tu navegador, usa el <b>modo lector</b> (o una extensión como MarkDownload), copia el texto y pégalo aquí. La Academia lo resume, saca las referencias que cita y contrasta sus afirmaciones con otras fuentes. Además, al escribir o reescribir esta lección entra como la primera fuente. El análisis se hace en tu equipo.</p>
    <input type="text" id="apTit" placeholder="Título (opcional)"><input type="text" id="apUrl" placeholder="Dirección de la página (opcional)">
    <textarea id="apTxt" rows="7" placeholder="Pega aquí el texto de la página (mínimo 200 caracteres)"></textarea>
    <div class="fila"><button class="btn pri" id="apEnviar">📎 Guardar y analizar</button><span id="apEstado" class="suave peq"></span></div>
    ${lista.map((a) => `<div class="tarjeta" style="margin-top:.6rem"><div class="fila entre"><b>${esc(a.titulo)}</b><button class="btn peq fantasma" data-ap-borrar="${esc(a.id)}">🗑️</button></div>
      <span class="suave peq">${a.caracteres.toLocaleString(LOC)} caracteres${a.url ? " · " + esc(a.url) : ""}</span>${ver(a)}</div>`).join("")}</details>`;
  $("#apEnviar").onclick = async () => {
    const b = $("#apEnviar"), st = $("#apEstado"); b.disabled = true; st.innerHTML = `<span class="cargando"></span> Guardando…`;
    try {
      const j = await api("aportada", { tema: d.tema.id, titulo: $("#apTit").value, url: $("#apUrl").value, texto: $("#apTxt").value });
      await esperarTrabajo(j.trabajo, (t) => (st.innerHTML = `<span class="cargando"></span> ${esc(textoEstado(t))}`));
      montarAportadas(d);
    } catch (e) { st.textContent = "❌ " + e.message; b.disabled = false; }
  };
  $$("[data-ap-borrar]").forEach((b) => (b.onclick = async () => { await api("aportada/borrar", { id: b.dataset.apBorrar }); montarAportadas(d); }));
}

/* ---------- rutas vivas (2026-10-27): preparar toda la ruta y actualizarla ---------- */
async function montarRutaViva(cont, params) {
  if (!cont) return;
  const qs = new URLSearchParams(params).toString();
  const e = await api("ruta/estado?" + qs).catch(() => null);
  if (!e || e.error) { cont.innerHTML = ""; return; }
  const r = e.revision;
  cont.innerHTML = `<div class="tarjeta"><div class="fila entre"><b>🔄 Ruta viva</b><span class="suave peq">${e.listas}/${e.pendientes} lecciones listas${e.en_cola ? ` · ⏳ ${e.en_cola} en cola` : ""}</span></div>
    <p class="suave peq" style="margin:.3rem 0">Cada día se renueva el nivel profesional que pide el mercado${params.objetivo ? " (en las metas, el mapa de la frontera)" : ""} y se revisa la ruta: lo que falta se agrega solo y se preparan sus lecciones.
      ${r ? `Última revisión: ${new Date(r.fecha * 1000).toLocaleDateString(LOC)}.` : "Aún no se ha revisado."}${e.mercado_fecha ? ` Mercado: ${new Date(e.mercado_fecha * 1000).toLocaleDateString(LOC)}.` : ""}</p>
    ${r ? `<details${r.agregados.length ? " open" : ""}><summary class="peq"><b>Qué cambió</b>${r.agregados.length ? ` · ➕ ${r.agregados.length}` : ""}${r.en_declive.length ? ` · 📉 ${r.en_declive.length}` : ""}</summary>
      <p class="peq">${esc(r.resumen)}</p>
      ${r.agregados.length ? `<ul class="peq">${r.agregados.map((x) => `<li>${x.tipo === "modulo" ? "🆕 módulo" : "➕"} <b>${esc(x.t)}</b> en ${esc(x.modulo)}${x.ids && x.ids[0] ? ` · <a href="#/tema/${esc(x.ids[0])}">abrir</a>` : ""}<br><span class="suave">${esc(x.por_que)}</span></li>`).join("")}</ul>` : ""}
      ${r.en_declive.length ? `<p class="peq"><b>📉 Pesan menos hoy</b> (no se borran):</p><ul class="peq">${r.en_declive.map((x) => `<li>${esc(x.tema)} — <span class="suave">${esc(x.por_que)}</span></li>`).join("")}</ul>` : ""}</details>` : ""}
    <div class="fila" style="margin-top:.5rem">
      <button class="btn peq ${e.preparar ? "" : "pri"}" data-rv="preparar">📥 ${e.preparar ? "Preparando toda la ruta (re-encolar)" : "Preparar toda la ruta"}</button>
      ${e.trabajo ? `<span class="etq medio"><span class="cargando"></span> ${esc(textoEstado(e.trabajo))}</span>` : `<button class="btn peq" data-rv="actualizar">🔄 Actualizar ahora (mercado + revisión + lo que falte)</button>`}</div></div>`;
  $$("[data-rv]", cont).forEach((b) => (b.onclick = async (ev) => {
    ev.preventDefault(); b.disabled = true;
    if (b.dataset.rv === "preparar") {
      const x = await api("ruta/preparar", params);
      aviso(x.encoladas ? `📥 ${x.encoladas} lecciones en cola (de fondo, detrás de lo diario). Queda recordado: si algo se corta, se re-encola cada día.` : "Todas las lecciones de la ruta ya están listas o en cola");
    } else {
      const j = await api("ruta/actualizar", params);
      aviso("🔄 Actualizando la ruta (varios minutos); puedes seguir");
      esperarTrabajo(j.trabajo, () => {}).then(() => { aviso("✅ Ruta actualizada"); if (document.body.contains(cont)) montarRutaViva(cont, params); }).catch((er) => aviso("Error: " + er.message));
    }
    montarRutaViva(cont, params);
  }));
}

/* ---------- 🌳 sub-ramas y 🚀 laboratorio de innovación (2026-10-27) ---------- */
const IMP = { esencial: ["🔴", "mal"], importante: ["🟡", "medio"], complementaria: ["⚪", ""] };
function htmlRamas(d) {
  const R = d.ramas, t = (d.trabajos || {}).ramas;
  if (!R) return `<p class="suave peq">Aún no hay mapa. La IA arma el árbol completo de la meta (sub-ramas del campo, de campos vecinos y los fundamentos que de verdad se usan), marca lo esencial y agrega a tu ruta lo que falte para que no quede ningún hueco.</p>
    ${t ? `<p><span class="cargando"></span> ${esc(textoEstado(t))}</p>` : `<button class="btn pri peq" data-lab="ramas">🌳 Mapear las sub-ramas</button>`}`;
  const cub = R.ramas.filter((x) => x.importancia !== "complementaria");
  const prom = cub.length ? cub.reduce((s, x) => s + (x.dominio || 0), 0) / cub.length : 0;
  return `<div class="suave peq">${R.ramas.length} sub-ramas · dominio medio de lo esencial e importante: <b>${Math.round(prom * 100)} %</b>${R.fecha ? ` · mapa del ${new Date(R.fecha * 1000).toLocaleDateString(LOC)}` : ""}${t ? ` · <span class="cargando"></span> actualizando` : ` · <a href="javascript:void 0" data-lab="ramas">🔄 rehacer el mapa</a>`}</div>
    ${R.ramas.map((x) => `<details class="peq" style="margin:.35rem 0"><summary><span class="etq ${IMP[x.importancia][1]}">${IMP[x.importancia][0]} ${esc(x.importancia)}</span> <b>${esc(x.nombre)}</b> · nivel ${x.nivel} ${x.dominio != null ? `<span class="etq ${x.dominio >= 0.8 ? "bien" : ""}">${Math.round(x.dominio * 100)} %</span>` : `<span class="etq mal">sin cubrir</span>`}</summary>
      <div style="margin:.3rem 0 .3rem 1rem">${esc(x.por_que)}<br><span class="suave">Temas clave: ${x.temas_clave.map(esc).join(" · ")}</span><br>${x.modulos.map((m) => m.primero ? `<a href="#/tema/${esc(m.primero)}">${esc(m.t)}</a>` : esc(m.t)).join(" · ")}</div></details>`).join("")}`;
}
const NOV = (n) => n == null ? `<span class="etq">novedad sin datos</span>` : `<span class="etq ${n >= 4 ? "bien" : n >= 3 ? "medio" : "mal"}" title="Frente a trabajos publicados parecidos (OpenAlex)">novedad ${n}/5</span>`;
function htmlNovedad(nv) {
  if (!nv) return "";
  return `<details class="peq"><summary>${NOV(nv.novedad)} <b>Comparada con lo publicado</b></summary><p>${esc(nv.diferencia)}</p>${nv.como_hacerla_mas_nueva ? `<p>🚀 <b>Para que sea más nueva:</b> ${esc(nv.como_hacerla_mas_nueva)}</p>` : ""}
    ${(nv.trabajos || []).length ? `<ol>${nv.trabajos.map((p, i) => `<li${(nv.mas_parecidos || []).includes(i + 1) ? ` style="font-weight:700"` : ""}><a href="${escUrl(p.url)}" target="_blank" rel="noopener">${esc(p.titulo)}</a> (${p.anio}, ${p.citas} citas)${(nv.mas_parecidos || []).includes(i + 1) ? " · el más parecido" : ""}</li>`).join("")}</ol>` : ""}</details>`;
}
function htmlIdea(x) {
  const i = x.datos, pr = x.presentacion, rv = x.revision;
  return `<details class="tarjeta" style="margin:.5rem 0${x.elegida ? ";border-color:var(--acento)" : ""}"${x.elegida ? " open" : ""}><summary>${x.elegida ? "⭐ " : ""}<b>${esc(i.titulo)}</b> ${NOV(x.novedad && x.novedad.novedad)}</summary>
    <div class="peq"><p><b>Problema:</b> ${esc(i.problema)}</p><p><b>La idea:</b> ${esc(i.idea)}</p><p><b>Por qué sería nueva:</b> ${esc(i.por_que_nueva)}</p>
      <p><b>Cruce de áreas:</b> ${esc(i.cruce)}</p><p><b>Cómo probarla:</b> ${esc(i.como_probarla)}</p><p><b>Riesgo:</b> ${esc(i.riesgo)}</p>
      ${i.modulos.length ? `<p><b>Ruta crítica (lo que necesitas):</b> ${i.modulos.map((r) => esc(nombreModulo(r))).join(" · ")}</p>` : ""}
      ${htmlNovedad(x.novedad)}</div>
    <div class="fila" style="margin-top:.4rem">${x.elegida ? `<span class="etq bien">⭐ tu proyecto: su ruta crítica va primero</span>` : `<button class="btn peq pri" data-elegir="${x.id}">⭐ Elegir como mi proyecto</button>`}
      <button class="btn peq" data-pres="${x.id}">🎤 ${pr ? "Rehacer" : "Preparar"} la presentación</button><button class="btn peq" data-pares="${x.id}">🧑‍⚖️ ${rv ? "Otra" : ""} revisión de pares</button></div>
    ${pr ? `<details class="peq" style="margin-top:.5rem"><summary><b>🎤 Presentación: ${esc(pr.titulo)}</b></summary>
      <p><b>Resumen</b></p><p>${esc(pr.resumen)}</p><p><b>Estructura</b></p><ol>${pr.estructura.map((e) => `<li><b>${esc(e.seccion)}:</b> ${esc(e.contenido)}</li>`).join("")}</ol>
      <details><summary><b>Guion de 10 minutos</b></summary><div class="leccion" data-md-idea="${esc(pr.guion_10min)}"></div></details>
      <p><b>❓ Preguntas difíciles del público</b></p><ul>${pr.preguntas_dificiles.map((q) => `<li><b>${esc(q.pregunta)}</b><br>${esc(q.como_responder)}</li>`).join("")}</ul>
      <p><b>📅 Plan de validación</b></p><ul>${pr.plan_validacion.map((v) => `<li>Semana ${v.semana}: ${esc(v.tarea)} → <i>${esc(v.entregable)}</i></li>`).join("")}</ul>
      ${pr.que_dominar.length ? `<p><b>📚 Domina a fondo antes de presentar:</b> ${pr.que_dominar.map(esc).join(" · ")}</p>` : ""}</details>` : ""}
    ${rv ? `<details class="peq" style="margin-top:.5rem"><summary><b>🧑‍⚖️ Revisión de pares</b> ${rv.revisores.map((r) => `<span class="etq">${r.puntaje}/10</span>`).join(" ")}</summary>
      ${rv.revisores.map((r) => `<p><b>${esc(r.perfil)}</b> · ${r.puntaje}/10 · <i>${esc(r.veredicto)}</i><br>✅ ${esc(r.fortalezas)}<br>❌ ${esc(r.debilidades)}<br>👉 ${esc(r.pide)}</p>`).join("")}
      <p><b>Cambios prioritarios:</b></p><ol>${rv.cambios_prioritarios.map((c) => `<li>${esc(c)}</li>`).join("")}</ol></details>` : ""}</details>`;
}
function htmlLab(d, f) {
  const t = (d.trabajos || {}).ideas;
  return `<p class="suave peq">La meta final: presentar algo lo más innovador posible. La IA propone ideas que atacan los problemas abiertos de la frontera y las cruza con lo que ya sabes; cada una se <b>compara con trabajos publicados reales</b> para medir su novedad. Elige tu proyecto (su ruta crítica pasa primero), prepara la presentación y somételo a una revisión de pares simulada.</p>
    ${!f ? `<p class="peq">Primero hace falta el mapa de la 🔭 frontera.</p>` : t ? `<p><span class="cargando"></span> ${esc(textoEstado(t))} (10-25 min: genera y busca trabajos parecidos para cada idea)</p>`
      : `<div class="fila"><input type="text" id="labEnfoque" placeholder="(Opcional) enfoque: «algo con hardware barato», «aplicado a Colombia»…" style="flex:1"><button class="btn pri" data-lab="ideas">🚀 ${d.ideas.length ? "Más ideas" : "Generar ideas"}</button></div>`}
    ${d.ideas.map(htmlIdea).join("")}`;
}
function montarLab(o, caja, recargar) {
  $$("[data-lab]", caja).forEach((b) => (b.onclick = async (e) => {
    e.preventDefault();
    const que = b.dataset.lab;
    const j = await api(que, { objetivo: o.id, enfoque: que === "ideas" && $("#labEnfoque") ? $("#labEnfoque").value : "" });
    if (j.error) return aviso(j.error);
    aviso(que === "ramas" ? "🌳 Mapeando sub-ramas (5-10 min); puedes seguir" : "🚀 Generando ideas y chequeando su novedad (10-25 min); puedes seguir");
    recargar(); esperarTrabajo(j.trabajo, () => {}).then(recargar).catch((er) => aviso("Error: " + er.message));
  }));
  $$("[data-elegir]", caja).forEach((b) => (b.onclick = async () => { await api("idea/elegir", { idea: +b.dataset.elegir }); aviso("⭐ Proyecto elegido: su ruta crítica va primero en tu plan"); recargar(); }));
  const tarea = (ruta, msg) => async (ev) => {
    const b = ev.currentTarget; b.disabled = true; b.innerHTML = `<span class="cargando"></span> ${msg}`;
    try { const j = await api(ruta, { idea: +b.dataset.pres || +b.dataset.pares }); await esperarTrabajo(j.trabajo, (t) => (b.innerHTML = `<span class="cargando"></span> ${esc(textoEstado(t))}`)); recargar(); }
    catch (er) { b.textContent = "Error: " + er.message; }
  };
  $$("[data-pres]", caja).forEach((b) => (b.onclick = tarea("idea/presentacion", "Preparando (3-8 min)…")));
  $$("[data-pares]", caja).forEach((b) => (b.onclick = tarea("idea/pares", "Revisando (2-5 min)…")));
  $$("[data-md-idea]", caja).forEach((el) => pintarMd(el, el.dataset.mdIdea));
}

/* =============================== PROGRAMA DE DOMINIO (2026-10-27) ===============================
   Una meta termina cuando puedes aplicar, leer la investigación de hoy, seguir una conferencia y proponer algo
   propio: plan con plazo, frontera viva (se renueva cada mes), lectura guiada de papers y tu aporte. */
const fechaCorta = (t) => new Date(t * 1000).toLocaleDateString(LOC, { day: "numeric", month: "short" });
const PLAZOS = [[2, "2 semanas"], [4, "1 mes"], [8, "2 meses"], [13, "3 meses"], [26, "6 meses"], [52, "1 año"]];
// [P3], [P7, P11] y [W2] → enlaces a cada fuente
const refFrontera = (f, k, n) => (k === "P" ? (f.papers || [])[n - 1] : (f.web || [])[n - 1]);
const conRefs = (t, f) => esc(t).replace(/\[((?:[PW]\d+(?:,\s*)?)+)\]/g, (m, lista) => "[" + lista.split(/,\s*/).map((r) => {
  const x = refFrontera(f, r[0], +r.slice(1));
  return x ? `<a href="${escUrl(x.url)}" target="_blank" rel="noopener" title="${esc(x.titulo)}">${r}</a>` : r;
}).join(", ") + "]");
async function montarDominio(o) {
  const caja = $("#dominioCaja"); if (!caja) return;
  const d = await api("dominio?objetivo=" + o.id);
  if (d.error) { caja.innerHTML = ""; return; }
  const P = d.programa, prog = P.programa, f = d.frontera;
  const estadoProg = !prog ? `<p class="suave peq" style="margin:.3rem 0">Sin plazo, a tu meta diaria te tomaría ~${plazo(P.dias_a_tu_meta)}${P.dias_a_tu_ritmo ? ` (a tu ritmo real, ~${plazo(P.dias_a_tu_ritmo)})` : ""}: ${P.faltan} temas, ~${P.horas} h de estudio. Ponle fecha y la Academia lo prioriza y te dice si vas a tiempo.</p>
      <div class="fila"><select id="plazoSel" style="width:auto">${PLAZOS.map(([s, t]) => `<option value="${s}" ${s === 8 ? "selected" : ""}>${t}</option>`).join("")}</select><button class="btn pri" id="plazoPoner">📅 Ponerle plazo</button></div>`
    : `<div class="stats" style="margin:.4rem 0">
        <div class="stat"><b>${P.dias_restantes}</b><span>días restantes (hasta ${fechaCorta(P.fin)})</span></div>
        <div class="stat"><b>${P.faltan}</b><span>temas por dominar (~${P.horas} h)</span></div>
        <div class="stat"><b style="color:var(--${P.viable_meta ? "bien" : "mal"})">${P.min_dia_necesarios}</b><span>min/día necesarios (tu meta: ${Math.round(P.minutos_meta)})</span></div>
        <div class="stat"><b style="color:var(--${P.diferencia >= 0 ? "bien" : "mal"})">${P.diferencia >= 0 ? "+" : ""}${P.diferencia}</b><span>temas ${P.diferencia >= 0 ? "adelantado" : "atrasado"}</span></div></div>
      ${!P.viable_meta ? `<p class="peq" style="color:var(--mal)">Con ${Math.round(P.minutos_meta)} min/día no alcanza: sube los minutos, alarga el plazo o usa ⚡ «Ya lo sé» en los módulos que domines.</p>` : !P.viable_real && P.ritmo.min_dia_real ? `<p class="peq" style="color:var(--medio)">Cabe en tu meta diaria, pero a tu ritmo real (${P.ritmo.min_dia_real} min/día) no llegas: lo que decide es estudiar los días que planeaste.</p>` : ""}
      <details><summary class="peq"><b>Hitos semana a semana</b></summary>${P.hitos.map((h) => `<div class="peq" style="margin:.4rem 0"><b>Semana ${h.semana}</b> (desde ${fechaCorta(h.desde)}) · ${h.temas} temas: ${h.modulos.map((m) => `<a href="#/tema/${m.primero}">${esc(m.t)}</a> (${m.temas})`).join(" · ")}</div>`).join("")}</details>
      <div class="fila" style="margin-top:.4rem"><select id="plazoSel" style="width:auto">${PLAZOS.map(([s, t]) => `<option value="${s}" ${s === prog.semanas ? "selected" : ""}>${t}</option>`).join("")}</select><button class="btn peq" id="plazoPoner">Cambiar plazo (empieza hoy)</button><button class="btn peq fantasma" id="plazoQuitar">Quitar plazo</button></div>`;
  const fr = !f ? (d.frontera_trabajo ? `<p><span class="cargando"></span> Mapeando la frontera: ${esc(textoEstado(d.frontera_trabajo))} (5-15 min)</p>`
      : `<p class="suave peq">Aún no hay mapa. La IA busca revisiones recientes, lo más citado de los últimos 2 años y preprints de arXiv (OpenAlex), más problemas abiertos y conferencias en la web, y arma el mapa del estado del arte.</p><button class="btn pri" id="frGen">🔭 Mapear la frontera</button>`)
    : `<div class="suave peq">Mapa v${f.version} del ${fechaCorta(f.creada)} · se renueva solo cada 30 días ${d.frontera_trabajo ? `· <span class="cargando"></span> actualizando…` : `· <a href="javascript:void 0" id="frGen">🔄 actualizar ahora</a>`}</div>
      ${f.que_cambio ? `<div class="tarjeta" style="border-color:var(--medio);margin:.5rem 0"><b>🆕 Qué cambió desde el mapa anterior</b><p class="peq" style="margin:.3rem 0 0">${conRefs(f.que_cambio, f)}</p></div>` : ""}
      ${(f.temas_agregados || []).length ? `<p class="peq">➕ Temas nuevos agregados a tu ruta (módulo «🔭 Frontera viva»): ${f.temas_agregados.map(esc).join(" · ")}</p>` : ""}
      <details open><summary><b>🧭 Estado del arte</b></summary><div class="leccion peq" id="frEstado"></div></details>
      <details><summary><b>🧪 Líneas de investigación activas (${f.lineas.length})</b></summary>${f.lineas.map((l) => `<div class="peq" style="margin:.5rem 0"><b>${esc(l.nombre)}</b> <span class="etq ${l.madurez === "emergente" ? "medio" : l.madurez === "en auge" ? "bien" : ""}">${esc(l.madurez)}</span> ${l.refs.map((r) => conRefs(r, f)).join(" ")}<br>${esc(l.que_es)}<br><i>Por qué importa:</i> ${esc(l.por_que_importa)}</div>`).join("")}</details>
      <details><summary><b>❓ Problemas abiertos (${f.problemas_abiertos.length})</b></summary>${f.problemas_abiertos.map((x) => `<div class="peq" style="margin:.5rem 0"><b>${esc(x.problema)}</b> ${x.refs.map((r) => conRefs(r, f)).join(" ")}<br><i>Por qué es difícil:</i> ${esc(x.por_que_es_dificil)}<br><i>Qué haría falta:</i> ${esc(x.que_haria_falta)}</div>`).join("")}</details>
      <details><summary><b>🗣️ Vocabulario de las charlas (${f.vocabulario.length})</b></summary><dl class="peq">${f.vocabulario.map((v) => `<dt><b>${esc(v.termino)}</b></dt><dd style="margin:0 0 .4rem 1rem">${esc(v.significado)}</dd>`).join("")}</dl></details>
      ${f.conferencias.length ? `<details><summary><b>🎤 Conferencias y espacios del tema</b></summary><ul class="peq">${f.conferencias.map((c) => `<li><b>${esc(c.nombre)}</b> ${conRefs(c.ref, f)} — ${esc(c.nota)}</li>`).join("")}</ul></details>` : ""}
      <h3>📄 Papers para leer (en orden)</h3><p class="suave peq">La habilidad de una conferencia es leer investigación. «Lectura guiada»: contexto, requisitos enlazados a tu ruta, glosario y 6 preguntas que la IA corrige. Tú lees el paper.</p>
      ${(f.papers_clave.length ? f.papers_clave : f.papers.slice(0, 6).map((p, i) => ({ p: i + 1, por_que: "" }))).map((k) => { const p = f.papers[k.p - 1]; const hecha = d.lecturas.find((l) => l.openalex === p.openalex);
        return `<div class="tarjeta" style="margin:.4rem 0"><div class="peq"><span class="etq">${esc(p.clase || "")}</span> ${esc(p.autores)} (${p.anio}) · ${p.citas} citas${p.abierto ? ` · <a href="${escUrl(p.abierto)}" target="_blank" rel="noopener">texto libre</a>` : ""}</div>
          <b><a href="${escUrl(p.url)}" target="_blank" rel="noopener">${esc(p.titulo)}</a></b>${k.por_que ? `<div class="suave peq">${esc(k.por_que)}</div>` : ""}
          <div class="fila" style="margin-top:.4rem">${hecha ? `<button class="btn peq" onclick="ir('paper/${hecha.id}')">📄 Seguir la lectura (${hecha.respondidas}/${hecha.total}${hecha.promedio != null ? ` · ${hecha.promedio}/100` : ""})</button>` : `<button class="btn peq pri" data-guia="${k.p}">📄 Lectura guiada</button>`}</div></div>`; }).join("")}
      <details><summary class="suave peq">Todos los papers del mapa (${f.papers.length})</summary><ol class="peq">${f.papers.map((p) => `<li>${esc(p.clase || "")} · <a href="${escUrl(p.url)}" target="_blank" rel="noopener">${esc(p.titulo)}</a> (${p.anio}, ${p.citas} citas)</li>`).join("")}</ol></details>`;
  caja.innerHTML = `<div class="tarjeta"><h2 style="margin-top:0">📅 Plan con plazo</h2>${estadoProg}
      <div class="fila entre" style="margin-top:.6rem;border-top:1px solid var(--borde);padding-top:.6rem"><div class="peq"><b>🎯 Ubícame en esta meta</b><div class="suave">Lo más rápido es no estudiar lo que ya sabes: 4-6 pruebas de nivel en búsqueda binaria por toda la ruta (cada una que pasas da por sabidos sus requisitos).</div></div><button class="btn peq" id="ubMeta">Empezar</button></div></div>
    <div class="tarjeta"><h2 style="margin-top:0">🌳 Sub-ramas que necesitas</h2>${htmlRamas(d)}</div>
    <div class="tarjeta"><h2 style="margin-top:0">🔭 Frontera viva</h2>${fr}</div>
    <div class="tarjeta"><h2 style="margin-top:0">🚀 Laboratorio de innovación</h2>${htmlLab(d, f)}</div>
    <div class="tarjeta"><h2 style="margin-top:0">💡 Tu propia idea</h2><p class="suave peq">¿Se te ocurrió algo? La IA la contrasta con los problemas abiertos, los papers del mapa y una búsqueda de trabajos parecidos (novedad real): originalidad, viabilidad, si ya existe, el siguiente paso y cómo presentarla.</p>
      <textarea id="apTexto" placeholder="Ej.: ¿Se podría usar … para medir … sin …?"></textarea><div class="fila" style="margin-top:.4rem"><button class="btn pri" id="apEnviar">Evaluar mi idea</button><span id="apEstado" class="suave peq"></span></div>
      ${d.aportes.map(htmlAporte).join("")}</div>`;
  montarLab(o, caja, () => { if (location.hash.includes("objetivos/" + o.id)) montarDominio(o); });
  if (f) pintarMd($("#frEstado"), f.estado_del_arte.replace(/\[((?:[PW]\d+(?:,\s*)?)+)\]/g, (m, lista) => "\\[" + lista.split(/,\s*/).map((r) => { const x = refFrontera(f, r[0], +r.slice(1)); return x ? `[${r}](${x.url})` : r; }).join(", ") + "\\]"));
  $("#ubMeta").onclick = () => ubicarme({ id: "obj" + o.id, nombre: o.titulo, modulos: o.pasos.map((p) => ({ ref: p.ref, t: p.t, nivel: p.nivel, dominio: p.dominio })) }, true);
  const plazoPoner = $("#plazoPoner"); if (plazoPoner) plazoPoner.onclick = async () => { await api("programa", { objetivo: o.id, semanas: +$("#plazoSel").value }); aviso("📅 Plazo puesto: sus temas van primero en tu plan"); montarDominio(o); };
  if ($("#plazoQuitar")) $("#plazoQuitar").onclick = async () => { await api("programa", { objetivo: o.id, semanas: 0 }); montarDominio(o); };
  if ($("#frGen")) $("#frGen").onclick = async () => {
    const j = await api("frontera", { objetivo: o.id }); aviso("🔭 Mapeando la frontera (5-15 min); puedes seguir estudiando");
    montarDominio(o); esperarTrabajo(j.trabajo, () => {}).then(() => { if (location.hash.includes("objetivos/" + o.id)) montarDominio(o); }).catch((e) => aviso("Error: " + e.message));
  };
  if (d.frontera_trabajo && !f) setTimeout(() => { if (location.hash.includes("objetivos/" + o.id)) montarDominio(o); }, 20000);
  $$("[data-guia]", caja).forEach((b) => (b.onclick = async () => {
    b.disabled = true; b.innerHTML = `<span class="cargando"></span> Preparando (2-5 min)…`;
    try { const j = await api("paper/guia", { objetivo: o.id, paper: +b.dataset.guia }); const r = await esperarTrabajo(j.trabajo, (t) => (b.innerHTML = `<span class="cargando"></span> ${esc(textoEstado(t))}`)); ir("paper/" + r.id); }
    catch (e) { b.textContent = "Error: " + e.message; b.disabled = false; }
  }));
  $("#apEnviar").onclick = async () => {
    const texto = $("#apTexto").value.trim(); if (texto.length < 20) return aviso("Escribe tu idea con al menos una frase completa");
    const est = $("#apEstado"); $("#apEnviar").disabled = true;
    try { const j = await api("aporte", { objetivo: o.id, texto }); await esperarTrabajo(j.trabajo, (t) => (est.innerHTML = `<span class="cargando"></span> ${esc(textoEstado(t))}`)); montarDominio(o); }
    catch (e) { est.textContent = "Error: " + e.message; $("#apEnviar").disabled = false; }
  };
}
function htmlAporte(a) {
  const e = a.evaluacion;
  return `<details class="tarjeta" style="margin:.5rem 0"><summary><b>${esc(a.texto.slice(0, 90))}${a.texto.length > 90 ? "…" : ""}</b> <span class="etq">originalidad ${e.originalidad}/5</span> <span class="etq">viabilidad ${e.viabilidad}/5</span></summary>
    <div class="peq"><p><b>Problema que toca:</b> ${esc(e.problema_que_toca)}</p><p><b>¿Ya existe?</b> ${esc(e.ya_existe)}</p><p>✅ ${esc(e.fortalezas)}</p><p>❌ ${esc(e.debilidades)}</p>
    ${e.novedad_literatura ? htmlNovedad(e.novedad_literatura) : ""}
    <p>👉 <b>Siguiente paso:</b> ${esc(e.siguiente_paso)}</p><p>🎤 <b>Cómo presentarla:</b> ${esc(e.como_presentarlo)}</p><p>📚 <b>Qué te falta aprender:</b> ${esc(e.que_te_falta_aprender)}</p></div></details>`;
}
const TIPO_PREG = { problema: "🎯 El problema", metodo: "🔧 El método", resultado: "📊 El resultado", limites: "⚠️ Los límites", conexion: "🔗 Conexión con tu meta", critica: "🧐 Tu crítica" };
VISTAS.paper = async ([id]) => {
  const d = await api("paper?id=" + encodeURIComponent(id));
  if (d.error) throw new Error(d.error);
  const p = d.paper, g = d.guia;
  vista.innerHTML = `<button class="btn fantasma peq" onclick="ir('objetivos/${d.objetivo}')">← La meta</button>
    <div class="suave peq" style="margin-top:.5rem">📄 Lectura guiada · ${esc(p.clase || "")} · ${esc(p.autores)} (${p.anio}) · ${p.citas} citas</div>
    <h1 style="margin-top:.2rem">${esc(p.titulo)}</h1>
    <div class="fila"><a class="btn pri" href="${escUrl(p.abierto || p.url)}" target="_blank" rel="noopener">${p.abierto ? "📖 Abrir el texto libre" : "📖 Abrir el paper"}</a>${p.abierto && p.url !== p.abierto ? `<a class="btn" href="${escUrl(p.url)}" target="_blank" rel="noopener">Ficha (DOI)</a>` : ""}</div>
    <div class="tarjeta"><b>💡 Idea central</b><p style="margin:.3rem 0">${esc(g.idea_central)}</p><b>Por qué importa</b><p class="peq" style="margin:.3rem 0">${esc(g.por_que_importa)}</p></div>
    <details class="tarjeta" open><summary><b>🧭 Cómo leerlo</b></summary><div class="leccion peq" id="pComo"></div></details>
    ${g.requisitos.length ? `<details class="tarjeta"><summary><b>🧱 Lo que necesitas saber antes (${g.requisitos.length})</b></summary>${g.requisitos.map((r) => `<div class="peq" style="margin:.4rem 0"><b>${esc(r.concepto)}</b>: ${esc(r.explicacion)}${r.tema ? ` · <a href="#/tema/${esc(r.tema)}">estudiarlo en tu ruta →</a>` : ""}</div>`).join("")}</details>` : ""}
    ${g.glosario.length ? `<details class="tarjeta"><summary><b>🗣️ Glosario (${g.glosario.length})</b></summary><dl class="peq">${g.glosario.map((v) => `<dt><b>${esc(v.termino)}</b></dt><dd style="margin:0 0 .4rem 1rem">${esc(v.significado)}</dd>`).join("")}</dl></details>` : ""}
    <h2>✍️ Responde mientras lees</h2><p class="suave peq">Con tus palabras, sin copiar. La IA corrige como un investigador del tema: premia tu razonamiento y la crítica bien fundada.</p>
    ${g.preguntas.map((q, i) => { const r = d.respuestas[i]; return `<div class="tarjeta" data-pq="${i}"><div class="suave peq">${TIPO_PREG[q.tipo] || q.tipo}</div><div class="pq"></div>
      <textarea placeholder="Tu respuesta…">${esc(r ? r.respuesta : "")}</textarea>
      <div class="fila" style="margin-top:.4rem"><button class="btn peq pri" data-corr="${i}">${r ? "Corregir de nuevo" : "Corregir"}</button></div><div class="nota">${r ? notaIA(r.nota) : ""}</div>
      ${r ? `<details><summary class="suave peq">Respuesta de referencia</summary><div class="peq rm"></div></details>` : ""}</div>`; }).join("")}`;
  pintarMd($("#pComo"), g.como_leerlo);
  g.preguntas.forEach((q, i) => { const c = $(`[data-pq="${i}"]`); pintarMd($(".pq", c), q.pregunta); const rm = $(".rm", c); if (rm) pintarMd(rm, q.respuesta_modelo); });
  $$("[data-corr]").forEach((b) => (b.onclick = async () => {
    const i = +b.dataset.corr, c = $(`[data-pq="${i}"]`), txt = $("textarea", c).value.trim();
    if (txt.length < 3) return aviso("Escribe tu respuesta");
    b.disabled = true; const n = $(".nota", c); n.innerHTML = `<span class="cargando"></span> Corrigiendo…`;
    try { const j = await api("paper/responder", { id: d.id, i, respuesta: txt }); await esperarTrabajo(j.trabajo, (t) => (n.innerHTML = `<span class="cargando"></span> ${esc(textoEstado(t))}`)); refrescar(); }
    catch (e) { n.textContent = "Error: " + e.message; b.disabled = false; }
  }));
};

/* =============================== CÓMO APRENDES (panel) =============================== */
const pct = (x) => (x == null ? "—" : Math.round(x * 100) + "%");
function tip(texto) { return ` data-tip="${esc(texto)}" tabindex="0"`; }
function barrasV(datos, { alto = 130, etiqueta, valor, tipTxt, max, cada = 1, sufijo = "" }) {
  const m = max || Math.max(1, ...datos.map(valor));
  return `<div class="graf-v" style="height:${alto}px">${datos.map((x, i) => {
    const v = valor(x); const h = v == null ? 0 : Math.max(v > 0 ? 3 : 0, (v / m) * (alto - 22));
    return `<div class="col"${tip(tipTxt(x))}><i style="height:${h}px" class="${v == null ? "sin" : ""}"></i><span>${i % cada === 0 ? esc(etiqueta(x)) : ""}</span></div>`;
  }).join("")}</div>`;
}
function barrasH(filas_, { valor, nombre, texto, max, color }) {
  const m = max || Math.max(1, ...filas_.map(valor));
  return filas_.map((x) => `<div class="graf-h"${tip(texto(x))}><span class="n">${esc(nombre(x))}</span>
    <div class="pista"><i style="width:${Math.max(1, (valor(x) / m) * 100)}%;${color ? "background:" + color(x) : ""}"></i></div><b>${esc(texto(x).split(" · ")[0])}</b></div>`).join("");
}
// 📖 Lectura medida (velocidad por idioma y fórmulas, lecturas completas, avance por actividad): panel y reporte
function htmlLectura(x) {
  if (!x || !x.sesiones) return `<h2>📖 Cómo lees</h2><div class="tarjeta"><p class="suave">Aún sin datos: se mide sola mientras lees lecciones, noticias a fondo y lecturas guiadas (solo cuenta el tiempo con actividad real).</p></div>`;
  const hace = (t) => new Date(t * 1000).toLocaleDateString(LOC, { day: "numeric", month: "short" });
  return `<h2>📖 Cómo lees</h2><div class="tarjeta">
    <div class="stats"><div class="stat"><b>${x.wpm_base}</b><span>palabras/min en español${x.propia ? "" : " (estimado: aún sin datos propios)"}</span></div>
      <div class="stat"><b>${x.completas}/${x.sesiones}</b><span>lecturas terminadas (30 d)</span></div></div>
    ${x.velocidades.length ? `<table class="tabla"><tr><th>Tipo de texto</th><th>Velocidad</th><th>Tiempo leído</th></tr>${x.velocidades.map((v) =>
      `<tr><td>${esc(v.nombre)}</td><td><b>${v.valor ?? "—"}</b> ${esc(v.unidad)}</td><td>${v.min} min · ${v.n} ${v.cat === "formulas" ? "fórmulas" : "palabras"}</td></tr>`).join("")}</table>` : ""}
    ${x.metodos.length ? `<table class="tabla" style="margin-top:.6rem"><tr><th>Actividad</th><th>Terminadas</th><th>Avance</th></tr>${x.metodos.map((m) =>
      `<tr><td>${esc(m.nombre)}</td><td>${m.completas}/${m.sesiones}</td><td>${m.avance_10min == null ? "—" : m.avance_10min + " % del texto cada 10 min"} · ${m.min} min</td></tr>`).join("")}</table>` : ""}
    ${x.recientes.length ? `<details style="margin-top:.6rem"><summary class="suave peq">Últimas lecturas</summary><ul class="peq">${x.recientes.map((r) =>
      `<li>${hace(r.fin)} · ${esc(r.tema || r.metodo)} · ${r.min} min · ${r.avance} % ${r.completa ? "✅" : ""}</li>`).join("")}</ul></details>` : ""}
    <p class="suave peq">Terminada = llegaste al final sin ir más rápido que 2,5× tu velocidad. Un bloque cuenta como leído cuando estuvo en pantalla al menos lo que tardas en leerlo a 3× tu ritmo.</p></div>`;
}
VISTAS.progreso = async () => {
  const [d, p, ch, lp, nv, yo] = await Promise.all([api("analitica"), api("progreso"), api("chequeos"), api("largo_plazo"), api("niveles"), api("yo")]);
  const activas = nv.areas.filter((a) => (yo.perfil.pesos[a.id] || 0) > 0 || a.por_nivel[a.siguiente] > 0 || a.nivel > 0)
    .sort((a, b) => b.nivel - a.nivel || (b.progreso_siguiente || 0) - (a.progreso_siguiente || 0));
  const inactivas = nv.areas.filter((a) => !activas.includes(a));
  const filaNivel = (a, meta) => `<div class="nivel-fila"${tip(Object.entries(a.por_nivel).map(([k, v]) => `${NIVELES[k]}: ${pct(v)}`).join(" · "))}>
    <div class="fila entre"><span>${meta ? "🎯 " + esc(a.titulo) : esc(a.icono || "") + " " + esc(a.nombre)}</span>
      <span class="insignia n${a.examen === undefined || a.examen === null ? a.nivel : Math.max(1, a.nivel)}">${esc(a.etiqueta)}</span></div>
    <div class="barra-prog" style="margin-top:.3rem"><i style="width:${Math.min(100, (a.progreso_siguiente || 0) * 100)}%"></i></div>
    <div class="suave peq">${a.siguiente ? `${Math.round(Math.min(1, a.progreso_siguiente) * 100)} % hacia <b>${esc(a.proximo || "")}</b> (nivel ${NIVELES[a.siguiente]})` : "Nivel máximo de la ruta alcanzado 🏆"} · ${esc(a.explicacion)}</div>
    ${meta || a.grupo === "Idiomas" ? "" : filaMercado(a)}</div>`;
  const filaMercado = (a) => {
    const m = a.mercado;
    if (!m) return `<button class="btn peq fantasma" style="margin-top:.3rem" data-mercado="${a.id}">📊 Medir contra lo que pide hoy el mercado</button>`;
    const lista = (xs, f) => xs.length ? `<ul class="peq">${xs.map(f).join("")}</ul>` : `<p class="suave peq">—</p>`;
    const TEND = { nueva: "🆕", "en alza": "📈", estable: "➖", "en declive": "📉" };
    return `<details class="mercado"><summary class="peq">📊 <b>Según lo que pide hoy el mercado: ${esc(m.etiqueta)}</b>
        ${m.siguiente ? ` · ${Math.round(Math.min(1, m.progreso_siguiente) * 100)} % hacia ${esc(m.rol_siguiente || "")}` : " · nivel máximo 🏆"}
        ${m.nivel < a.nivel ? ` <span class="etq medio">por debajo del nivel de la ruta</span>` : ""}</summary>
      <p class="peq">${esc(m.resumen)}</p>
      <b class="peq">Qué cambió en 5 años</b>${lista(m.cambios_5_anios, (x) => `<li>${esc(x)}</li>`)}
      <b class="peq">Te falta para subir (de lo que la Academia enseña)</b>${lista(m.brechas, (b) => `<li>${TEND[b.tendencia] || ""} <b>N${b.nivel}</b> ${esc(b.competencia)} · ${Math.round(b.cobertura * 100)} %${b.modulos.length ? ` → ${b.modulos.map((x) => `<a href="#/ruta/${esc(x.ref.split(".")[0])}">${esc(x.t)}</a>`).join(", ")}` : ""}</li>`)}
      ${m.fuera_del_curriculo.length ? `<b class="peq">Lo piden pero tu ruta aún no lo enseña</b>${lista(m.fuera_del_curriculo, (b) => `<li>${TEND[b.tendencia] || ""} <b>N${b.nivel}</b> ${esc(b.competencia)}</li>`)}<p class="suave peq">Puedes cubrirlo creando un 🎯 objetivo con estas competencias.</p>` : ""}
      ${m.en_declive.length ? `<p class="peq"><b>📉 Pesa cada vez menos:</b> ${m.en_declive.map(esc).join("; ")}</p>` : ""}
      <details><summary class="suave peq">Qué se exige hoy en cada nivel</summary>${m.referente.map((n) => `<p class="peq" style="margin:.4rem 0 .1rem"><b>${n.nivel}. ${esc(n.rol)}</b> · tu cobertura ${Math.round((m.por_nivel[n.nivel] || 0) * 100)} %</p><ul class="peq">${n.competencias.map((c) => `<li>${TEND[c.tendencia] || ""} ${esc(c.competencia)} <span class="suave">· ${c.cobertura == null ? "no está en la ruta" : Math.round(c.cobertura * 100) + " %"}</span></li>`).join("")}</ul>`).join("")}</details>
      <p class="suave peq">Referente armado el ${new Date(m.fecha * 1000).toLocaleDateString(LOC)} con ${m.fuentes.length} fuentes web (${m.fuentes.slice(0, 3).map((f) => `<a href="${escUrl(f.url)}" target="_blank" rel="noopener">${esc((f.titulo || "").slice(0, 40))}</a>`).join(", ")}…). Se renueva solo cada mes.
        <button class="btn peq fantasma" data-mercado="${a.id}">🔄 Actualizar ahora</button></p></details>`;
  };
  const L = lp.largo, C = lp.cambios;
  const fmtC = (f, v) => v == null ? "—" : f.unidad === "%" ? pct(v) : `${Math.round(v * 10) / 10}${f.unidad ? " " + f.unidad : ""}`;
  const maxCalor = Math.max(1, ...d.calor.flat());
  const totMem = Object.values(d.memoria).reduce((a, b) => a + b, 0);
  const MEM = [["firme", "Firme (≥90 %)", "var(--bien)"], ["estable", "Estable (80-90 %)", "color-mix(in srgb, var(--bien) 55%, var(--panel2))"],
    ["olvidando", "Olvidándose (60-80 %)", "var(--medio)"], ["olvidada", "Probablemente olvidada (<60 %)", "var(--mal)"], ["nueva", "Nueva (sin repasar)", "var(--panel2)"]];
  const grupos = {}; p.areas.forEach((a) => (grupos[a.grupo] = grupos[a.grupo] || []).push(a));
  const r = d.resultados;
  vista.innerHTML = `<h1>📈 Cómo aprendes</h1>
    <div class="stats">
      <div class="stat"><b>🔥 ${p.racha}</b><span>días seguidos</span></div>
      <div class="stat"><b>${d.minutos_30}</b><span>minutos en 30 días</span></div>
      <div class="stat"><b>${d.dias_activos_14}/14</b><span>días activos</span></div>
      <div class="stat"><b>${pct(r.repaso)}</b><span>retención real (30 d)</span></div>
      <div class="stat"><b>${p.dominados}</b><span>temas dominados</span></div>
      <div class="stat"><b>${d.seg_por_tarjeta ?? "—"}<small class="suave"> s</small></b><span>por tarjeta</span></div>
    </div>
    <div class="tarjeta" style="border-color:var(--acento)"><div class="fila entre"><b>🧪 Chequeo semanal</b>
      <button class="btn peq ${ch.abierto ? "pri" : ""}" onclick="ir('chequeo')">${ch.abierto ? "Hacer el chequeo pendiente" : "Ver chequeos"}</button></div>
      <p class="suave peq" style="margin:.3rem 0 0">Cada ${DIAS[ch.dia]} te examina de lo que estudiaste y detecta qué olvidaste.
      ${ch.historial.filter((x) => x.puntaje != null).slice(0, 1).map((x) => `Último: <b>${pct(x.puntaje)}</b> recordado (${x.retenidos} ✓ · ${x.olvidados} ✗).`).join("")}</p></div>
    <h2>💡 Lo que dicen tus datos</h2>
    <div class="tarjeta"><ul class="consejos">${d.consejos.map((c) => `<li>${md(c).replace(/^<p>|<\/p>\s*$/g, "")}</li>`).join("")}</ul></div>
    <div class="fila"><button class="btn" onclick="ir('reporte')">📄 Reporte completo y descarga de datos</button></div>
    <h2>🎓 Tu nivel profesional</h2>
    <div class="tarjeta"><p class="suave peq" style="margin-top:0">Un nivel se alcanza cuando dominas en promedio el 70 % de sus temas <b>y de todos los anteriores</b>. Escala: ${nv.escala.map((e) => `<b>${e.nivel}</b> ${esc(e.etiqueta)}`).join(" · ")}. Si ya sabes algo, haz la ⚡ prueba de nivel de sus módulos en la Ruta para que aparezca tu nivel real. Se recalcula en cada actualización diaria y tras cada chequeo.</p>
      ${activas.map((a) => filaNivel(a)).join("") || `<p class="suave">Activa áreas en Ajustes.</p>`}
      ${inactivas.length ? `<details><summary class="suave peq">Áreas sin prioridad (${inactivas.length})</summary>${inactivas.map((a) => filaNivel(a)).join("")}</details>` : ""}</div>
    ${nv.metas.length ? `<div class="tarjeta"><b>Tus metas</b>${nv.metas.map((m) => filaNivel(m, true)).join("")}</div>` : ""}
    ${nv.historial.length ? `<details class="tarjeta"><summary><b>📜 Historial de niveles</b></summary><ul class="consejos">${nv.historial.map((h) => `<li>${new Date(h.fecha * 1000).toLocaleDateString(LOC)} · ${esc(h.nombre)}: ${h.a > h.de ? "⬆️ subiste a" : "⬇️ bajaste a"} <b>${esc(h.examen || h.etiqueta)}</b></li>`).join("")}</ul></details>` : ""}
    ${lp.plan.ajustes.length ? `<h2>🧭 Cómo se adapta tu estudio</h2><div class="tarjeta"><ul class="consejos">${lp.plan.ajustes.map((a) => `<li>${esc(a)}</li>`).join("")}</ul>
      <p class="suave peq" style="margin-bottom:0">Las lecciones, el tutor y los chequeos también reciben esto: «${esc(lp.plan.adaptacion || "aún sin patrones")}».</p></div>` : ""}

    <h2>⏱️ Corto plazo</h2>
    <div class="stats">
      <div class="stat"><b>${pct(L.pulso_media)}</b><span>pulso diario (30 d)</span></div>
      <div class="stat"${tip(`${L.n_1dia} repasos`)}><b>${pct(L.retencion_1dia)}</b><span>recuerdas a 1-2 días</span></div>
      <div class="stat"><b>${L.pulso_30.length}</b><span>pulsos en 30 días</span></div></div>
    ${L.pulso_30.length ? `<div class="tarjeta"><div class="suave peq">Pulso diario: % recordado cada día</div>${barrasV(L.pulso_30, { etiqueta: (x) => new Date(x.fecha * 1000).getDate(), valor: (x) => x.valor, max: 1, cada: Math.ceil(L.pulso_30.length / 10), tipTxt: (x) => `${new Date(x.fecha * 1000).toLocaleDateString(LOC)} · ${pct(x.valor)}` })}</div>` : `<p class="suave peq">Haz el ⚡ Pulso diario en «Hoy» (1-2 min) para medir tu memoria de corto plazo.</p>`}

    <h2>🏛️ Largo plazo</h2>
    <div class="tarjeta"><div class="suave peq">% que recuerdas según hace cuánto aprendiste algo (repasos con ≥1 día de separación). Esto verifica el conocimiento a lo más largo posible: con los meses aparecen las barras de 6-12 meses y +1 año.</div>
      ${barrasV(L.curva_edad, { etiqueta: (x) => x.edad, valor: (x) => x.retencion, max: 1, alto: 130, tipTxt: (x) => `Aprendido hace ${x.edad} · ${x.retencion == null ? "sin datos aún" : pct(x.retencion) + " recordado"} · ${x.n} repasos` })}
      <div class="fila peq suave" style="justify-content:space-around">${L.curva_edad.map((x) => `<span>${pct(x.retencion)}</span>`).join("")}</div>
      <p class="peq" style="margin-bottom:0">${L.recuerdo_mas_antiguo ? `🏆 Recuerdo verificado más antiguo: <b>${L.recuerdo_mas_antiguo.dias} días</b> («${esc(L.recuerdo_mas_antiguo.frente)}»).` : "Aún no hay recuerdos verificados a largo plazo."}
      ${L.n_chequeo_viejos ? ` · Temas de hace más de 1 mes en chequeos: <b>${pct(L.chequeo_temas_viejos)}</b> (${L.n_chequeo_viejos}).` : ""}</p></div>

    <h2>🔄 Cómo ha cambiado tu forma de aprender</h2>
    <div class="tarjeta"><p class="suave peq" style="margin-top:0">Cada semana se guarda una foto de tu forma de aprender (horarios, métodos, retención, velocidad). Tu cerebro cambia: aquí se ve cómo.</p>
      ${C.notas.length ? `<ul class="consejos">${C.notas.map((n) => `<li>${esc(n)}</li>`).join("")}</ul>` : `<p class="suave">${C.historial.length < 2 ? "Se necesitan al menos 4 semanas de datos para comparar; la primera foto se toma esta semana." : "Sin cambios notables respecto a hace 4 semanas."}</p>`}
      <table class="tabla"><tr><th>Indicador</th><th>Ahora</th><th>Hace ~4 sem</th><th>Hace ~12 sem</th></tr>${C.filas.map((f) => `<tr><td>${esc(f.nombre)}</td><td><b>${fmtC(f, f.ahora)}</b></td><td>${fmtC(f, f.hace4)}</td><td>${fmtC(f, f.hace12)}</td></tr>`).join("")}</table></div>
    ${d.informe ? `<details class="tarjeta"><summary><b>🧑‍🏫 Informe semanal de tu coach (IA)</b> <span class="suave peq">· ${new Date(d.informe.creado * 1000).toLocaleDateString(LOC)}</span></summary><div class="leccion" id="informe"></div></details>` : ""}

    <h2>🕐 Cuándo estudias</h2>
    <div class="tarjeta"><div class="suave peq">Minutos por hora del día · últimos 30 días</div>
      ${barrasV(d.por_hora, { etiqueta: (x) => x.h + "h", valor: (x) => x.min, cada: 3, tipTxt: (x) => `${x.h}:00-${x.h + 1}:00 · ${Math.round(x.min)} min · ${x.repasos} repasos${x.repasos ? " · " + pct(x.bien / x.repasos) + " recordado" : ""}` })}</div>
    <div class="rejilla" style="grid-template-columns:repeat(auto-fit,minmax(140px,1fr))">${d.franjas.map((f) => `<div class="stat"${tip(`${f.repasos} repasos en esta franja (90 d)`)}>
      <b>${f.retencion == null ? "—" : pct(f.retencion)}</b><span>recuerdas en la ${f.franja} (${f.desde}-${f.hasta} h) · ${f.min} min</span></div>`).join("")}</div>
    <div class="tarjeta" style="margin-top:.8rem"><div class="suave peq">Tu semana tipo · minutos por día y hora (8 semanas)</div>
      <div class="calor-sem">${d.calor.map((fila_, i) => `<span class="dia">${DIAS_C[i]}</span>${fila_.map((v, h) => `<i${tip(`${DIAS[i]} ${h}:00 · ${Math.round(v)} min`)} style="${v ? `background:color-mix(in srgb, var(--acento) ${Math.round(15 + (v / maxCalor) * 85)}%, var(--panel2))` : ""}"></i>`).join("")}`).join("")}
      <span></span>${Array.from({ length: 24 }, (_, h) => `<span class="hora">${h % 6 === 0 ? h : ""}</span>`).join("")}</div>
      <div class="leyenda-seq"><span>menos</span><i style="background:var(--panel2)"></i><i style="background:color-mix(in srgb, var(--acento) 40%, var(--panel2))"></i><i style="background:color-mix(in srgb, var(--acento) 70%, var(--panel2))"></i><i style="background:var(--acento)"></i><span>más</span></div></div>

    <h2>🧠 Cómo estudias</h2>
    <div class="tarjeta"><div class="suave peq">Minutos por método · últimos 30 días</div>
      ${d.metodos.length ? barrasH(d.metodos, { valor: (x) => x.min, nombre: (x) => x.nombre, texto: (x) => `${x.min} min · ${x.usos} veces` }) : `<p class="suave">Aún sin datos.</p>`}</div>
    ${htmlLectura(d.lectura)}
    <div class="stats">
      <div class="stat"${tip(`${r.n.quiz || 0} quizzes`)}><b>${pct(r.quiz)}</b><span>promedio en quizzes</span></div>
      <div class="stat"${tip(`${r.n.feynman || 0} explicaciones`)}><b>${pct(r.feynman)}</b><span>explicaciones Feynman</span></div>
      <div class="stat"${tip(`${r.n.apunte_eval || 0} apuntes evaluados`)}><b>${pct(r.apuntes)}</b><span>apuntes a mano</span></div>
      <div class="stat"${tip(`${r.n.prueba || 0} pruebas`)}><b>${pct(r.prueba)}</b><span>pruebas de nivel</span></div>
      <div class="stat"${tip(`${r.n.practica || 0} entregas corregidas`)}><b>${pct(r.practica)}</b><span>ejercicios de práctica</span></div></div>
    <div class="tarjeta"><b>¿Qué método te hace recordar más?</b><p class="suave peq">Retención de las tarjetas de temas trabajados con cada método, frente a las de temas sin él (repasos con ≥1 día de separación). Se necesita ≥20 repasos por grupo para concluir.</p>
      <table class="tabla"><tr><th>Método</th><th>Con</th><th>Sin</th><th>Diferencia</th></tr>${d.eficacia.map((e) => {
        const ok = e.n_con >= 20 && e.n_sin >= 20; const dif = ok ? e.con - e.sin : null;
        return `<tr><td>${esc(e.metodo)}</td><td>${pct(e.con)} <span class="suave peq">(${e.n_con})</span></td><td>${pct(e.sin)} <span class="suave peq">(${e.n_sin})</span></td>
          <td>${dif == null ? `<span class="suave">faltan datos</span>` : `<span class="etq ${dif > 0 ? "bien" : "mal"}">${dif > 0 ? "▲" : "▼"} ${Math.abs(Math.round(dif * 100))} pts</span>`}</td></tr>`; }).join("")}</table></div>
    <div class="stats">
      <div class="stat"><b>${d.sesiones.n}</b><span>sesiones (30 d)</span></div>
      <div class="stat"><b>${d.sesiones.mediana}<small class="suave"> min</small></b><span>duración típica</span></div>
      <div class="stat"><b>${d.sesiones.por_semana}</b><span>sesiones por semana</span></div>
      <div class="stat"><b>${d.sesiones.hora_tipica == null ? "—" : d.sesiones.hora_tipica + ":00"}</b><span>hora en que sueles empezar</span></div></div>

    <h2>📅 Tu ritmo semana a semana</h2>
    <div class="rejilla">
      <div class="tarjeta"><div class="suave peq">Minutos de estudio por semana</div>${barrasV(d.semanas, { etiqueta: (x) => x.etiqueta, valor: (x) => x.min, tipTxt: (x) => `Semana del ${x.etiqueta} · ${x.min} min · ${x.lecciones} lecciones · ${x.repasos} repasos` })}</div>
      <div class="tarjeta"><div class="suave peq">Retención en repasos por semana</div>${barrasV(d.semanas, { etiqueta: (x) => x.etiqueta, valor: (x) => x.retencion, max: 1, tipTxt: (x) => `Semana del ${x.etiqueta} · ${x.retencion == null ? "sin repasos" : pct(x.retencion) + " recordado de " + x.repasos}` })}</div></div>

    <h2>📉 Tu curva del olvido</h2>
    <div class="tarjeta"><div class="suave peq">% que recuerdas según los días que pasan sin repasar (90 d). FSRS programa cada tarjeta para mantenerla en ~90 %.</div>
      ${barrasV(d.curva, { etiqueta: (x) => x.rango, valor: (x) => x.retencion, max: 1, alto: 140, tipTxt: (x) => `${x.rango} sin repasar · ${x.retencion == null ? "sin datos" : pct(x.retencion) + " recordado"} · ${x.n} repasos` })}
      <div class="fila peq suave" style="justify-content:space-around">${d.curva.map((x) => `<span>${pct(x.retencion)}</span>`).join("")}</div></div>

    <h2>🧩 Estado de tu memoria ahora</h2>
    <div class="tarjeta"><div class="suave peq">${totMem} tarjetas según su probabilidad de recordarlas hoy</div>
      <div class="apilada">${MEM.filter(([k]) => d.memoria[k]).map(([k, n, c]) => `<i style="flex:${d.memoria[k]};background:${c}"${tip(`${n}: ${d.memoria[k]}`)}></i>`).join("") || `<i style="flex:1;background:var(--panel2)"></i>`}</div>
      <div class="leyenda">${MEM.map(([k, n, c]) => `<span><i style="background:${c}"></i>${n} <b>${d.memoria[k]}</b></span>`).join("")}</div>
      ${d.olvidando.length ? `<p style="margin-bottom:.2rem"><b>Temas que se te están olvidando</b> <span class="suave peq">(probabilidad media de recordar sus tarjetas)</span></p>
        <ul class="temas">${d.olvidando.map((t) => `<li data-tema="${t.id}"><span class="punto" style="border-color:var(--medio)"></span><span style="flex:1">${esc(t.t)} <span class="suave peq">· ${esc(t.area)}</span></span><span class="etq ${t.r < 0.6 ? "mal" : "medio"}">${pct(t.r)}</span></li>`).join("")}</ul>
        <button class="btn pri" style="margin-top:.6rem" onclick="ir('repasar')">🔁 Repasar ahora</button>` : ""}
      ${d.areas_memoria.length ? `<p><b>Memoria por área</b></p>${barrasH(d.areas_memoria, { valor: (x) => x.r, max: 1, nombre: (x) => x.nombre, texto: (x) => `${pct(x.r)} · ${x.n} tarjetas` })}` : ""}</div>

    <h2>⏳ Tiempo por área (30 días)</h2>
    <div class="tarjeta">${d.minutos_area.length ? barrasH(d.minutos_area, { valor: (x) => x.min, nombre: (x) => x.nombre, texto: (x) => `${x.min} min` }) : `<p class="suave">Aún sin datos.</p>`}</div>

    <h2>🗂️ Constancia (26 semanas)</h2>${calorAnual(p)}
    ${p.debiles.length ? `<h2>⚠️ Más fallos en repasos (30 d)</h2><div class="tarjeta"><ul class="temas">${p.debiles.map((x) => `<li data-tema="${x.tema}"><span class="punto"></span><span style="flex:1">${esc(x.t)}</span><span class="etq mal">${x.fallos} fallos</span></li>`).join("")}</ul></div>` : ""}
    <h2>🎓 Dominio por área</h2>${Object.entries(grupos).map(([g, as]) => `<div class="nivel-tit">${esc(g)}</div><div class="tarjeta">${as.map((a) => `
      <div style="margin:.5rem 0;cursor:pointer" onclick="ir('ruta/${a.id}')"><div class="fila entre peq"><span>${esc(a.icono)} ${esc(a.nombre)}</span><span class="suave">${a.dominados}/${a.temas}</span></div>
      <div class="barra-prog"><i style="width:${a.dominio * 100}%"></i></div></div>`).join("")}</div>`).join("")}`;
  if (d.informe) pintarMd($("#informe"), d.informe.informe);
  $$("[data-tema]").forEach((li) => (li.onclick = () => ir("tema/" + li.dataset.tema)));
  $$("[data-mercado]").forEach((b) => (b.onclick = async (e) => {
    e.preventDefault(); b.disabled = true;
    try {
      const j = await api("mercado", { area: b.dataset.mercado });
      await esperarTrabajo(j.trabajo, (t) => (b.textContent = "⏳ " + textoEstado(t)));
      refrescar();
    } catch (x) { b.textContent = "❌ " + x.message; }
  }));
};
const DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"];
const DIAS_C = ["L", "M", "X", "J", "V", "S", "D"];
function calorAnual(p) {
  const dias = []; const hoy = new Date(); hoy.setHours(12);
  const inicio = new Date(hoy); inicio.setDate(inicio.getDate() - 7 * 25 - inicio.getDay());
  for (let x = new Date(inicio); x <= hoy; x.setDate(x.getDate() + 1)) {
    const k = x.toISOString().slice(0, 10); const v = p.dias[k] || { repasos: 0, minutos: 0, lecciones: 0 };
    const nivel = v.repasos + v.lecciones * 10 + v.minutos;
    dias.push(`<i${tip(`${k}: ${Math.round(v.minutos)} min, ${v.repasos} repasos, ${v.lecciones} lecciones`)} style="${nivel ? `background:color-mix(in srgb, var(--acento) ${Math.min(100, 25 + nivel)}%, var(--panel2))` : ""}"></i>`);
  }
  return `<div class="tarjeta"><div class="calor">${dias.join("")}</div></div>`;
}

/* =============================== CHEQUEO SEMANAL =============================== */
VISTAS.chequeo = async ([id]) => {
  const ch = await api("chequeos");
  if (!id && ch.abierto) return ir("chequeo/" + ch.abierto);
  if (!id) {
    const s = ch.semana;
    vista.innerHTML = `<h1>🧪 Chequeo semanal</h1>
      <p class="suave">Cada <b>${DIAS[ch.dia]}</b> la IA prepara un examen corto con lo que estudiaste esta semana y lo más antiguo que no has tocado, más las tarjetas que más riesgo tienen de olvidarse.
      Lo que falles deja de contar como dominado y vuelve a tu repaso. Lo que aciertes queda reforzado.</p>
      <div class="tarjeta"><b>Esta semana</b><div class="stats" style="margin-bottom:.3rem">
        <div class="stat"><b>${s.minutos}</b><span>minutos</span></div><div class="stat"><b>${s.nuevos.length}</b><span>temas nuevos</span></div>
        <div class="stat"><b>${s.dominados.length}</b><span>dominados</span></div><div class="stat"><b>${s.tarjetas_nuevas}</b><span>tarjetas nuevas</span></div></div>
        ${s.nuevos.length ? `<div class="peq">✅ <b>Aprendiste:</b> ${s.nuevos.map((t) => esc(t.t)).join(" · ")}</div>` : ""}
        ${s.olvidos.length ? `<div class="peq" style="margin-top:.4rem">⚠️ <b>Olvidaste en repasos:</b> ${s.olvidos.map((t) => `${esc(t.t)} (${t.n})`).join(" · ")}</div>` : ""}</div>
      <div class="fila"><button class="btn pri" id="crear" ${ch.trabajo ? "disabled" : ""}>${ch.esta_semana ? "Hacer otro chequeo ahora" : "Hacer el chequeo ahora"}</button><span id="chEstado" class="suave peq">${ch.trabajo ? esc(textoEstado(ch.trabajo)) : ""}</span></div>
      <label>Día del chequeo automático</label><div class="chips">${DIAS.map((d, i) => `<button class="chip ${i === ch.dia ? "activo" : ""}" data-dia="${i}">${d}</button>`).join("")}</div>
      <h2>Historial</h2>
      ${ch.historial.filter((x) => x.completado).length ? `<div class="tarjeta">${barrasV(ch.historial.filter((x) => x.completado).reverse(), { etiqueta: (x) => x.semana.slice(5), valor: (x) => x.puntaje, max: 1, tipTxt: (x) => `${x.semana} · ${pct(x.puntaje)} · ${x.retenidos} recordado · ${x.olvidados} olvidado` })}</div>` : ""}
      ${ch.historial.map((x) => `<div class="tarjeta fila entre" style="cursor:pointer" onclick="ir('chequeo/${x.id}')"><span><b>Semana ${esc(x.semana)}</b><br><span class="suave peq">${new Date(x.creado * 1000).toLocaleDateString(LOC)}</span></span>
        ${x.completado ? `<span><span class="etq bien">${x.retenidos} ✓</span> <span class="etq mal">${x.olvidados} ✗</span> <b>${pct(x.puntaje)}</b></span>` : `<span class="etq medio">pendiente</span>`}</div>`).join("") || `<p class="vacio">Aún no hay chequeos.</p>`}`;
    $$("[data-dia]").forEach((b) => (b.onclick = async () => { await api("chequeo/dia", { dia: +b.dataset.dia }); aviso("Chequeo cada " + DIAS[+b.dataset.dia]); enrutar(); }));
    const seguir = async (j) => {
      const r = await esperarTrabajo(j, (t) => { const e = $("#chEstado"); if (e) e.innerHTML = `<span class="cargando"></span> ${esc(textoEstado(t))} (2-4 min)`; });
      if (r.vacio) { $("#chEstado").textContent = r.motivo; $("#crear").disabled = false; return; }
      ir("chequeo/" + r.chequeo);
    };
    $("#crear").onclick = async () => { $("#crear").disabled = true; try { const j = await api("chequeo/crear", {}); await seguir(j.trabajo); } catch (e) { $("#chEstado").textContent = "Error: " + e.message; } };
    if (ch.trabajo) seguir(ch.trabajo.id).catch(() => {});
    return;
  }
  const c = await api("chequeo?id=" + id);
  if (c.error) throw new Error(c.error);
  if (c.resultado) return resultadoChequeo(c);
  const resp = {}, tresp = {};
  vista.innerHTML = `<button class="btn fantasma peq" onclick="ir('chequeo')">← Chequeos</button><h1>🧪 Chequeo · semana ${esc(c.semana)}</h1>
    <p class="suave">Sin mirar nada. No pasa nada por fallar: el objetivo es descubrir qué se olvidó para recuperarlo.</p>
    ${c.preguntas.length ? `<h2>1. ¿Lo sigues entendiendo?</h2><div id="chPreg"></div>` : ""}
    ${c.tarjetas.length ? `<h2>2. ¿Lo recuerdas?</h2><p class="suave peq">Piensa la respuesta antes de destaparla y sé honesto.</p><div id="chTarj"></div>` : ""}
    <button class="btn pri" id="chFin" style="width:100%;margin-top:1rem" disabled>Ver qué recuerdo y qué olvidé</button>`;
  const total = c.preguntas.length + c.tarjetas.length;
  const actualizar = () => ($("#chFin").disabled = Object.keys(resp).length + Object.keys(tresp).length < total);
  c.preguntas.forEach((p, i) => {
    const caja = document.createElement("div"); caja.className = "tarjeta";
    caja.innerHTML = `<div class="suave peq">${esc((c.temas_info[p.tema] || {}).t || "")}</div><div class="pq"></div>${p.opciones.map((o, j) => `<button class="opcion" data-j="${j}"></button>`).join("")}<div class="exp suave peq"></div>`;
    $("#chPreg").appendChild(caja);
    pintarMd($(".pq", caja), `**${i + 1}.** ${p.pregunta}`);
    $$(".opcion", caja).forEach((b, j) => { pintarMd(b, p.opciones[j]); b.onclick = () => {
      if (resp[i] != null) return; resp[i] = j;
      $$(".opcion", caja)[p.correcta].classList.add("ok"); if (j !== p.correcta) b.classList.add("no");
      pintarMd($(".exp", caja), "💡 " + p.explicacion); actualizar();
    }; });
  });
  c.tarjetas.forEach((t) => {
    const caja = document.createElement("div"); caja.className = "tarjeta";
    caja.innerHTML = `<div class="fr"></div><div class="rv" hidden style="margin-top:.6rem;padding-top:.6rem;border-top:1px dashed var(--borde)"></div>
      <div class="fila" style="margin-top:.6rem"><button class="btn peq destapar">Mostrar respuesta</button></div>`;
    $("#chTarj").appendChild(caja);
    pintarMd($(".fr", caja), t.frente); const t0 = Date.now();
    $(".destapar", caja).onclick = (e) => {
      const rv = $(".rv", caja); rv.hidden = false; pintarMd(rv, t.reverso, t.idioma);
      e.target.parentNode.innerHTML = `<button class="btn peq" data-r="0">✗ No lo recordaba</button><button class="btn peq" data-r="1">✓ Lo recordaba</button>`;
      $$("[data-r]", caja).forEach((b) => (b.onclick = () => { tresp[t.id] = { id: t.id, recordada: b.dataset.r === "1", segundos: (Date.now() - t0) / 1000 };
        $$("[data-r]", caja).forEach((x) => x.classList.toggle("pri", x === b)); actualizar(); }));
    };
  });
  $("#chFin").onclick = async () => {
    $("#chFin").disabled = true;
    const r = await api("chequeo/responder", { id: +id, respuestas: Object.entries(resp).map(([i, e]) => ({ i: +i, elegida: e })), tarjetas: Object.values(tresp) });
    if (r.error) return aviso(r.error);
    enrutar(); refrescarIA();
  };
};
function resultadoChequeo(c) {
  const r = c.resultado; const s = r.semana;
  const olv = r.temas.filter((x) => !x.ok), ret = r.temas.filter((x) => x.ok);
  const tOlv = r.tarjetas.filter((x) => !x.ok), tRet = r.tarjetas.filter((x) => x.ok);
  vista.innerHTML = `<button class="btn fantasma peq" onclick="ir('chequeo')">← Chequeos</button><h1>🧪 Resultado · semana ${esc(c.semana)}</h1>
    <div class="stats"><div class="stat"><b>${pct(r.puntaje)}</b><span>recordado</span></div>
      <div class="stat"><b>${ret.length + tRet.length}</b><span>✓ sigue en tu memoria</span></div>
      <div class="stat"><b>${olv.length + tOlv.length}</b><span>✗ olvidado</span></div>
      <div class="stat"><b>${s.minutos}</b><span>minutos esa semana</span></div></div>
    ${olv.length || tOlv.length ? `<div class="tarjeta" style="border-color:var(--mal)"><b>✗ Olvidado</b> <span class="suave peq">— ya volvió a tu repaso; los temas dejaron de contar como dominados.</span>
      <ul class="temas">${olv.map((x) => `<li data-tema="${x.id}"><span class="punto"></span><span style="flex:1">${esc(x.t)}</span><span class="btn peq">Repasar lección</span></li>`).join("")}
      ${tOlv.map((x) => `<li style="cursor:default"><span class="punto"></span><span class="peq">${esc(x.frente.slice(0, 120))}</span></li>`).join("")}</ul>
      <button class="btn pri" style="margin-top:.6rem" onclick="ir('repasar')">🔁 Recuperarlo ahora</button></div>` : `<div class="tarjeta">🎉 No olvidaste nada de lo evaluado.</div>`}
    ${ret.length || tRet.length ? `<div class="tarjeta" style="border-color:var(--bien)"><b>✓ Lo recuerdas</b><ul class="temas">${ret.map((x) => `<li data-tema="${x.id}"><span class="punto dominado"></span>${esc(x.t)}</li>`).join("")}
      ${tRet.map((x) => `<li style="cursor:default"><span class="punto dominado"></span><span class="peq">${esc(x.frente.slice(0, 120))}</span></li>`).join("")}</ul></div>` : ""}
    <div class="tarjeta"><b>Lo que aprendiste esa semana</b>
      <p class="peq">${s.nuevos.length ? s.nuevos.map((t) => esc(t.t)).join(" · ") : "Ningún tema nuevo."}</p>
      <p class="peq suave">${s.tarjetas_nuevas} tarjetas nuevas · ${s.repasos} repasos · ${s.dominados.length} temas dominados</p></div>
    ${c.informe ? `<div class="tarjeta"><b>🧑‍🏫 Informe de tu coach</b><div class="leccion" id="chInf"></div></div>` : ""}
    <button class="btn" onclick="ir('progreso')">📈 Ver cómo aprendes</button>`;
  if (c.informe) pintarMd($("#chInf"), c.informe);
  $$("[data-tema]").forEach((li) => (li.onclick = () => ir("tema/" + li.dataset.tema)));
}

/* tooltip único para todas las gráficas (ratón o toque) */
(() => {
  const t = document.createElement("div"); t.className = "tooltip"; t.hidden = true; document.body.appendChild(t);
  const mostrar = (el) => {
    t.textContent = el.dataset.tip; t.hidden = false;
    const r = el.getBoundingClientRect(); const w = t.offsetWidth;
    t.style.left = Math.min(window.innerWidth - w - 8, Math.max(8, r.left + r.width / 2 - w / 2)) + "px";
    t.style.top = Math.max(8, r.top - t.offsetHeight - 8) + "px";
  };
  document.addEventListener("pointerover", (e) => { const el = e.target.closest("[data-tip]"); if (el) mostrar(el); else t.hidden = true; });
  document.addEventListener("focusin", (e) => { const el = e.target.closest("[data-tip]"); if (el) mostrar(el); });
  window.addEventListener("scroll", () => (t.hidden = true), { passive: true });
})();

/* =============================== REPORTE =============================== */
VISTAS.reporte = async () => {
  const r = await api("reporte");
  const d = r.analitica, L = r.largo_plazo;
  vista.innerHTML = `<div class="fila entre no-imprimir"><button class="btn fantasma peq" onclick="ir('progreso')">← Cómo aprendes</button>
      <div class="fila"><a class="btn peq" href="api/exportar">⬇️ Todos mis datos (ZIP)</a><a class="btn peq" href="api/reporte.md">⬇️ Reporte (.md)</a><button class="btn peq" onclick="window.print()">🖨️ Imprimir / PDF</button></div></div>
    <h1>📄 Reporte de desarrollo</h1>
    <p class="suave">${esc(r.perfil.nombre || r.usuario)} · generado ${new Date(r.generado * 1000).toLocaleString(LOC)}</p>
    <div class="stats">
      <div class="stat"><b>${d.minutos_30}</b><span>minutos (30 d)</span></div><div class="stat"><b>${d.dias_activos_14}/14</b><span>días activos</span></div>
      <div class="stat"><b>${pct(d.resultados.repaso)}</b><span>retención</span></div><div class="stat"><b>${pct(L.retencion_1dia)}</b><span>a 1-2 días</span></div>
      <div class="stat"><b>${L.recuerdo_mas_antiguo ? L.recuerdo_mas_antiguo.dias + " d" : "—"}</b><span>recuerdo más antiguo</span></div>
      <div class="stat"><b>${r.areas.reduce((s, a) => s + a.dominados, 0)}</b><span>temas dominados</span></div></div>
    <h2>🧑‍💼 Análisis de la IA</h2>
    <div class="tarjeta">${r.informe_ia ? `<div class="suave peq">Escrito el ${new Date(r.informe_ia.fecha * 1000).toLocaleString(LOC)}</div><div class="leccion" id="repIA"></div>` : `<p class="suave">Aún no hay análisis escrito.</p>`}
      <div class="fila no-imprimir"><button class="btn peq" id="repGen">${r.informe_ia ? "Rehacer" : "Escribir"} análisis con IA (3-5 min)</button><span id="repEstado" class="suave peq">${r.trabajo ? esc(textoEstado(r.trabajo)) : ""}</span></div></div>
    <h2>🚩 Necesidades</h2><div class="tarjeta">${r.necesidades.length ? `<ul class="consejos">${r.necesidades.map((n) => `<li>${esc(n)}</li>`).join("")}</ul>` : "<p>Nada urgente.</p>"}</div>
    <h2>✅ Recomendaciones</h2><div class="tarjeta"><ul class="consejos">${[...d.consejos.map((c) => md(c).replace(/^<p>|<\/p>\s*$/g, "")), ...r.plan.ajustes.map(esc)].map((c) => `<li>${c}</li>`).join("")}</ul></div>
    <h2>📈 Desarrollo por área</h2><div class="tarjeta">${barrasH(r.areas, { valor: (x) => x.dominio, max: 1, nombre: (x) => x.nombre, texto: (x) => `${pct(x.dominio)} · ${x.dominados}/${x.temas} temas` })}</div>
    <h2>⏱️ Corto y 🏛️ largo plazo</h2><div class="tarjeta"><table class="tabla"><tr><th>Medida</th><th>Valor</th></tr>
      <tr><td>Pulso diario (30 d)</td><td>${pct(L.pulso_media)}</td></tr><tr><td>Recuerdo a 1-2 días</td><td>${pct(L.retencion_1dia)} (${L.n_1dia})</td></tr>
      ${L.curva_edad.map((c) => `<tr><td>Aprendido hace ${c.edad}</td><td>${pct(c.retencion)} (${c.n})</td></tr>`).join("")}
      <tr><td>Temas de +1 mes en chequeos</td><td>${pct(L.chequeo_temas_viejos)} (${L.n_chequeo_viejos})</td></tr></table></div>
    <h2>🧠 Cómo aprendes</h2><div class="tarjeta">${d.metodos.length ? barrasH(d.metodos, { valor: (x) => x.min, nombre: (x) => x.nombre, texto: (x) => `${x.min} min · ${x.usos} veces` }) : "<p class='suave'>Sin datos aún.</p>"}
      <table class="tabla" style="margin-top:.6rem"><tr><th>Franja</th><th>Recuerdas</th><th>Minutos (30 d)</th></tr>${d.franjas.map((f) => `<tr><td>${f.franja}</td><td>${pct(f.retencion)} (${f.repasos})</td><td>${f.min}</td></tr>`).join("")}</table>
      <p class="peq">Sesión típica: ${d.sesiones.mediana} min · ${d.sesiones.por_semana} por semana · empiezas hacia las ${d.sesiones.hora_tipica ?? "—"}:00</p></div>
    ${htmlLectura(d.lectura)}
    <h2>🔄 Cambios en tu forma de aprender</h2><div class="tarjeta">${r.cambios.notas.length ? `<ul class="consejos">${r.cambios.notas.map((n) => `<li>${esc(n)}</li>`).join("")}</ul>` : `<p class="suave">Aún no hay suficientes semanas para comparar.</p>`}</div>
    <h2>🧪 Chequeos semanales</h2><div class="tarjeta">${r.chequeos.filter((c) => c.completado).map((c) => `<div class="fila entre peq"><span>Semana ${esc(c.semana)}</span><span>${pct(c.puntaje)} · ${c.retenidos} ✓ · ${c.olvidados} ✗</span></div>`).join("") || "<p class='suave'>Aún no hay chequeos completados.</p>"}</div>
    <h2>🗄️ Qué datos se guardan y cómo se usan</h2>
    <p class="suave peq">Todo vive solo en tu PC (carpeta <code>datos/</code>). Tus datos no se envían fuera: la IA es la tuya. Cada cuenta de Tailscale ve solo sus datos.</p>
    <div class="tarjeta" style="overflow-x:auto"><table class="tabla"><tr><th>Dato</th><th>Qué es</th><th>Para qué se usa</th><th>Registros</th></tr>
      ${r.diccionario.map((x) => `<tr><td><b>${esc(x.tabla)}</b></td><td>${esc(x.que)}</td><td>${esc(x.uso)}</td><td>${x.filas ?? "—"}</td></tr>`).join("")}</table></div>`;
  if (r.informe_ia) pintarMd($("#repIA"), r.informe_ia.texto);
  const seguir = async (id) => {
    await esperarTrabajo(id, (t) => { const e = $("#repEstado"); if (e) e.innerHTML = `<span class="cargando"></span> ${esc(textoEstado(t))}`; });
    refrescar();
  };
  $("#repGen").onclick = async () => { $("#repGen").disabled = true; try { const j = await api("reporte/ia", {}); await seguir(j.trabajo); } catch (e) { $("#repEstado").textContent = "Error: " + e.message; } };
  if (r.trabajo) seguir(r.trabajo.id).catch(() => {});
};

/* =============================== AJUSTES =============================== */
VISTAS.ajustes = async () => {
  const [yo, mapa, ia, cfg] = await Promise.all([api("yo"), api("mapa"), api("ia"), api("config")]);
  const p = yo.perfil;
  const mias = mapa.areas.filter((a) => esMia(a, yo));
  const filasArea = (as) => Object.entries(porGrupo(as)).map(([g, xs]) => `<div class="nivel-tit">${esc(g)}</div>${xs.map((a) => `
        <div class="fila entre" style="margin:.3rem 0"><span>${esc(a.icono)} ${esc(a.nombre)}</span>
        <div class="chips">${[0, 1, 2, 3].map((n) => `<button class="chip ${(p.pesos[a.id] ?? yo.prioridad?.[a.id] ?? 0) === n ? "activo" : ""}" data-area="${a.id}" data-n="${n}">${n}</button>`).join("")}</div></div>`).join("")}`).join("");
  vista.innerHTML = `<h1>⚙️ Ajustes y perfil</h1>
    ${cfg.editable ? `<div class="tarjeta" id="autoCfg"><b>🪄 Configuración automática</b>
      <p class="suave peq">Revisa qué tiene este PC (memoria, tarjeta gráfica, servidores de IA y sus modelos, buscador, Tailscale) y te
      propone la mejor configuración con los pasos para lo que falte. No lee tus archivos y el resultado se borra solo en 24 h.</p>
      <div id="autoCuerpo"><span class="cargando"></span></div></div>` : ""}
    <h2>🟢 Básico</h2>
    <div class="tarjeta"><b>Cuenta:</b> ${esc(yo.usuario)} ${yo.local ? `<span class="etq">en este PC</span>` : `<span class="etq">vía Tailscale</span>`}
      ${yo.local && yo.perfiles.length > 1 ? `<div style="margin-top:.5rem"><label>Perfil en este navegador</label><select id="perfilSel">${yo.perfiles.map((u) => `<option ${u === yo.usuario ? "selected" : ""}>${esc(u)}</option>`).join("")}</select></div>` : ""}
      <p class="suave peq" style="margin-bottom:0">Cada cuenta de Tailscale tiene su propio progreso. Todo se guarda en tu PC (carpeta <code>datos/</code>).</p></div>
    <div class="tarjeta"><b>Tu perfil (la IA lo lee para adaptar todo)</b>
      <label>Nombre</label><input type="text" id="pNombre" value="${esc(p.nombre)}">
      <label>Situación actual</label><textarea id="pSit">${esc(p.situacion)}</textarea>
      <label>Metas</label><textarea id="pMetas">${esc(p.metas)}</textarea>
      <label>Cómo te gusta aprender</label><input type="text" id="pEstilo" value="${esc(p.estilo)}">
      <div class="rejilla" style="margin-top:.4rem">
        <div><label>Lecciones nuevas por día</label><input type="number" id="pNuevos" min="1" max="8" value="${p.nuevos_dia}"></div>
        <div><label>Tarjetas nuevas por día</label><input type="number" id="pTarj" min="5" max="100" value="${p.tarjetas_nuevas_dia}"></div>
        <div><label>Meta de minutos por día</label><input type="number" id="pMin" min="10" max="600" value="${p.minutos_dia}"></div></div>
      <label class="fila" style="font-weight:500"><input type="checkbox" id="pLapiz" ${p.solo_lapiz ? "checked" : ""} style="width:auto;min-height:0"> Cuaderno: dibujar solo con el lápiz (el dedo desplaza la página)</label>
      <label class="fila" style="font-weight:500"><input type="checkbox" id="pDiaMax" ${p.dia_maxima ? "checked" : ""} style="width:auto;min-height:0"> 🔬 Dejar TODAS las lecciones del día listas a máxima profundidad en la actualización diaria (más horas de IA)</label>
      <div class="rejilla" style="margin-top:.4rem"><div><label>🧭 Cómo leer las lecciones</label><select id="pModoLect">
        <option value="auto" ${!p.modo_lectura || p.modo_lectura === "auto" ? "selected" : ""}>Automático: completa (paso a paso si no las terminas)</option>
        <option value="rapida" ${p.modo_lectura === "rapida" ? "selected" : ""}>🗺️ Empezar por la vista previa (10-15 min) y luego la completa</option>
        <option value="esencial" ${p.modo_lectura === "esencial" ? "selected" : ""}>📗 Esencial: lo central, lo opcional plegado</option>
        <option value="completo" ${p.modo_lectura === "completo" ? "selected" : ""}>📚 Completo: todo abierto</option></select></div></div>
      <div class="rejilla"><div><label>👣 Paso a paso (una parte a la vez, con «¿lo entendiste?»)</label><select id="pPaso">
        <option value="" ${p.paso_a_paso == null ? "selected" : ""}>Automático (si no terminas las lecciones)</option>
        <option value="si" ${p.paso_a_paso === true ? "selected" : ""}>Siempre</option>
        <option value="no" ${p.paso_a_paso === false ? "selected" : ""}>Nunca</option></select></div></div>
      <label class="fila" style="font-weight:500"><input type="checkbox" id="pDiag" ${p.diagnostico_previo !== false ? "checked" : ""} style="width:auto;min-height:0"> ⚡ Ofrecer un diagnóstico de 4 preguntas antes de leer (si ya lo sabes, te saltas la lectura)</label></div>
    <div class="tarjeta" style="cursor:pointer" onclick="ir('conexiones')"><b>🔔 Modo corto, avisos y ☁️ API de IA</b> <span class="etq">opcional</span>
      <p class="suave peq" style="margin:.3rem 0 0">Estudiar 10 minutos al día, recibir un recordatorio en el celular o usar una API de IA para ir más rápido. Todo apagado por defecto. Toca para configurarlo →</p></div>
    <div class="tarjeta"><b>Prioridad por área</b><p class="suave peq">0 = pausada · 1 = de fondo · 2 = importante · 3 = prioridad máxima. Consejo con evidencia: con idiomas, 1-2 activos en serio rinde más que 5 a la vez; los demás en 1 (mantenimiento).</p>
      ${mias.length ? filasArea(mias) : `<p>${SIN_AREAS}</p>`}</div>
    <div class="tarjeta"><b>🌍 Noticias por región</b><p class="suave peq">De dónde quieres tus noticias. 0 = no la quiero · 1 = poco · 2 = normal · 3 = primero.
      La 🌍 Global trae medios internacionales y ciencia; las regiones, lo de cada lugar.</p>
      <div id="regPrio"><span class="cargando"></span></div></div>
    <button class="btn pri" id="guardar" style="width:100%">Guardar perfil</button>
    <div class="tarjeta" style="margin-top:1rem"><b>🎨 Apariencia</b> <span class="suave peq">(se guarda en este navegador)</span>
      <label>Modo</label><div class="chips">${["auto", "light", "dark"].map((t) => `<button class="chip ${(leerLS("tema") || "auto") === t ? "activo" : ""}" data-tema-visual="${t}">${{ auto: "Automático", light: "Claro", dark: "Oscuro" }[t]}</button>`).join("")}</div>
      <label>Paleta</label><div class="chips" id="paletas"><span class="cargando"></span></div>
      <label>Color de acento propio</label><div class="fila"><input type="color" id="acento" value="${esc(leerLS("acento") || "#4f6df5")}" style="width:4rem;min-height:2.4rem;padding:.1rem">
        <button class="btn peq" id="acentoQuitar">Usar el de la paleta</button></div>
      <label>Tamaño de letra</label><div class="chips">${[[0.9, "Pequeña"], [1, "Normal"], [1.15, "Grande"], [1.3, "Muy grande"]].map(([v, n]) => `<button class="chip ${(+leerLS("escala") || 1) === v ? "activo" : ""}" data-escala="${v}">${n}</button>`).join("")}</div></div>
    <div class="tarjeta"><b>📄 Tus datos</b><p class="suave peq">Descarga todo lo que la Academia guarda de ti y un reporte de desarrollo, necesidades y recomendaciones.</p>
      <div class="fila"><button class="btn peq" onclick="ir('reporte')">Ver reporte</button><a class="btn peq" href="api/exportar">⬇️ Descargar mis datos (ZIP)</a></div></div>
    <details class="avanzado"><summary><h2 style="display:inline">🛠️ Avanzado</h2> <span class="suave peq">IA, ritmo de trabajo, actualización diaria y versión</span></summary>
    ${cfg.editable ? `<div class="tarjeta" style="margin-top:1rem"><b>🤖 Dónde se procesa la IA</b>
      <div class="modo-actual"><span class="etq ${cfg.modo === "remoto" ? "medio" : "bien"}">${cfg.modo === "remoto" ? "🌐 Remoto" : "💻 Local"}</span>
        <span class="peq">${cfg.modo === "remoto" ? "Tus datos se guardan en este PC; la IA y el buscador son de otro PC del tailnet." : "Tus datos y la IA están en este mismo PC."}</span></div>
      <table class="tabla peq" style="margin-top:.5rem"><tr><td>Servidor de IA</td><td><code>${esc(cfg.ia_url)}</code></td></tr>
        <tr><td>Modelo</td><td><code>${esc(cfg.modelo)}</code>${cfg.modelo_ligero ? ` · ligero <code>${esc(cfg.modelo_ligero)}</code>` : ""}</td></tr>
        <tr><td>Buscador web</td><td>${cfg.searx_url ? `<code>${esc(cfg.searx_url)}</code>` : "sin búsqueda web"}</td></tr>
        <tr><td>Monitor de GPU (aigate)</td><td>${cfg.aigate_url ? `<code>${esc(cfg.aigate_url)}</code>` : "—"}</td></tr>
        <tr><td>Tareas a la vez</td><td>${cfg.trabajos_paralelos || 1} en este equipo${cfg.trabajos_nube ? ` + ${cfg.trabajos_nube} en la API de la nube` : ""}</td></tr>
        <tr><td>Lecciones por adelantado / persona</td><td>${cfg.lecciones_adelantadas ?? 2}</td></tr>
        <tr><td>Noticias a fondo por persona/día</td><td>${cfg.noticias_a_fondo_por_persona || 8}</td></tr>
        <tr><td>Se prepara solo para</td><td>quien usó la Academia en las últimas 48 h</td></tr>
        <tr><td>Si otra app usa la IA</td><td>${cfg.permitir_interrumpir === true ? "me pregunta si interrumpir" : "espera en la cola (nunca interrumpe)"}</td></tr>
        <tr><td>Datos</td><td><code>${esc(cfg.datos)}</code></td></tr></table>
      <p class="peq suave">Cargados ahora en ese servidor: ${esc(ia.cargados.join(", ") || "ninguno")}.</p>
      ${cfg.editable ? `<details id="cfgIA"><summary class="btn peq" style="display:inline-flex">⚙️ Cambiar</summary>
        <p class="peq" style="margin-top:.8rem"><b>1. Elige un modo</b> (rellena todo; luego puedes ajustar):</p>
        <div class="presets">${Object.entries(cfg.presets).map(([k, p]) => `<button class="preset" data-preset="${k}">${p.modo === "remoto" ? "🌐" : "💻"} ${esc(p.nombre_preset)}</button>`).join("")}</div>
        <div class="fila" style="margin:.5rem 0"><button class="btn peq" id="cDetectar">🔍 Detectar servidores de IA</button><span id="cDet" class="suave peq"></span></div>
        <p class="peq"><b>2. Revisa los datos</b></p>
        <label>Servidor de IA (compatible con OpenAI)</label><input type="text" id="cIa" value="${esc(cfg.ia_url)}">
        <label>Modelo principal</label><input type="text" id="cMod" value="${esc(cfg.modelo)}" list="cModelos"><datalist id="cModelos"></datalist>
        <label>Modelo ligero (opcional)</label><input type="text" id="cLig" value="${esc(cfg.modelo_ligero || "")}" list="cModelos">
        <label>Buscador SearXNG (vacío = sin búsqueda web)</label><input type="text" id="cSx" value="${esc(cfg.searx_url || "")}">
        <label>Monitor de GPU tipo aigate (opcional: URL que responde «ocupado» cuando no se debe usar la IA, p. ej. jugando)</label><input type="text" id="cAg" value="${esc(cfg.aigate_url || "")}">
        <label>Tareas de IA a la vez (igual a los «slots» del servidor: llama-server --parallel N)</label>
        <input type="number" id="cPar" min="1" max="4" value="${cfg.trabajos_paralelos || 1}" style="width:6rem">
        <label>Tareas a la vez en la API de la nube (aparte de las de arriba; 0 = sin carril propio. Si la API no responde, esas tareas pasan a las locales)</label>
        <input type="number" id="cNube" min="0" max="6" value="${cfg.trabajos_nube || 0}" style="width:6rem">
        <label>Lecciones preparadas por adelantado por persona (sin leer; cada una ~45 min de IA)</label>
        <input type="number" id="cAde" min="0" max="6" value="${cfg.lecciones_adelantadas ?? 2}" style="width:6rem">
        <label>Noticias a máxima profundidad por persona y día (cada una ~15 min de IA)</label>
        <input type="number" id="cNot" min="1" max="60" value="${cfg.noticias_a_fondo_por_persona || 8}" style="width:6rem">
        <label class="fila" style="font-weight:500"><input type="checkbox" id="cInt" ${cfg.permitir_interrumpir === true ? "checked" : ""} style="width:auto;min-height:0"> Preguntarme si quiero interrumpir otra app que esté usando la IA (si está apagado, mi tarea siempre espera en la cola y la otra termina completa)</label>
        <p class="peq"><b>3. Prueba y guarda</b> (aplica al instante, sin reiniciar)</p>
        <div class="fila"><button class="btn" id="cProbar">🔌 Probar conexión</button><button class="btn pri" id="cGuardar">💾 Guardar</button><span id="cEstado" class="suave peq"></span></div></details>`
        : ""}</div>
    <div class="tarjeta" id="instalacion"><b>🧩 Esta instalación</b><div id="verInfo" class="peq suave"><span class="cargando"></span></div></div>
    <div class="tarjeta" id="regAdmin"><b>🗺️ Regiones y fuentes de noticias</b>
      <p class="suave peq">Agrega o quita regiones y sus fuentes (RSS). Solo se descargan las regiones que alguien tiene en prioridad 1 o más.</p>
      <div id="regLista"><span class="cargando"></span></div></div>
    <div class="tarjeta"><b>🕕 Actualización diaria</b><p class="suave peq">Una vez al día, a esta hora, se descargan las fuentes de noticias, la IA analiza las más importantes, escribe las síntesis y prepara tus lecciones del día. Si el PC está apagado a esa hora, lo hace apenas prenda.
      Última: ${yo.diaria_ultima ? new Date(yo.diaria_ultima * 1000).toLocaleString(LOC, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "nunca"}.</p>
      <div class="fila"><input type="time" id="horaDiaria" value="${esc(yo.hora_diaria)}" style="width:auto">
      <button class="chip" data-hora="06:00">6:00 a. m.</button><button class="chip" data-hora="22:00">10:00 p. m.</button>
      <button class="btn peq" id="guardarHora">Guardar hora</button></div></div>` : `<p class="suave">La configuración avanzada solo la cambia quien administra esta Academia (desde su PC).</p>`}
    </details>`;
  const pesos = Object.assign({}, p.pesos);
  const prioReg = {};
  pintarRegiones(prioReg, cfg.editable);
  pintarVersion(cfg.editable, false);
  if (cfg.editable) pintarAuto();
  if (leerLS("ajustes_avanzado") === "1") $(".avanzado").open = true;
  $(".avanzado").addEventListener("toggle", (e) => escribirLS("ajustes_avanzado", e.target.open ? "1" : ""));
  cargarTemas().then((ts) => {
    const act = leerLS("paleta") || "clasico";
    $("#paletas").innerHTML = ts.map((t) => `<button class="chip ${t.id === act ? "activo" : ""}" data-paleta="${esc(t.id)}" title="${esc(t.descripcion || "")}">${esc(t.nombre)}</button>`).join("");
    $$("[data-paleta]").forEach((b) => (b.onclick = () => { escribirLS("paleta", b.dataset.paleta); aplicarApariencia(); $$("[data-paleta]").forEach((x) => x.classList.toggle("activo", x === b)); }));
  });
  $("#acento").oninput = (e) => { escribirLS("acento", e.target.value); aplicarApariencia(); };
  $("#acentoQuitar").onclick = () => { escribirLS("acento", ""); aplicarApariencia(); };
  $$("[data-escala]").forEach((b) => (b.onclick = () => { escribirLS("escala", b.dataset.escala); aplicarApariencia(); $$("[data-escala]").forEach((x) => x.classList.toggle("activo", x === b)); }));
  if (cfg.editable) {
    let cmodo = cfg.modo || "local";
    const rellenar = (p) => {
      cmodo = p.modo; $("#cIa").value = p.ia_url; $("#cMod").value = p.modelo; $("#cLig").value = p.modelo_ligero || "";
      $("#cSx").value = p.searx_url || ""; $("#cAg").value = p.aigate_url || ""; $("#cInt").checked = p.permitir_interrumpir === true;
    };
    $$("[data-preset]").forEach((b) => (b.onclick = () => { rellenar(cfg.presets[b.dataset.preset]); $$("[data-preset]").forEach((x) => x.classList.toggle("activo", x === b)); $("#cProbar").click(); }));
    $("#cDetectar").onclick = async () => {
      $("#cDet").innerHTML = `<span class="cargando"></span> Buscando…`;
      const r = await api("config/detectar", {});
      $("#cDet").innerHTML = r.servidores.map((x) => x.lugar === "tailnet" && !x.disponible ? `❌ ${esc(x.nombre)}: no responde` :
        `<button class="chip" data-url="${esc(x.url)}">✅ ${esc(x.nombre)} · ${x.modelos.length} modelos</button>`).join(" ") || "No encontré servidores de IA en este PC.";
      $$("[data-url]", $("#cDet")).forEach((b) => (b.onclick = () => {
        const x = r.servidores.find((s_) => s_.url === b.dataset.url);
        $("#cIa").value = x.url; cmodo = x.lugar === "tailnet" ? "remoto" : "local";
        $("#cModelos").innerHTML = x.modelos.map((m) => `<option value="${esc(m)}">`).join("");
        if (!x.modelos.includes($("#cMod").value)) $("#cMod").value = x.modelos.find((m) => /gemma/i.test(m)) || x.modelos[0] || "";
        aviso("Servidor elegido: revisa el modelo y pulsa Guardar");
      }));
    };
    const datosC = () => ({ modo: cmodo, ia_url: $("#cIa").value.trim(), modelo: $("#cMod").value.trim(), modelo_ligero: $("#cLig").value.trim(),
      searx_url: $("#cSx").value.trim(), aigate_url: $("#cAg").value.trim(), permitir_interrumpir: $("#cInt").checked, trabajos_paralelos: +$("#cPar").value || 1, trabajos_nube: +$("#cNube").value || 0, noticias_a_fondo_por_persona: +$("#cNot").value || 8, lecciones_adelantadas: +$("#cAde").value });
    $("#cProbar").onclick = async () => {
      $("#cEstado").innerHTML = `<span class="cargando"></span> Probando…`;
      const r = await api("config/probar", datosC());
      if (r.modelos) $("#cModelos").innerHTML = r.modelos.map((m) => `<option value="${esc(m)}">`).join("");
      $("#cEstado").innerHTML = `${r.ia ? `✅ IA: ${r.modelos.length} modelos` : `❌ IA: ${esc(r.ia_error)}`}${r.buscador === undefined ? "" : r.buscador ? " · ✅ buscador" : ` · ❌ buscador: ${esc(r.buscador_error || "")}`}`;
    };
    $("#cGuardar").onclick = async () => {
      const r = await api("config", datosC()).catch((e) => ({ error: e.message }));
      if (r.error) return aviso(r.error);
      aviso("✅ Configuración guardada: ya está en uso"); enrutar();
    };
  }
  $$("[data-hora]").forEach((b) => (b.onclick = () => ($("#horaDiaria").value = b.dataset.hora)));
  if ($("#guardarHora")) $("#guardarHora").onclick = async () => {
    try { const r = await api("horario", { hora: $("#horaDiaria").value }); aviso(`🕕 Actualización diaria a las ${r.hora}`); } catch (e) { aviso(e.message); }
  };
  $$("[data-area]").forEach((b) => (b.onclick = () => { pesos[b.dataset.area] = +b.dataset.n; $$(`[data-area="${b.dataset.area}"]`).forEach((x) => x.classList.toggle("activo", x === b)); }));
  $$("[data-tema-visual]").forEach((b) => (b.onclick = () => { escribirLS("tema", b.dataset.temaVisual); aplicarTema(); enrutar(); }));
  if ($("#perfilSel")) $("#perfilSel").onchange = (e) => { document.cookie = "perfil=" + encodeURIComponent(e.target.value) + ";path=/;max-age=31536000"; location.reload(); };
  $("#guardar").onclick = async () => {
    await api("perfil", { nombre: $("#pNombre").value, situacion: $("#pSit").value, metas: $("#pMetas").value, estilo: $("#pEstilo").value,
      nuevos_dia: +$("#pNuevos").value, tarjetas_nuevas_dia: +$("#pTarj").value, minutos_dia: +$("#pMin").value,
      solo_lapiz: $("#pLapiz").checked, dia_maxima: $("#pDiaMax").checked, modo_lectura: $("#pModoLect").value,
      paso_a_paso: { si: true, no: false }[$("#pPaso").value] ?? null, diagnostico_previo: $("#pDiag").checked, pesos, regiones: prioReg, configurado: true });
    aviso("✅ Perfil guardado"); ir("hoy");
  };
};
const FUENTE = "https://github.com/Anexolocuz/academia-comunidad";   // AGPL-3.0 §13: enlace al código fuente
async function pintarVersion(admin, buscar) {
  const el = $("#verInfo"); if (!el) return;
  el.insertAdjacentHTML("afterend", $("#fuenteInfo") ? "" : `<p class="peq suave" id="fuenteInfo">Software libre (AGPL-3.0) · <a href="${FUENTE}" target="_blank" rel="noopener">código fuente y manuales</a> · solo se dona el software: cada quien lo corre en su propio PC.</p>`);
  const v = await api("version" + (buscar ? "?buscar=1" : "")).catch(() => ({ git: false }));
  if (!v.git) {
    el.innerHTML = `Versión <b>${esc(v.version)}</b>. ` + (v.docker ? "Corre en Docker: para actualizar, <code>docker compose pull && docker compose up -d</code> (tus datos están en el volumen y no se tocan)."
      : "Instalada sin Git (por ZIP): para actualizar, descarga el ZIP nuevo y copia tu carpeta <code>datos/</code>."); return;
  }
  const repo = (v.remoto || "").replace(/^https:\/\/github.com\//, "").replace(/\.git$/, "");
  el.innerHTML = `Versión <b>${esc(v.version)}</b> · commit <code>${esc(v.commit)}</code> del ${new Date(v.fecha).toLocaleDateString(LOC)} — «${esc(v.mensaje)}»<br>
    Código: <code>${esc(repo || "sin remoto")}</code> (rama ${esc(v.rama)}). Es el mismo código para todas las instalaciones; solo cambia la configuración de arriba y los datos.
    ${v.cambios_locales ? `<br>⚠️ Hay cambios locales sin subir en el código.` : ""}
    ${v.buscado === undefined ? `<div class="fila" style="margin-top:.5rem"><button class="btn peq" id="verBuscar">🔄 Buscar actualizaciones</button></div>` :
      !v.buscado ? `<br>❌ No pude consultar GitHub (sin conexión o sin permiso).` :
      v.atras ? `<br><b>Hay ${v.atras} cambio(s) nuevo(s):</b><ul>${v.novedades.map((n) => `<li>${esc(n)}</li>`).join("")}</ul>
        ${admin ? `<button class="btn pri peq" id="verActualizar">⬇️ Actualizar ahora</button>` : ""}` :
      `<br>✅ Al día con GitHub${v.adelante ? ` (este PC tiene ${v.adelante} cambio(s) que aún no están en GitHub)` : ""}.`}`;
  if ($("#verBuscar")) $("#verBuscar").onclick = () => { el.innerHTML = `<span class="cargando"></span> Consultando GitHub…`; pintarVersion(admin, true); };
  if ($("#verActualizar")) $("#verActualizar").onclick = async () => {
    const r = await api("actualizar", {}).catch((e) => ({ error: e.message }));
    if (r.error) return aviso(r.error);
    el.innerHTML = `<span class="cargando"></span> Actualizado; reiniciando…`;
    setTimeout(() => location.reload(), 5000);
  };
}

/* ---------- regiones de noticias: prioridad por persona (Básico) y catálogo (Avanzado, administrador) ---------- */
async function pintarRegiones(prioReg, admin) {
  const r = await api("regiones").catch(() => null); if (!r) return;
  r.regiones.forEach((x) => { REGIONES[x.id] = x; prioReg[x.id] = x.prioridad; });
  $("#regPrio").innerHTML = r.regiones.map((x) => `<div class="fila entre" style="margin:.3rem 0">
      <span title="${esc(x.descripcion || "")}">${esc(x.icono)} ${esc(x.nombre)} <span class="suave peq">· ${x.fuentes.length} fuentes</span></span>
      <div class="chips">${[0, 1, 2, 3].map((n) => `<button class="chip ${x.prioridad === n ? "activo" : ""}" data-reg="${esc(x.id)}" data-n="${n}">${n}</button>`).join("")}</div></div>`).join("");
  $$("[data-reg]").forEach((b) => (b.onclick = () => { prioReg[b.dataset.reg] = +b.dataset.n; $$(`[data-reg="${CSS.escape(b.dataset.reg)}"]`).forEach((x) => x.classList.toggle("activo", x === b)); }));
  if (!admin || !$("#regLista")) return;
  const idiomas = ["es", "en", "pt", "fr", "de", "it"];
  $("#regLista").innerHTML = r.regiones.map((x) => `<details class="region"><summary><b>${esc(x.icono)} ${esc(x.nombre)}</b> <span class="suave peq">${x.fuentes.length} fuentes</span></summary>
      <ul class="peq" style="margin:.4rem 0">${x.fuentes.map((f) => `<li class="fila entre"><span><a href="${escUrl(f.u)}" target="_blank" rel="noopener">${esc(f.n)}</a> <span class="suave">· ${esc(f.idioma || "")} · peso ${f.peso}${f.propia ? " · agregada" : ""}</span></span>
        <button class="btn fantasma peq" data-quitar-fuente="${esc(f.u)}" title="Quitar">🗑️</button></li>`).join("") || "<li class='suave'>Sin fuentes.</li>"}</ul>
      <div class="rejilla"><div><label>Nombre</label><input type="text" class="fNom" placeholder="p. ej. El Universo"></div>
        <div><label>Dirección del RSS</label><input type="text" class="fUrl" placeholder="https://…/rss"></div>
        <div><label>Idioma · peso</label><div class="fila"><select class="fIdi">${idiomas.map((i) => `<option>${i}</option>`).join("")}</select>
          <select class="fPeso"><option value="1">1</option><option value="2" selected>2</option><option value="3">3</option></select></div></div></div>
      <div class="fila" style="margin-top:.4rem"><button class="btn peq" data-probar="${esc(x.id)}">🔌 Probar</button><button class="btn pri peq" data-agregar="${esc(x.id)}">➕ Agregar fuente</button>
        ${x.id !== "global" ? `<button class="btn fantasma peq" data-quitar-region="${esc(x.id)}">Quitar región</button>` : ""}<span class="suave peq fEstado"></span></div></details>`).join("") + `
    <div class="fila" style="margin-top:.8rem"><input type="text" id="rIco" value="📍" style="width:4rem"><input type="text" id="rNom" placeholder="Nueva región (p. ej. Ecuador)" style="flex:1">
      <button class="btn peq" id="rAgregar">➕ Agregar región</button></div>
    <p class="peq suave" style="margin-top:.6rem">Para perfiles nuevos: ${Object.entries(r.por_defecto).map(([k, v]) => `${esc(REGIONES[k]?.icono || k)} ${v}`).join(" · ")}
      <button class="btn fantasma peq" id="rDefecto">Usar mis prioridades de arriba</button></p>`;
  const caja = (b) => b.closest("details");
  const datosF = (b) => ({ region: b.dataset.probar || b.dataset.agregar, n: $(".fNom", caja(b)).value.trim(), u: $(".fUrl", caja(b)).value.trim(),
    idioma: $(".fIdi", caja(b)).value, peso: +$(".fPeso", caja(b)).value });
  $$("[data-probar]").forEach((b) => (b.onclick = async () => {
    const st = $(".fEstado", caja(b)); st.innerHTML = `<span class="cargando"></span>`;
    const x = await api("regiones/fuente/probar", datosF(b)).catch((e) => ({ error: e.message }));
    st.innerHTML = x.error ? `❌ ${esc(x.error)}` : `✅ ${x.noticias} noticias · «${esc(x.ejemplos[0] || "")}»`;
  }));
  $$("[data-agregar]").forEach((b) => (b.onclick = async () => {
    const st = $(".fEstado", caja(b)); st.innerHTML = `<span class="cargando"></span>`;
    const x = await api("regiones/fuente", datosF(b)).catch((e) => ({ error: e.message }));
    if (x.error) { st.textContent = "❌ " + x.error; return; }
    aviso(`✅ Fuente agregada (${x.noticias} noticias)`); pintarRegiones(prioReg, admin);
  }));
  $$("[data-quitar-fuente]").forEach((b) => (b.onclick = async () => {
    if (!(await preguntarSiNo("🗑️ ¿Quitar esta fuente?", "Deja de descargarse para todos. Puedes volver a agregarla cuando quieras.", "Sí, quitar", "No"))) return;
    await api("regiones/fuente/borrar", { u: b.dataset.quitarFuente }); pintarRegiones(prioReg, admin);
  }));
  $$("[data-quitar-region]").forEach((b) => (b.onclick = async () => {
    if (!(await preguntarSiNo("🗑️ ¿Quitar esta región?", "Desaparece con sus fuentes para todas las personas de esta Academia. Las noticias ya guardadas no se borran.", "Sí, quitar", "No"))) return;
    await api("regiones/region/borrar", { id: b.dataset.quitarRegion }); pintarRegiones(prioReg, admin);
  }));
  $("#rAgregar").onclick = async () => {
    const x = await api("regiones/region", { nombre: $("#rNom").value, icono: $("#rIco").value }).catch((e) => ({ error: e.message }));
    if (x.error) return aviso(x.error);
    aviso("✅ Región agregada: ahora agrégale fuentes"); pintarRegiones(prioReg, admin);
  };
  $("#rDefecto").onclick = async () => { await api("config", { regiones_por_defecto: prioReg }); aviso("✅ Guardado para perfiles nuevos"); pintarRegiones(prioReg, admin); };
}

/* ---------- apariencia: modo, paletas (web/temas/*.json), acento y tamaño de letra ---------- */
function leerLS(k) { try { return localStorage.getItem(k) || ""; } catch (e) { return ""; } }
function escribirLS(k, v) { try { v ? localStorage.setItem(k, v) : localStorage.removeItem(k); } catch (e) {} }
function aplicarTema() {
  const t = leerLS("tema") || "auto";
  if (t === "auto") document.documentElement.removeAttribute("data-theme"); else document.documentElement.dataset.theme = t;
  aplicarApariencia();
}
let _temas = null;
const _paletas = {};
async function cargarTemas() {
  if (!_temas) _temas = await fetch("temas/index.json").then((r) => r.json()).catch(() => [{ id: "clasico", nombre: "Clásica" }]);
  return _temas;
}
async function aplicarApariencia() {
  const raiz = document.documentElement, pal = leerLS("paleta") || "clasico", acento = leerLS("acento");
  raiz.style.cssText = "";
  raiz.style.fontSize = (+leerLS("escala") || 1) * 100 + "%";
  if (pal !== "clasico") {
    _paletas[pal] = _paletas[pal] || (await fetch(`temas/${encodeURIComponent(pal)}.json`).then((r) => r.json()).catch(() => ({})));
    const oscuro = raiz.dataset.theme === "dark" || (!raiz.dataset.theme && matchMedia("(prefers-color-scheme: dark)").matches);
    for (const [k, v] of Object.entries((oscuro ? _paletas[pal].oscuro : _paletas[pal].claro) || {}))
      if (/^[a-z0-9-]+$/.test(k)) raiz.style.setProperty("--" + k, String(v));
  }
  if (acento) raiz.style.setProperty("--acento", acento);
}
matchMedia("(prefers-color-scheme: dark)").addEventListener?.("change", aplicarApariencia);

/* ---------- auto-configuración: escanear (sí/no) → recomendación → aplicar (sí/no) ---------- */
function preguntarSiNo(titulo, texto, si = "Sí", no = "No") {
  return new Promise((ok) => {
    modal(`<h2>${titulo}</h2><div class="peq">${texto}</div><div class="fila" style="margin-top:1rem">
      <button class="btn pri" id="sn_si">${si}</button><button class="btn" id="sn_no">${no}</button></div>`);
    $("#sn_si").onclick = () => { cerrarModal(); ok(true); };
    $("#sn_no").onclick = () => { cerrarModal(); ok(false); };
  });
}
async function pintarAuto() {
  const el = $("#autoCuerpo"); if (!el) return;
  const r = await api("escaneo").catch((e) => ({ error: e.message }));
  const g = r.guardado;
  if (!g) {
    el.innerHTML = `<button class="btn pri" id="autoEscanear">🔍 Escanear mi PC</button>`;
  } else {
    const e = g.escaneo, rec = g.recomendacion, c = rec.config, horas = Math.max(0, Math.round((g.expira - Date.now() / 1000) / 3600));
    el.innerHTML = `<p class="peq">Escaneado el ${new Date(g.creado * 1000).toLocaleString(LOC, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
      · se borra solo en ~${horas} h.</p>
      <table class="tabla peq"><tr><td>Sistema</td><td>${esc(e.sistema)} · ${esc(e.procesador.nombre)} (${e.procesador.nucleos} hilos)</td></tr>
        <tr><td>Memoria</td><td>${e.ram_gb ?? "?"} GB RAM${e.graficas.length ? " · " + e.graficas.map((x) => esc(x.nombre) + (x.vram_gb ? ` (${x.vram_gb} GB)` : "")).join(", ") : " · sin tarjeta gráfica detectada"}</td></tr>
        <tr><td>Servidores de IA</td><td>${e.servidores_ia.map((s_) => `${esc(s_.nombre)} · ${s_.modelos.length} modelos`).join("<br>") || "ninguno"}</td></tr>
        <tr><td>Buscador</td><td>${e.buscadores.map(esc).join(", ") || "ninguno"}</td></tr></table>
      <p class="peq" style="margin-bottom:.2rem"><b>Qué puedes usar</b></p><ul class="consejos peq">${rec.capacidades.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>
      ${rec.pasos.length ? `<p class="peq" style="margin-bottom:.2rem"><b>Cómo completarlo</b></p><ol class="peq">${rec.pasos.map((x) => `<li>${md(x).replace(/^<p>|<\/p>\s*$/g, "")}</li>`).join("")}</ol>` : ""}
      <p class="peq" style="margin-bottom:.2rem"><b>Configuración recomendada</b></p>
      <table class="tabla peq">${Object.entries(c).map(([k, v]) => `<tr><td><code>${esc(k)}</code></td><td>${esc(v === "" ? "—" : v)}</td></tr>`).join("")}</table>
      <div class="fila" style="margin-top:.6rem"><button class="btn pri" id="autoAplicar">✅ Aplicar esta configuración</button>
        <button class="btn" id="autoEscanear">🔄 Escanear de nuevo</button><button class="btn fantasma peq" id="autoBorrar">🗑️ Borrar el escaneo ya</button></div>`;
  }
  $("#autoEscanear").onclick = async () => {
    if (!(await preguntarSiNo("🔍 ¿Escanear este PC?", `Voy a revisar, <b>solo en este PC</b>: sistema, procesador, memoria, tarjeta gráfica,
      servidores de IA locales y sus modelos, buscador SearXNG, Tailscale y Docker.<br><br>No se leen tus archivos ni se envía nada a internet.
      El resultado se guarda en <code>datos/escaneo.json</code> y <b>se borra solo en 24 horas</b>.`, "Sí, escanear", "No"))) return;
    el.innerHTML = `<span class="cargando"></span> Escaneando (unos segundos)…`;
    const x = await api("escaneo", { confirmar: true }).catch((e) => ({ error: e.message }));
    if (x.error) aviso(x.error);
    pintarAuto();
  };
  if ($("#autoAplicar")) $("#autoAplicar").onclick = async () => {
    if (!(await preguntarSiNo("✅ ¿Aplicar la configuración recomendada?", "Reemplaza el servidor de IA, los modelos, el buscador y el ritmo de trabajo por los de la tabla. Tus datos y tu progreso no se tocan; puedes cambiarlo después en Avanzado.", "Sí, aplicar", "No"))) return;
    const x = await api("escaneo/aplicar", { confirmar: true }).catch((e) => ({ error: e.message }));
    if (x.error) return aviso(x.error);
    aviso("✅ Configuración aplicada: ya está en uso"); enrutar();
  };
  if ($("#autoBorrar")) $("#autoBorrar").onclick = async () => { await api("escaneo", {}, "DELETE"); aviso("🗑️ Escaneo borrado"); pintarAuto(); };
}

/* =============================== arranque =============================== */
aplicarTema();
if ("speechSynthesis" in window) speechSynthesis.getVoices();
api("yo").then((y) => { E.wpm = y.wpm; }).catch(() => {});   // tu velocidad de lectura (umbral de inactividad)
api("regiones").then((r) => r.regiones.forEach((x) => (REGIONES[x.id] = x))).catch(() => {});
api("mapa").then((m) => { E.mapa = m.areas; m.areas.forEach((a) => (AREA_ES[a.id] = a)); }).catch(() => {});
// esperar a que carguen todos los scripts (cuaderno.js registra su vista después de este archivo)
document.addEventListener("DOMContentLoaded", () => { enrutar(); refrescarIA(); });
