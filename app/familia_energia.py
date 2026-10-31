"""Familia «Energía eléctrica del mundo y su competencia» (2026-10-29).

Datos para `acciones.FAMILIAS`: quién genera, transmite, distribuye y fabrica los equipos de la electricidad en cada
región, más los fondos del sector. Cada símbolo se comprobó contra Yahoo Finance (precio y al menos 20 sesiones de
historia) antes de ponerlo aquí; los que no existen o ya no cotizan no están. Las compañías de solo gas, petróleo,
agua o telecomunicaciones se dejaron fuera aunque se llamen «energía».

`nucleo` son las empresas que la persona pidió expresamente: entran a la lista principal con alertas y pronóstico de IA.
El resto queda en el grupo plegable «Energía eléctrica» de la lista (sin alertas de movimiento ni IA diaria), para que
60 o 230 símbolos no saturen la pantalla, las alertas de Telegram ni la GPU.
"""

NUCLEO = ["GEV", "TLN", "CEG", "VST", "NEE", "ISA.CL", "CELSIA.CL", "GEB.CL"]


def _g(titulo, defecto, notas, simbolos):
    """Un grupo: cada símbolo lleva su nota propia o, si no, la del grupo."""
    return (titulo, [(s, notas.get(s) or defecto) for s in simbolos])


