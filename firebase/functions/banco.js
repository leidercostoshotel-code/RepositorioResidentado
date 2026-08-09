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
const admin = require("firebase-admin");

if (!admin.apps.length) admin.initializeApp();

const ORIGENES_PERMITIDOS = [
  "https://leidercostoshotel-code.github.io",
  "https://examen-residentado.web.app",
  "https://examen-residentado.firebaseapp.com",
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

/* Motivos separados a proposito: el estudiante tiene que poder distinguir
   "no me vendieron todavia" de "se me vencio" de "esta en mi otro celular",
   porque cada uno se resuelve distinto. */
const MOTIVOS = {
  sin_sesion: "Inicia sesión para entrar.",
  sin_correo: "Tu cuenta no tiene un correo verificado. Revisa tu bandeja y confirma el correo.",
  sin_licencia: "Esta cuenta todavía no tiene acceso. Escríbele al administrador con el correo con el que entraste.",
  vencida: "Tu acceso venció. Escríbele al administrador para renovarlo.",
  suspendida: "Tu acceso está suspendido. Escríbele al administrador.",
  otro_aparato: "Esta cuenta ya está en uso en otro dispositivo. Solo se puede usar en uno.",
  sin_aparato: "Falta identificar el dispositivo. Recarga la página.",
};

function fallo(res, codigo, motivo) {
  return res.status(codigo).json({ error: { motivo, message: MOTIVOS[motivo] || "Acceso denegado." } });
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

    /* 1. Quien pide. El token lo firma Firebase; el cliente no puede falsearlo. */
    const cabecera = req.headers.authorization || "";
    const token = cabecera.startsWith("Bearer ") ? cabecera.slice(7) : "";
    if (!token) return fallo(res, 401, "sin_sesion");

    let sesion;
    try {
      sesion = await admin.auth().verifyIdToken(token);
    } catch (e) {
      return fallo(res, 401, "sin_sesion");
    }
    const correo = (sesion.email || "").toLowerCase();
    if (!correo || !sesion.email_verified) return fallo(res, 403, "sin_correo");

    /* 2. Desde donde. */
    const aparato = String((req.body && req.body.aparato) || "");
    if (aparato.length < 16 || aparato.length > 64) return fallo(res, 400, "sin_aparato");

    /* 3. Tiene licencia. */
    const db = admin.firestore();
    const ref = db.collection("licencias").doc(correo);
    const snap = await ref.get();
    if (!snap.exists) return fallo(res, 403, "sin_licencia");

    const lic = snap.data() || {};
    if (lic.activa !== true) return fallo(res, 403, "suspendida");
    if (lic.vence && lic.vence.toMillis && lic.vence.toMillis() < Date.now()) {
      return fallo(res, 403, "vencida");
    }

    /* 4. Es su aparato. El primero que entra se queda con la licencia; para
       soltarla hay que borrar el campo desde la consola. Asi una cuenta
       comprada no se reparte entre varias personas. */
    if (!lic.dispositivo) {
      await ref.update({ dispositivo: aparato, visto: admin.firestore.FieldValue.serverTimestamp() });
    } else if (lic.dispositivo !== aparato) {
      return fallo(res, 403, "otro_aparato");
    } else {
      await ref.update({ visto: admin.firestore.FieldValue.serverTimestamp() });
    }

    /* 5. La version. Si el navegador ya tiene esta, no se manda nada. */
    const metaSnap = await db.collection("banco").doc("meta").get();
    const meta = metaSnap.exists ? metaSnap.data() : null;
    if (!meta) return res.status(503).json({ error: { message: "El banco todavía no está publicado." } });

    if (req.body && req.body.version && req.body.version === meta.version) {
      return res.status(200).json({ version: meta.version, sinCambios: true });
    }

    /* 6. El banco, armado a partir de sus partes. */
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
