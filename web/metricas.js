/* Academia — 🔬 «Qué sabe el sistema de ti» (fase F1). Se carga después de app.js y usa sus utilidades (api, esc, VISTAS, vista, aviso).
   Muestra TODO lo que el sistema deduce de ESTA persona: cada métrica con su origen (directa o indirecta), su fórmula, la ventana, cuánta muestra
   tiene, su confianza y la decisión que alimenta. La persona puede marcar «esto está mal», ignorar una métrica o apagar una familia entera:
   las de confianza baja nunca deciden nada. Cada perfil ve solo lo suyo. */
"use strict";

const MT = {
  conf: { "sin datos": ["", "⚪ sin datos"], baja: ["mal", "🔴 baja"], media: ["medio", "🟡 media"], alta: ["bien", "🟢 alta"] },
  orden: ["memoria", "lectura", "habito", "estilo", "contenido", "metas", "decision", "sistema"],
};
const mtValor = (m) => {
  if (m.error) return `<span class="ac-baja">error</span>`;
  if (m.valor == null) return `<span class="suave">—</span>`;
  const v = typeof m.valor === "number" && m.unidad === "%" ? Math.round(m.valor * 1000) / 10 : m.valor;
  return `<b style="font-size:1.25rem">${esc(typeof v === "number" ? v.toLocaleString(LOC) : v)}</b> <span class="suave peq">${esc(m.unidad === "%" ? "%" : m.unidad || "")}</span>`;
};

function mtTarjeta(m) {
  const c = MT.conf[m.confianza] || MT.conf["sin datos"], aj = m.ajuste;
  return `<li style="cursor:default;display:block;${aj || m.familia_apagada ? "opacity:.6" : ""}" data-id="${esc(m.id)}">
    <div class="fila entre" style="gap:.5rem;align-items:flex-start">
      <div style="flex:1;min-width:0"><b>${esc(m.nombre)}</b>
        <span class="etq" title="${m.origen === "D" ? "Directa: la diste tú de forma explícita" : "Indirecta: se deduce de cómo estudias"}">${m.origen === "D" ? "directa" : "indirecta"}</span>
        <span class="etq ${c[0]}">${c[1]}</span>${m.usable ? "" : ` <span class="etq" title="No decide nada: poca muestra, la ignoraste o está apagada">no decide</span>`}
        ${aj ? `<span class="etq medio">${aj.estado === "mal" ? "marcada como errónea" : "ignorada"}</span>` : ""}</div>
      <div style="text-align:right">${mtValor(m)}</div></div>
    <details style="margin-top:.3rem"><summary class="suave peq">Cómo se calcula · muestra n = ${m.n} · ventana: ${esc(m.ventana)}</summary>
      <p class="peq" style="margin:.4rem 0"><b>Fórmula:</b> ${esc(m.formula)}</p>
      <p class="peq" style="margin:.2rem 0"><b>Qué decide:</b> ${esc(m.decide)}</p>
      <p class="peq" style="margin:.2rem 0"><b>Confianza:</b> ${esc(m.confianza)} (mínimo para decidir: ${m.n_min} de muestra).</p>
      <div class="fila" style="gap:.4rem;flex-wrap:wrap;margin-top:.4rem">
        ${aj ? `<button class="btn peq" data-aj="ok">↩️ Quitar mi ajuste</button>` : `<button class="btn peq" data-aj="mal">⚠️ Esto está mal</button>
          <button class="btn peq" data-aj="ignorar">🙈 Ignorar</button>`}
        <button class="btn peq" data-tend="1">📈 Tendencia</button></div>
      <div class="mt-tend"></div></details></li>`;
}