GRUPOS = [
    _g("⭐ Las que pediste", "", {
        "GEV": "Turbinas de gas, eólica y equipos de red (la antigua GE); gran beneficiada por la demanda de los centros de datos.",
        "TLN": "Generadora independiente (nuclear y gas) que vende electricidad directamente a centros de datos.",
        "CEG": "Mayor operadora de plantas nucleares de EE. UU. y gran vendedora de energía sin emisiones.",
        "VST": "Generadora independiente (gas, nuclear) y comercializadora minorista de electricidad en EE. UU.",
        "NEE": "La mayor eléctrica de EE. UU. (Florida Power & Light) y líder mundial en eólica y solar.",
        "ISA.CL": "Interconexión Eléctrica: transmisión de energía y concesiones viales en Colombia y América Latina.",
        "CELSIA.CL": "Generación y distribución de energía, con énfasis en fuentes limpias, en Colombia y Centroamérica.",
        "GEB.CL": "Grupo Energía Bogotá: transmisión de electricidad, y transporte y distribución de gas natural.",
    }, NUCLEO),

    _g("🇺🇸 Generadoras independientes y nuclear (rivales de CEG, VST y TLN)", "Generadora independiente de EE. UU.", {
        "NRG": "Generadora y comercializadora de electricidad en EE. UU.; rival directa de Vistra.",
        "AES": "Generación y distribución en varios países, con fuerte apuesta por renovables y almacenamiento.",
        "OKLO": "Reactores nucleares pequeños (aún sin ingresos): apuesta de alto riesgo.",
        "SMR": "NuScale: reactores modulares pequeños; empresa en etapa temprana.",
        "BWXT": "Componentes y combustible para reactores navales y comerciales.",
        "CCJ": "Cameco: una de las mayores productoras de uranio del mundo.",
        "LEU": "Centrus: enriquecimiento de uranio para reactores.",
        "UEC": "Uranium Energy: minera de uranio de EE. UU.",
        "NNE": "Nano Nuclear: microrreactores; etapa muy temprana."},
       ["NRG", "AES", "OKLO", "SMR", "BWXT", "CCJ", "LEU", "UEC", "NNE"]),

    _g("🇺🇸 Eléctricas reguladas de EE. UU. (rivales de NextEra)", "Eléctrica regulada de EE. UU. (generación, transmisión y distribución).", {
        "AEP": "Dueña de la mayor red de transmisión de EE. UU.",
        "DUK": "Duke Energy: una de las mayores eléctricas del país, en el sureste.",
        "SO": "Southern Company: eléctrica del sureste con nuevos reactores nucleares (Vogtle).",
        "D": "Dominion: eléctrica de Virginia, el mayor mercado de centros de datos del mundo.",
        "EXC": "Exelon: solo transmisión y distribución, sin plantas propias.",
        "XEL": "Xcel Energy: eléctrica del centro-norte con mucha eólica.",
        "PCG": "PG&E: California; riesgo de incendios forestales y de regulación.",
        "EIX": "Edison International: sur de California; también expuesta a incendios.",
        "SRE": "Sempra: California, Texas (Oncor) y gas natural licuado."},
       ["AEP", "DUK", "SO", "D", "EXC", "XEL", "PCG", "EIX", "SRE", "ED", "PEG", "WEC", "ES", "DTE", "AEE", "ETR", "PPL",
        "FE", "CNP", "CMS", "EVRG", "LNT", "NI", "OGE", "PNW", "IDA", "POR", "AVA", "BKH", "NWE", "OTTR", "MGEE", "UTL"]),

    _g("🏗️ Equipos de red, turbinas y respaldo (rivales de GE Vernova)", "Fabricante de equipos para generar o mover electricidad.", {
        "ETN": "Eaton: equipos eléctricos y de distribución de energía.",
        "VRT": "Vertiv: energía y refrigeración para centros de datos.",
        "PWR": "Quanta: construye líneas de transmisión y subestaciones.",
        "HUBB": "Hubbell: componentes de red eléctrica y servicios públicos.",
        "POWL": "Powell: tableros y equipos de maniobra de media tensión.",
        "MYRG": "MYR Group: contratista de líneas de transmisión y distribución.",
        "NVT": "nVent: protección y conexión eléctrica.",
        "GNRC": "Generac: generadores de respaldo.",
        "AMSC": "American Superconductor: tecnología para estabilizar redes y eólica.",
        "ITRI": "Itron: medidores y tecnología de redes inteligentes.",
        "CAT": "Caterpillar: grupos electrógenos y turbinas, demandados por centros de datos.",
        "CMI": "Cummins: generadores y motores de respaldo.",
        "ENR.DE": "Siemens Energy: turbinas, transformadores y equipos de red; rival directa de GE Vernova.",
        "SU.PA": "Schneider Electric: gestión de energía y automatización.",
        "ABBN.SW": "ABB: electrificación, automatización y robótica.",
        "PRY.MI": "Prysmian: cables de energía de alta tensión y submarinos.",
        "NEX.PA": "Nexans: cables y sistemas de electrificación.",
        "WRT1V.HE": "Wärtsilä: motores para centrales eléctricas flexibles y almacenamiento.",
        "6501.T": "Hitachi: incluye Hitachi Energy (transformadores y red).",
        "6503.T": "Mitsubishi Electric: equipos eléctricos y automatización.",
        "7011.T": "Mitsubishi Heavy: turbinas de gas y equipos nucleares.",
        "034020.KS": "Doosan Enerbility: turbinas, reactores y calderas de Corea del Sur.",
        "267260.KS": "HD Hyundai Electric: transformadores, muy demandados en EE. UU.",
        "010120.KS": "LS Electric: equipos de distribución y cables.",
        "600089.SS": "TBEA: transformadores y equipos de transmisión chinos.",
        "WEGE3.SA": "WEG: motores y transformadores de Brasil.",
        "POWERINDIA.NS": "Hitachi Energy India: transformadores y equipos de red."},
       ["ETN", "VRT", "PWR", "HUBB", "POWL", "MYRG", "NVT", "GNRC", "AMSC", "ITRI", "CAT", "CMI", "ENR.DE", "SU.PA",
        "ABBN.SW", "PRY.MI", "NEX.PA", "WRT1V.HE", "6501.T", "6503.T", "7011.T", "034020.KS", "267260.KS", "010120.KS",
        "600089.SS", "WEGE3.SA", "POWERINDIA.NS"]),

    _g("☀️ Solar, viento y almacenamiento en baterías", "Energía renovable o su equipo.", {
        "FSLR": "First Solar: módulos solares fabricados en EE. UU.",
        "ENPH": "Enphase: microinversores y baterías para solar residencial.",
        "SEDG": "SolarEdge: inversores solares.",
        "RUN": "Sunrun: paneles solares residenciales por suscripción.",
        "NXT": "Nextpower (antes Nextracker): seguidores solares.",
        "ARRY": "Array: seguidores solares.",
        "SHLS": "Shoals: cableado eléctrico para plantas solares.",
        "BE": "Bloom Energy: celdas de combustible para centros de datos.",
        "FLNC": "Fluence: sistemas de almacenamiento en baterías.",
        "STEM": "Stem: software y almacenamiento de energía.",
        "EOSE": "Eos: baterías de zinc para almacenamiento de larga duración.",
        "PLUG": "Plug Power: hidrógeno y celdas de combustible.",
        "BEP": "Brookfield Renewable: hidroeléctrica, eólica y solar en varios continentes.",
        "CWEN": "Clearway: propietaria de parques solares y eólicos.",
        "ORA": "Ormat: geotermia.",
        "HASI": "HASI: financia proyectos de energía limpia.",
        "VWS.CO": "Vestas: la mayor fabricante de turbinas eólicas de Occidente.",
        "ORSTED.CO": "Ørsted: líder mundial en eólica marina.",
        "NDX1.DE": "Nordex: turbinas eólicas terrestres.",
        "EDPR.LS": "EDP Renovables: eólica y solar en Europa, EE. UU. y Brasil.",
        "2208.HK": "Goldwind: turbinas eólicas de China.",
        "601615.SS": "Ming Yang: turbinas eólicas chinas.",
        "SUZLON.NS": "Suzlon: turbinas eólicas de India.",
        "300274.SZ": "Sungrow: inversores solares y almacenamiento.",
        "601012.SS": "LONGi: una de las mayores fabricantes de paneles solares del mundo.",
        "002459.SZ": "JA Solar: paneles solares chinos.",
        "300750.SZ": "CATL: la mayor fabricante de baterías del mundo.",
        "SLR.MC": "Solaria: plantas solares en España.",
        "GRE.MC": "Grenergy: solar y almacenamiento, con mucho negocio en Chile.",
        "SCATC.OL": "Scatec: solar, eólica e hidroeléctrica en mercados emergentes.",
        "ENLT": "Enlight: renovables de Israel con proyectos en EE. UU. y Europa."},
       ["FSLR", "ENPH", "SEDG", "RUN", "NXT", "ARRY", "SHLS", "BE", "FLNC", "STEM", "EOSE", "PLUG", "BEP", "CWEN", "ORA",
        "HASI", "VWS.CO", "ORSTED.CO", "NDX1.DE", "EDPR.LS", "2208.HK", "601615.SS", "SUZLON.NS", "300274.SZ",
        "601012.SS", "002459.SZ", "300750.SZ", "SLR.MC", "GRE.MC", "SCATC.OL", "ENLT"]),

    _g("🇨🇦 Canadá", "Eléctrica o generadora de Canadá.", {
        "FTS.TO": "Fortis: eléctricas reguladas en Canadá, EE. UU. y el Caribe.",
        "EMA.TO": "Emera: eléctrica de Nueva Escocia y Florida.",
        "H.TO": "Hydro One: transmisión y distribución en Ontario.",
        "AQN.TO": "Algonquin: eléctricas y renovables.",
        "CPX.TO": "Capital Power: generación en Canadá y EE. UU.",
        "NPI.TO": "Northland Power: eólica marina y solar.",
        "TA.TO": "TransAlta: hidroeléctrica, gas y renovables.",
        "ACO-X.TO": "ATCO: infraestructura de electricidad y gas."},
       ["FTS.TO", "EMA.TO", "H.TO", "AQN.TO", "CPX.TO", "NPI.TO", "TA.TO", "ACO-X.TO"]),

    _g("🇬🇧 Reino Unido", "Energía eléctrica del Reino Unido.", {
        "NG.L": "National Grid: redes de transmisión del Reino Unido y Nueva York.",
        "SSE.L": "SSE: renovables y redes.",
        "CNA.L": "Centrica: comercialización minorista (British Gas).",
        "DRX.L": "Drax: central de biomasa.",
        "UKW.L": "Greencoat UK Wind: fondo de parques eólicos.",
        "TRIG.L": "The Renewables Infrastructure Group: fondo de renovables."},
       ["NG.L", "SSE.L", "CNA.L", "DRX.L", "UKW.L", "TRIG.L"]),

    _g("🇪🇸🇵🇹 Península Ibérica", "Eléctrica de España o Portugal.", {
        "IBE.MC": "Iberdrola: gran operadora de redes y renovables en España, Reino Unido, EE. UU. y Brasil.",
        "ELE.MC": "Endesa: la mayor eléctrica de España (filial de Enel).",
        "RED.MC": "Redeia: opera la red de transmisión de España.",
        "NTGY.MC": "Naturgy: electricidad y gas.",
        "EDP.LS": "EDP: eléctrica de Portugal con renovables en el mundo."},
       ["IBE.MC", "ELE.MC", "RED.MC", "NTGY.MC", "EDP.LS"]),

    _g("🇮🇹🇫🇷🇩🇪 Italia, Francia y Alemania", "Eléctrica europea.", {
        "ENEL.MI": "Enel: la mayor eléctrica de Europa; presente en América Latina.",
        "TRN.MI": "Terna: red de transmisión de Italia.",
        "A2A.MI": "A2A: electricidad, gas y residuos en Italia.",
        "ERG.MI": "ERG: eólica y solar.",
        "ENGI.PA": "Engie: electricidad, gas y servicios de energía.",
        "RWE.DE": "RWE: la mayor generadora de Alemania, ahora con eólica marina y solar.",
        "EOAN.DE": "E.ON: redes de distribución y comercialización."},
       ["ENEL.MI", "TRN.MI", "A2A.MI", "ERG.MI", "ENGI.PA", "RWE.DE", "EOAN.DE"]),

    _g("🇪🇺 Resto de Europa", "Eléctrica europea.", {
        "FORTUM.HE": "Fortum: nuclear, hidroeléctrica y renovables en los países nórdicos.",
        "VER.VI": "Verbund: casi toda hidroeléctrica, en Austria.",
        "ELI.BR": "Elia: operadora de la red de Bélgica y de parte de Alemania.",
        "BKW.SW": "BKW: electricidad y servicios de energía en Suiza.",
        "PGE.WA": "PGE: la mayor eléctrica de Polonia, aún muy ligada al carbón.",
        "TPE.WA": "Tauron: electricidad y minería de carbón en Polonia.",
        "CEZ.PR": "ČEZ: nuclear y carbón en la República Checa.",
        "PPC.AT": "PPC: principal eléctrica de Grecia.",
        "H2O.RO": "Hidroelectrica: la mayor productora de Rumania.",
        "SNN.RO": "Nuclearelectrica: reactores de Cernavodă, Rumania."},
       ["FORTUM.HE", "VER.VI", "ELI.BR", "BKW.SW", "PGE.WA", "TPE.WA", "CEZ.PR", "PPC.AT", "H2O.RO", "SNN.RO"]),

    _g("🇯🇵🇰🇷 Japón y Corea del Sur", "Eléctrica regional de Japón.", {
        "9501.T": "Tokyo Electric (TEPCO): la mayor eléctrica de Japón; operó Fukushima.",
        "9502.T": "Chubu Electric: región de Nagoya.",
        "9503.T": "Kansai Electric: región de Osaka, con muchas plantas nucleares.",
        "9506.T": "Tohoku Electric: norte de Japón.",
        "9504.T": "Chugoku Electric: oeste de Japón.",
        "9505.T": "Hokuriku Electric: costa del mar de Japón.",
        "9508.T": "Kyushu Electric: isla de Kyushu, con nuclear.",
        "9507.T": "Shikoku Electric: isla de Shikoku.",
        "9511.T": "Okinawa Electric: islas de Okinawa.",
        "9513.T": "J-Power: generadora mayorista.",
        "015760.KS": "KEPCO: monopolio de transmisión y distribución de Corea del Sur."},
       ["9501.T", "9502.T", "9503.T", "9506.T", "9504.T", "9505.T", "9508.T", "9507.T", "9511.T", "9513.T", "015760.KS"]),

    _g("🇨🇳 China y Hong Kong", "Generadora china.", {
        "600900.SS": "China Yangtze Power: opera las presas de las Tres Gargantas.",
        "600025.SS": "Huaneng Lancang: hidroeléctricas del río Mekong/Lancang.",
        "600905.SS": "China Three Gorges Renewables.",
        "601985.SS": "China National Nuclear Power.",
        "600886.SS": "SDIC Power: hidroeléctrica, térmica y renovables.",
        "600011.SS": "Huaneng Power: una de las mayores generadoras de China (cotización en Shanghái).",
        "0902.HK": "Huaneng Power: la misma compañía, en Hong Kong.",
        "0991.HK": "Datang International: generación a base de carbón y renovables.",
        "0836.HK": "China Resources Power: térmica y renovables.",
        "0916.HK": "China Longyuan: la mayor operadora eólica de China.",
        "1816.HK": "CGN Power: plantas nucleares de China.",
        "2380.HK": "China Power International.",
        "0956.HK": "China Suntien Green Energy: eólica y gas.",
        "1798.HK": "Datang Renewable Power: eólica.",
        "0002.HK": "CLP Holdings: eléctrica de Hong Kong, con negocios en Asia.",
        "0006.HK": "Power Assets: inversiones en redes eléctricas en varios países."},
       ["600900.SS", "600025.SS", "600905.SS", "601985.SS", "600886.SS", "600011.SS", "0902.HK", "0991.HK", "0836.HK",
        "0916.HK", "1816.HK", "2380.HK", "0956.HK", "1798.HK", "0002.HK", "0006.HK"]),

    _g("🇮🇳 India", "Eléctrica de India.", {
        "NTPC.NS": "NTPC: la mayor generadora de India.",
        "POWERGRID.NS": "Power Grid: la red nacional de transmisión.",
        "TATAPOWER.NS": "Tata Power: generación, distribución y renovables.",
        "ADANIGREEN.NS": "Adani Green: solar y eólica a gran escala.",
        "ADANIPOWER.NS": "Adani Power: térmica a carbón.",
        "NHPC.NS": "NHPC: hidroeléctrica.",
        "JSWENERGY.NS": "JSW Energy: generación y renovables.",
        "TORNTPOWER.NS": "Torrent Power: generación y distribución.",
        "CESC.NS": "CESC: distribución en Calcuta."},
       ["NTPC.NS", "POWERGRID.NS", "TATAPOWER.NS", "ADANIGREEN.NS", "ADANIPOWER.NS", "NHPC.NS", "JSWENERGY.NS",
        "TORNTPOWER.NS", "CESC.NS"]),

    _g("🌏 Sudeste asiático, Oceanía, Medio Oriente y Turquía", "Eléctrica o generadora regional.", {
        "5347.KL": "Tenaga Nasional: eléctrica de Malasia.",
        "EGCO.BK": "EGCO: generadora de Tailandia.",
        "GULF.BK": "Gulf Development: generación de electricidad en Tailandia.",
        "BGRIM.BK": "B.Grimm Power: generación en Tailandia.",
        "RATCH.BK": "Ratch Group: generación en Tailandia y la región.",
        "GPSC.BK": "Global Power Synergy: generación de PTT en Tailandia.",
        "PGEO.JK": "Pertamina Geothermal: geotermia de Indonesia.",
        "U96.SI": "Sembcorp: energía y agua en Singapur, India y China.",
        "AGL.AX": "AGL: la mayor generadora y comercializadora de Australia.",
        "ORG.AX": "Origin Energy: electricidad y gas en Australia.",
        "MEZ.AX": "Meridian Energy: hidroeléctrica y eólica de Nueva Zelanda (cotiza en Australia).",
        "MCY.NZ": "Mercury: hidroeléctrica de Nueva Zelanda.",
        "CEN.NZ": "Contact Energy: electricidad en Nueva Zelanda.",
        "GNE.NZ": "Genesis Energy: electricidad y gas en Nueva Zelanda.",
        "5110.SR": "Saudi Energy Company: eléctrica nacional de Arabia Saudita.",
        "2082.SR": "ACWA Power: generación y desalinización en Medio Oriente y África.",
        "AKENR.IS": "Akenerji: generadora de Turquía.",
        "ODAS.IS": "Odaş: generadora de Turquía.",
        "ZOREN.IS": "Zorlu Enerji: generadora de Turquía."},
       ["5347.KL", "EGCO.BK", "GULF.BK", "BGRIM.BK", "RATCH.BK", "GPSC.BK", "PGEO.JK", "U96.SI", "AGL.AX", "ORG.AX",
        "MEZ.AX", "MCY.NZ", "CEN.NZ", "GNE.NZ", "5110.SR", "2082.SR", "AKENR.IS", "ODAS.IS", "ZOREN.IS"]),

    _g("🌎 Latinoamérica (además de Colombia)", "Eléctrica de América Latina.", {
        "AXIA3.SA": "AXIA Energia (antes Eletrobras): la mayor generadora de Brasil.",
        "CPFE3.SA": "CPFL: distribución y generación en Brasil.",
        "EGIE3.SA": "Engie Brasil: generación y transmisión.",
        "TAEE11.SA": "Taesa: transmisión en Brasil.",
        "CMIG4.SA": "Cemig: eléctrica de Minas Gerais.",
        "CPLE3.SA": "Copel: eléctrica del estado de Paraná.",
        "ENGI11.SA": "Energisa: distribución en Brasil.",
        "ENEV3.SA": "Eneva: generación térmica.",
        "EQTL3.SA": "Equatorial: distribución en el norte de Brasil.",
        "AURE3.SA": "Auren: renovables.",
        "ALUP11.SA": "Alupar: transmisión y generación.",
        "ENELCHILE.SN": "Enel Chile: generación y distribución.",
        "COLBUN.SN": "Colbún: generadora de Chile.",
        "ENELAM.SN": "Enel Américas: las eléctricas de Enel en varios países de América Latina.",
        "CGE.SN": "CGE: distribución en Chile.",
        "PAM": "Pampa Energía: una de las mayores generadoras de Argentina.",
        "EDN": "Edenor: distribución en Buenos Aires.",
        "CEPU": "Central Puerto: generadora de Argentina."},
       ["AXIA3.SA", "CPFE3.SA", "EGIE3.SA", "TAEE11.SA", "CMIG4.SA", "CPLE3.SA", "ENGI11.SA", "ENEV3.SA", "EQTL3.SA",
        "AURE3.SA", "ALUP11.SA", "ENELCHILE.SN", "COLBUN.SN", "ENELAM.SN", "CGE.SN", "PAM", "EDN", "CEPU"]),

    _g("📊 Fondos del sector eléctrico", "Fondo temático de energía.", {
        "XLU": "Las eléctricas del S&P 500 en un solo fondo.",
        "VPU": "Utilities de EE. UU. (Vanguard).",
        "ICLN": "Energía limpia del mundo (iShares).",
        "GRID": "Infraestructura de redes inteligentes.",
        "URA": "Uranio y nuclear (Global X).",
        "URNM": "Mineras de uranio.",
        "NLR": "Uranio y energía nuclear (VanEck).",
        "NUKZ": "Renacimiento nuclear.",
        "TAN": "Energía solar.",
        "FAN": "Energía eólica.",
        "PBW": "Energía limpia (WilderHill).",
        "QCLN": "Energía limpia (Nasdaq Clean Edge)."},
       ["XLU", "VPU", "ICLN", "GRID", "URA", "URNM", "NLR", "NUKZ", "TAN", "FAN", "PBW", "QCLN"]),
]

