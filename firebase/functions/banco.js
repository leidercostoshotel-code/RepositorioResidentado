/**
 * Entrega el banco de preguntas solo a quien tiene licencia activa y desde el
 * aparato registrado.
 *
 * Por que una funcion y no las reglas de Firestore: las reglas pueden decidir
 * segun quien pide y segun lo que ya hay guardado, pero en una LECTURA no ven
 * ningun dato que mande el cliente. El id del dispositivo lo manda el cliente,
 * asi que atar una cuenta a un aparato es imposible con reglas solas. Aqui si:
 * la peticion trae el id, se compara con el registrado y se decide.
 *
 * El banco vive en Firestore partido por area (un documento por area, porque
 * el limite de un documento es 1 MiB y el banco entero pesa mas). Se sirve
 * junto con su version, para que el navegador que ya lo tenga guardado no
 * vuelva a bajarlo.
 *
 * Despliegue: ver ../README.md
 */

const { onRequest } = require("firebase-functions/v2/https");
const { comprobar, responderDenegado } = require("./licencia");

const ORIGENES_PERMITIDOS = [
  "https://examen-residentado.web.app",
  "https://examen-residentado.firebaseapp.com",
  "https://leidercostoshotel-code.github.io",
  "http://localhost:5000",
  "http://127.0.0.1:5500",
];

/* Limitador por IP: bajar el banco es caro y no hay razon para pedirlo
   muchas veces seguidas. */
const golpes = new Map();
const VENTANA_MS = 60 * 1000;
const MAX_POR_VENTANA = 6;

function limitado(ip) {
  const ahora = Date.now();
  const previo = golpes.get(ip);
  if (!previo || ahora - previo.desde > VENTANA_MS) {
    golpes.set(ip, { desde: ahora, n: 1 });
    return false;
  }
  previo.n += 1;
  return previo.n > MAX_POR_VENTANA;
}

setInterval(() => {
  const ahora = Date.now();
  for (const [ip, v] of golpes) if (ahora - v.desde > VENTANA_MS) golpes.delete(ip);
}, VENTANA_MS).unref?.();

function aplicarCors(req, res) {
  const origen = req.headers.origin;
  if (origen && ORIGENES_PERMITIDOS.includes(origen)) {
    res.set("Access-Control-Allow-Origin", origen);
    res.set("Vary", "Origin");
  }
  res.set("Access-Control-Allow-Methods", "POST, OPTIONS");
  res.set("Access-Control-Allow-Headers", "content-type, authorization");
  res.set("Access-Control-Max-Age", "3600");
  return !origen || ORIGENES_PERMITIDOS.includes(origen);
}

exports.banco = onRequest(
  { region: "us-central1", memory: "512MiB", timeoutSeconds: 60 },
  async (req, res) => {
    const origenOk = aplicarCors(req, res);

    if (req.method === "OPTIONS") return res.status(204).send("");
    if (req.method !== "POST") return res.status(405).json({ error: { message: "Usa POST." } });
    if (!origenOk) return res.status(403).json({ error: { message: "Origen no autorizado." } });

    const ip = req.headers["x-forwarded-for"]?.split(",")[0]?.trim() || req.ip || "desconocida";
    if (limitado(ip)) {
      return res.status(429).json({ error: { message: "Demasiadas peticiones seguidas. Espera un minuto." } });
    }

    /* Quien pide, desde donde y con que derecho. La funcion del banco es la
       puerta de entrada, asi que aqui si se reclama el aparato: el primero
       que llega se queda con la licencia. */
    let db;
    try {
      ({ db } = await comprobar(req, { reclamar: true }));
    } catch (e) {
      return responderDenegado(res, e);
    }

    /* La version. Si el navegador ya tiene esta, no se manda nada. */
    const metaSnap = await db.collection("banco").doc("meta").get();
    const meta = metaSnap.exists ? metaSnap.data() : null;
    if (!meta) return res.status(503).json({ error: { message: "El banco todavía no está publicado." } });

    if (req.body && req.body.version && req.body.version === meta.version) {
      return res.status(200).json({ version: meta.version, sinCambios: true });
    }

    /* El banco, armado a partir de sus partes. */
    const partes = await Promise.all(
      meta.partes.map((p) => db.collection("banco").doc(p).get())
    );
    const bank = {};
    for (const p of partes) {
      if (!p.exists) continue;
      Object.assign(bank, JSON.parse(p.data().json));
    }

    return res.status(200).json({ version: meta.version, total: meta.total, bank });
  }
);