VISTAS.metricas = async () => {
  const pintar = async () => {
    const d = await api("metricas");
    const off = new Set(d.metricas.filter((m) => m.familia_apagada).map((m) => m.familia));
    const por = {};
    d.metricas.forEach((m) => (por[m.familia] = por[m.familia] || []).push(m));
    const ev = d.eventos;
    vista.innerHTML = `<div class="fila"><button class="btn peq pri" onclick="ir('tablero')">📊 Ver el tablero (metas, fechas y tendencias)</button></div>
      <h1>🔬 Qué sabe el sistema de ti</h1>
      <p class="suave peq">Todo lo que la Academia deduce de cómo estudias, y de dónde sale. <b>Directa</b> = la diste tú (una nota, un puntaje). <b>Indirecta</b> = se
        deduce de tu comportamiento (tiempo, lectura, a dónde vas). Si algo está mal, márcalo: el sistema deja de usarlo para decidir. Solo tú ves esto.</p>
      <div class="stats">
        <div class="stat"><b>${d.resumen.total}</b><span>métricas</span></div>
        <div class="stat"><b>${d.resumen.usables}</b><span>con confianza suficiente para decidir</span></div>
        <div class="stat"><b>${d.resumen.baja}</b><span>con poca muestra (no deciden)</span></div>
        <div class="stat"><b>${d.resumen.sin_datos}</b><span>sin datos todavía</span></div>
        <div class="stat"><b>${ev.total}</b><span>eventos en tu línea de tiempo</span></div></div>
      ${MT.orden.filter((f) => por[f]).map((f) => `<h2>${esc(d.familias[f])} <span class="suave peq">(${por[f].length})</span>
        <button class="btn peq" data-fam="${f}" data-off="${off.has(f) ? 0 : 1}">${off.has(f) ? "▶️ Encender familia" : "⏸ Apagar familia"}</button></h2>
        <ul class="temas">${por[f].map(mtTarjeta).join("")}</ul>`).join("")}
      <p class="suave peq">Las métricas de confianza <b>baja</b> o <b>sin datos</b> se muestran para que veas qué se mide, pero no deciden nada hasta tener muestra suficiente.</p>`;
    vista.querySelectorAll("[data-aj]").forEach((b) => b.onclick = async () => {
      await api("metricas/ajustar", { id: b.closest("li").dataset.id, estado: b.dataset.aj }); aviso("Anotado"); pintar();
    });
    vista.querySelectorAll("[data-fam]").forEach((b) => b.onclick = async () => {
      await api("metricas/ajustar", { familia: b.dataset.fam, apagada: b.dataset.off === "1" }); pintar();
    });
    vista.querySelectorAll("[data-tend]").forEach((b) => b.onclick = async () => {
      const li = b.closest("li"), cont = li.querySelector(".mt-tend"), t = await api("metricas/tendencia?id=" + encodeURIComponent(li.dataset.id));
      cont.innerHTML = t.serie.length ? `<p class="peq suave">${t.serie.map((x) => `${esc(x.dia)}: <b>${esc(x.valor ?? "—")}</b>`).join(" · ")}</p>`
        : `<p class="peq suave">Aún no hay historial: se guarda una foto por día.</p>`;
    });
  };
  await pintar();
};