FAMILIA = {
    "clave": "energia",
    "icono": "⚡",
    "nombre": "Energía eléctrica del mundo y su competencia",
    "descripcion": ("Quién genera, transmite, distribuye y fabrica los equipos de la electricidad en cada región, y los fondos "
                    "del sector. Las empresas que pediste (⭐) van a tu lista con alertas y pronóstico; el resto queda en el "
                    "grupo plegable «⚡ Energía eléctrica» sin alertas de movimiento ni IA diaria. Toca una para ver su precio, "
                    "sus velas y pronosticarla cuando quieras."),
    "ancla": None,          # sin índice ancla: ningún miembro entra en la rutina diaria de la IA
    "nucleo": NUCLEO,       # estos sí: lista principal, alertas y pronóstico diario
    "grupos": GRUPOS,
}


# ── Tipo de energía (segundo nivel de agrupación) ────────────────────────────────────────────────
# Clasificación por el negocio principal de cada compañía; es una guía didáctica, no una auditoría: las eléctricas que
# mezclan varias fuentes o negocios van en «mixta». Para cambiar una, muévela de lista: la prueba unitaria exige que
# cada símbolo esté en una sola.
FUENTES = [
    ("renovable", "☀️ Renovables (solar, eólica, hidráulica, geotermia, biomasa)"),
    ("nuclear", "☢️ Nucleares (reactores, uranio y combustible)"),
    ("fosil", "🛢️ No renovables fósiles (carbón, gas, petróleo)"),
    ("mixta", "🔀 Mixtas e integradas (varias fuentes o varios negocios)"),
    ("redes", "🔌 Redes (transmisión y distribución)"),
    ("equipos", "🏗️ Equipos y construcción (turbinas, transformadores, cables, respaldo)"),
    ("almacenamiento", "🔋 Almacenamiento e hidrógeno"),
]

