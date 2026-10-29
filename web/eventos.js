/* Academia — eventos indirectos de la interfaz (fase F1). Se carga después de app.js. Solo registra DOS cosas, ambas sin texto
   de la persona: cuántos segundos estuvo en cada vista y a qué vista fue después (con eso se mide cuánto tarda en decidir y si
   sigue lo que «Hoy» le sugiere). Se manda en lotes cada 30 s y al cerrar. Si apagas la familia «Decisión y comportamiento» en 🔬 «Qué sabe el sistema de ti», el servidor deja de guardarlos. */
"use strict";

const EVT = { cola: [], ruta: "", t0: Date.now(), activo: true };
const evtRaiz = (r) => (r || "hoy").split("?")[0].split("/")[0] || "hoy";
const evtRuta = () => decodeURIComponent((location.hash || "#/hoy").replace(/^#\/?/, "")).split("?")[0].slice(0, 60);

function evtSalida() {
  const seg = Math.min(600, Math.round((Date.now() - EVT.t0) / 1000));
  const nueva = evtRuta();
  if (EVT.ruta && seg >= 1) {
    EVT.cola.push({ tipo: "vista", objeto: evtRaiz(EVT.ruta), valor: seg });
    if (nueva !== EVT.ruta) EVT.cola.push({ tipo: "navega", objeto: nueva, valor: seg, contexto: { desde: evtRaiz(EVT.ruta) } });
  }
  EVT.ruta = nueva; EVT.t0 = Date.now();
}

function evtEnviar(final) {
  if (!EVT.cola.length || EVT.apagado) return;
  const lote = EVT.cola.splice(0, 50);
  fetch("api/evento", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ eventos: lote }),
    keepalive: !!final }).catch(() => {});
}

if (typeof ACT !== "undefined") {
  EVT.ruta = evtRuta();
  addEventListener("hashchange", () => { evtSalida(); });
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) { evtSalida(); evtEnviar(true); } else EVT.t0 = Date.now();
  });
  addEventListener("pagehide", () => { evtSalida(); evtEnviar(true); });
  setInterval(() => evtEnviar(false), 30000);
}
