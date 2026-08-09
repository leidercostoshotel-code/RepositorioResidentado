/**
 * Comprobacion de licencia compartida por las funciones.
 *
 * Vive aparte porque la usan dos: la que entrega el banco de preguntas y la
 * que habla con Claude. La segunda gasta dinero de verdad en cada llamada, y
 * dejarla abierta a cualquiera que conozca la URL era un agujero: la lista de
 * origenes permitidos se falsea con un curl en diez segundos, porque la
 * cabecera Origin la pone el cliente.
 */

const admin = require("firebase-admin");

if (!admin.apps.length) admin.initializeApp();

const MOTIVOS = {
  sin_sesion: "Inicia sesión para entrar.",
  sin_correo: "Tu cuenta no tiene un correo verificado. Revisa tu bandeja y confirma el correo.",
  sin_licencia: "Esta cuenta todavía no tiene acceso. Escríbele al administrador con el correo con el que entraste.",
  vencida: "Tu acceso venció. Escríbele al administrador para renovarlo.",
  suspendida: "Tu acceso está suspendido. Escríbele al administrador.",
  otro_aparato: "Esta cuenta ya está en uso en otro dispositivo. Solo se puede usar en uno.",
  sin_aparato: "Falta identificar el dispositivo. Recarga la página.",
};

class Denegado extends Error {
  constructor(motivo, codigo) {
    super(MOTIVOS[motivo] || "Acceso denegado.");
    this.motivo = motivo;
    this.codigo = codigo || 403;
  }
}

/**
 * Devuelve { correo, licencia, ref } si puede pasar. Si no, lanza Denegado.
 *
 * @param {object} req  la peticion de Express
 * @param {object} opciones
 * @param {boolean} opciones.reclamar  si true, el primer aparato que llega se
 *   queda con la licencia. Lo hace la funcion del banco, que es la puerta de
 *   entrada; la del tutor solo comprueba, para no registrar un aparato por un
 *   camino lateral.
 */
async function comprobar(req, opciones) {
  const cabecera = req.headers.authorization || "";
  const token = cabecera.startsWith("Bearer ") ? cabecera.slice(7) : "";
  if (!token) throw new Denegado("sin_sesion", 401);

  let sesion;
  try {
    sesion = await admin.auth().verifyIdToken(token);
  } catch (e) {
    throw new Denegado("sin_sesion", 401);
  }

  const correo = (sesion.email || "").toLowerCase();
  if (!correo || !sesion.email_verified) throw new Denegado("sin_correo");

  const aparato = String((req.body && req.body.aparato) || "");
  if (aparato.length < 16 || aparato.length > 64) throw new Denegado("sin_aparato", 400);

  const db = admin.firestore();
  const ref = db.collection("licencias").doc(correo);
  const snap = await ref.get();
  if (!snap.exists) throw new Denegado("sin_licencia");

  const licencia = snap.data() || {};
  if (licencia.activa !== true) throw new Denegado("suspendida");
  if (licencia.vence && licencia.vence.toMillis && licencia.vence.toMillis() < Date.now()) {
    throw new Denegado("vencida");
  }

  if (!licencia.dispositivo) {
    if (!(opciones && opciones.reclamar)) throw new Denegado("sin_aparato", 400);
    await ref.update({
      dispositivo: aparato,
      visto: admin.firestore.FieldValue.serverTimestamp(),
    });
    licencia.dispositivo = aparato;
  } else if (licencia.dispositivo !== aparato) {
    throw new Denegado("otro_aparato");
  } else if (opciones && opciones.reclamar) {
    await ref.update({ visto: admin.firestore.FieldValue.serverTimestamp() });
  }

  return { correo, licencia, ref, db };
}

function responderDenegado(res, e) {
  if (e instanceof Denegado) {
    return res.status(e.codigo).json({ error: { motivo: e.motivo, message: e.message } });
  }
  console.error("Fallo comprobando la licencia:", e);
  return res.status(500).json({ error: { message: "No se pudo comprobar tu acceso." } });
}

module.exports = { comprobar, responderDenegado, Denegado, MOTIVOS, admin };