/* =============================== 📊 TABLERO (metas con fecha estimada, dominio en el tiempo, tendencias) =============================== */
function lineasDominio(serie) {
  if (!serie || serie.length < 2 || !serie.some((x) => x.explorados > 0)) return `<p class="vacio">Aún no hay temas explorados para dibujar.</p>`;
  const W = 640, H = 200, ml = 30, mr = 108, mt = 12, mb = 26, max = Math.max(...serie.map((x) => x.explorados), 1);
  const X = (i) => ml + i / (serie.length - 1) * (W - ml - mr), Y = (v) => mt + (1 - v / max) * (H - mt - mb);
  const camino = (k) => serie.map((x, i) => `${i ? "L" : "M"}${X(i).toFixed(1)},${Y(x[k]).toFixed(1)}`).join("");
  const f = (x) => new Date(x.hasta + "T12:00:00").toLocaleDateString(LOC, { day: "numeric", month: "short" });
  const ult = serie[serie.length - 1];
  const ejes = [0, 0.5, 1].map((t) => `<line class="gp-red" x1="${ml}" x2="${W - mr}" y1="${Y(max * t)}" y2="${Y(max * t)}"/><text class="gp-eje" x="${ml - 4}" y="${Y(max * t) + 4}" text-anchor="end">${Math.round(max * t)}</text>`).join("");
  const marcas = serie.map((x, i) => (i % 2 === 0 ? `<text class="gp-eje" x="${X(i)}" y="${H - 8}" text-anchor="middle">${f(x)}</text>` : "")).join("");
  const puntos = serie.map((x, i) => `<rect x="${X(i) - 10}" y="0" width="20" height="${H}" fill="transparent"${tip(`Hasta el ${f(x)}: ${x.dominados} dominados · ${x.explorados} explorados`)}/>`).join("");
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Temas dominados y explorados por semana">${ejes}${marcas}
    <path d="${camino("explorados")}" class="gp-media"/><path d="${camino("dominados")}" class="gp-linea"/>
    <text class="gp-eje" x="${W - mr + 6}" y="${Y(ult.dominados) + 4}" fill="currentColor">${ult.dominados} dominados</text>
    <text class="gp-eje" x="${W - mr + 6}" y="${Y(ult.explorados) - 4}">${ult.explorados} explorados</text>${puntos}</svg>
    <div class="gp-leyenda peq suave"><span><i class="gp-l-precio"></i>dominados (quiz ≥ 80 % o marcados)</span><span><i class="gp-l-media"></i>explorados (abiertos o leídos)</span></div>
    <details class="peq"><summary class="suave">Ver como tabla</summary><table class="tabla"><tr><th>Hasta</th><th>Dominados</th><th>Explorados</th></tr>${serie.map((x) => `<tr><td>${f(x)}</td><td>${x.dominados}</td><td>${x.explorados}</td></tr>`).join("")}</table></details>`;
}
function estadosHtml(e) {
  if (!e || !e.con_evidencia) return `<p class="suave">Aún no hay temas con evidencia.</p>`;
  const max = Math.max(1, ...e.por_nivel.map((x) => x.temas));
  return `${e.por_nivel.map((x) => `<div class="graf-h"${tip(`${x.temas} temas en el estado ${x.nivel} (${x.etiqueta})`)}><span class="n">${x.nivel} · ${esc(x.etiqueta)}</span>
      <div class="pista"><i style="width:${Math.max(x.temas ? 2 : 0, x.temas / max * 100)}%"></i></div><b>${x.temas}</b></div>`).join("")}
    <p class="suave peq">Leer es <i>exposición</i> (1), no dominio. 2 recuerda · 3 comprende · 4 aplica · 5 domina (con las tres pruebas diferidas aprobadas a los 3, 14 y 45 días). Solo mide: no cambia lo que te toca hoy.</p>
    ${e.pendientes.length ? `<h3>🧬 Pruebas diferidas que ya tocan</h3><ul class="temas">${e.pendientes.slice(0, 8).map((p) => `<li data-ir-tema="${esc(p.tema)}" tabindex="0"><span style="flex:1"><b>${esc(p.titulo)}</b><br><span class="suave peq">prueba de los ${p.dias} días${p.vencida_hace_dias ? ` · pasaron ${p.vencida_hace_dias} día(s) desde que tocaba` : ""}</span></span><span class="etq medio">disponible</span></li>`).join("")}</ul>` : ""}`;
}
function metaHtml(m) {
  const fecha = (iso) => iso ? new Date(iso + "T12:00:00").toLocaleDateString(LOC, { month: "long", year: "numeric" }) : null;
  const anios = (iso) => iso ? (new Date(iso) - Date.now()) / (365 * 86400000) : null;
  const lejos = anios(m.fecha) != null && anios(m.fecha) > 5;
  const rango = m.fecha && m.pronto !== m.tarde ? ` (entre ${fecha(m.pronto)} y ${fecha(m.tarde)})` : "";
  const conf = { baja: ["Poca confianza", "mal"], media: ["Confianza media", "medio"], alta: ["Buena confianza", "bien"] }[m.confianza];
  return `<div class="tarjeta"><div class="fila entre"><b>🎯 ${esc(m.titulo)}</b><span class="etq ${conf[1]}">${conf[0]}</span></div>
    <div class="barra-prog" style="margin:.4rem 0"><i style="width:${Math.max(1, m.progreso * 100)}%"></i></div>
    <div class="peq"><b>${Math.round(m.progreso * 100)} %</b> · ${m.temas_hechos} de ${m.temas_total} temas dominados · faltan <b>${m.faltan}</b></div>
    <p class="peq" style="margin:.4rem 0 0">${m.fecha ? (lejos ? `A tu ritmo actual tardaría <b>más de 5 años</b> (${esc(fecha(m.fecha))}${esc(rango)}).` : `A tu ritmo actual la completarías hacia <b>${esc(fecha(m.fecha))}</b>${esc(rango)}.`) : "Sin temas dominados estudiando en las últimas semanas: no hay ritmo con el que proyectar una fecha."}</p>
    <p class="suave peq" style="margin:.2rem 0">${esc(m.nota)}</p>
    ${m.faltan ? `<p class="peq" style="margin:.2rem 0">⏱️ <b>Para terminarla en 12 meses:</b> unos ${acNum2(m.para_12_meses.temas_semana)} temas por semana (≈ ${m.para_12_meses.min_semana} min a la semana con tus ${m.para_12_meses.min_por_tema} min por tema).</p>` : ""}</div>`;
}
VISTAS.tablero = async () => {
  const t = await api("tablero");
  const sem = t.series.semanas, fsem = (x) => new Date(x.desde + "T12:00:00").toLocaleDateString(LOC, { day: "numeric", month: "short" });
  vista.innerHTML = `<div class="fila entre no-imprimir"><button class="btn fantasma peq" onclick="ir('metricas')">← 🔬 Todas las métricas</button><button class="btn peq" onclick="window.print()">🖨️ Imprimir / PDF</button></div>
    <h1>📊 Tablero</h1>
    <p class="suave peq">Lo importante de un vistazo: hacia dónde vas en cada meta y a qué ritmo, lo que realmente dominas frente a lo que solo exploraste, y cómo se mueven tu tiempo y tu memoria. Todo sale de tus datos; las fechas son <b>estimaciones a tu ritmo actual</b>, no promesas.</p>
    <div class="stats">
      <div class="stat"><b>${t.analitica.minutos_30}</b><span>minutos (30 d)</span></div><div class="stat"><b>${t.analitica.dias_activos_14}/14</b><span>días activos</span></div>
      <div class="stat"><b>${pct(t.resultados.repaso)}</b><span>retención en repasos</span></div><div class="stat"><b>${t.pendientes}</b><span>repasos atrasados</span></div></div>
    <h2>🎯 Tus metas y cuándo llegarías</h2>
    ${t.metas.length ? t.metas.map(metaHtml).join("") : `<div class="tarjeta"><p class="suave">Aún no tienes metas activas. Crea una en 🎯 Objetivos y aquí verás su avance y la fecha estimada.</p></div>`}
    <h2>🧬 Estados de dominio (0 a 5)</h2>
    <div class="tarjeta">${estadosHtml(t.estados)}</div>
    <h2>📈 Dominado frente a explorado</h2><div class="tarjeta">${lineasDominio(t.dominio_tiempo)}</div>
    <h2>⏱️ Tiempo, memoria y constancia</h2>${reporteGraficos(t.series)}
    <h2>🧠 Cuánto recuerdas según la edad del aprendizaje</h2>
    <div class="tarjeta">${t.curva_edad.length ? barrasV(t.curva_edad, { alto: 120, max: 1, etiqueta: (x) => x.edad, valor: (x) => x.retencion, tipTxt: (x) => `Aprendido hace ${x.edad}: ${pct(x.retencion)} recordado (${x.n} repasos)` })
      + `<p class="suave peq">Cada barra es la parte de los repasos que acertaste según hace cuánto aprendiste el tema. Si baja con la edad, el olvido te gana y toca repasar antes.</p>` : `<p class="suave">Aún no hay suficientes repasos.</p>`}</div>
    ${reporteCalibracion(t.calibracion)}`;
  $$("[data-ir-tema]").forEach((li) => { li.onclick = () => ir("tema/" + li.dataset.irTema); li.onkeydown = (e) => { if (e.key === "Enter") ir("tema/" + li.dataset.irTema); }; });
};