_POR_FUENTE = {
    "renovable": [
        "FSLR", "ENPH", "SEDG", "RUN", "NXT", "ARRY", "SHLS", "BEP", "CWEN", "ORA", "HASI", "VWS.CO", "ORSTED.CO", "NDX1.DE",
        "EDPR.LS", "2208.HK", "601615.SS", "SUZLON.NS", "300274.SZ", "601012.SS", "002459.SZ", "SLR.MC", "GRE.MC", "SCATC.OL",
        "ENLT", "NPI.TO", "DRX.L", "UKW.L", "TRIG.L", "ERG.MI", "VER.VI", "H2O.RO", "600900.SS", "600025.SS", "600905.SS",
        "0916.HK", "1798.HK", "ADANIGREEN.NS", "NHPC.NS", "PGEO.JK", "MEZ.AX", "MCY.NZ", "AXIA3.SA", "EGIE3.SA", "AURE3.SA",
        "ICLN", "TAN", "FAN", "PBW", "QCLN"],
    "nuclear": [
        "CEG", "OKLO", "SMR", "BWXT", "CCJ", "LEU", "UEC", "NNE", "SNN.RO", "601985.SS", "1816.HK", "URA", "URNM", "NLR", "NUKZ"],
    "fosil": [
        "NRG", "PGE.WA", "TPE.WA", "600011.SS", "0902.HK", "0991.HK", "NTPC.NS", "ADANIPOWER.NS", "9511.T", "ENEV3.SA"],
    "redes": [
        "ISA.CL", "GEB.CL", "AEP", "EXC", "EIX", "SRE", "ED", "ES", "PPL", "FE", "CNP", "UTL", "FTS.TO", "H.TO", "ACO-X.TO",
        "NG.L", "RED.MC", "TRN.MI", "EOAN.DE", "ELI.BR", "015760.KS", "0006.HK", "POWERGRID.NS", "TAEE11.SA", "ENGI11.SA",
        "EQTL3.SA", "ALUP11.SA", "CGE.SN", "EDN", "GRID"],
    "equipos": [
        "GEV", "ETN", "VRT", "PWR", "HUBB", "POWL", "MYRG", "NVT", "GNRC", "AMSC", "ITRI", "CAT", "CMI", "ENR.DE", "SU.PA",
        "ABBN.SW", "PRY.MI", "NEX.PA", "WRT1V.HE", "6501.T", "6503.T", "7011.T", "034020.KS", "267260.KS", "010120.KS",
        "600089.SS", "WEGE3.SA", "POWERINDIA.NS"],
    "almacenamiento": ["BE", "FLNC", "STEM", "EOSE", "PLUG", "300750.SZ"],
    "mixta": [
        "TLN", "VST", "NEE", "CELSIA.CL", "AES", "DUK", "SO", "D", "XEL", "PCG", "PEG", "WEC", "DTE", "AEE", "ETR", "CMS", "EVRG",
        "LNT", "NI", "OGE", "PNW", "IDA", "POR", "AVA", "BKH", "NWE", "OTTR", "MGEE", "EMA.TO", "AQN.TO", "CPX.TO", "TA.TO",
        "SSE.L", "CNA.L", "IBE.MC", "ELE.MC", "NTGY.MC", "EDP.LS", "ENEL.MI", "A2A.MI", "ENGI.PA", "RWE.DE", "FORTUM.HE",
        "BKW.SW", "CEZ.PR", "PPC.AT", "9501.T", "9502.T", "9503.T", "9506.T", "9504.T", "9505.T", "9508.T", "9507.T", "9513.T",
        "600886.SS", "0836.HK", "2380.HK", "0956.HK", "0002.HK", "TATAPOWER.NS", "JSWENERGY.NS", "TORNTPOWER.NS", "CESC.NS",
        "5347.KL", "EGCO.BK", "GULF.BK", "BGRIM.BK", "RATCH.BK", "GPSC.BK", "U96.SI", "AGL.AX", "ORG.AX", "CEN.NZ", "GNE.NZ",
        "5110.SR", "2082.SR", "AKENR.IS", "ODAS.IS", "ZOREN.IS", "CPFE3.SA", "CMIG4.SA", "CPLE3.SA", "ENELCHILE.SN", "COLBUN.SN",
        "ENELAM.SN", "PAM", "CEPU", "XLU", "VPU"],
}
FUENTE_DE = {s: f for f, lista in _POR_FUENTE.items() for s in lista}
