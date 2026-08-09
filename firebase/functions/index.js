/**
 * Proxy de Claude para el banco de preguntas de Residentado Medico.
 *
 * Que hace: recibe la peticion del navegador, comprueba que quien pide tiene
 * licencia activa en su aparato, le agrega la API key de Anthropic (que vive
 * solo aqui, como secreto de Firebase) y devuelve la respuesta. Asi la clave
 * nunca llega al codigo publico de index.html.
 *
 * La licencia no es un adorno: cada llamada gasta dinero de verdad. La lista
 * de origenes permitidos no basta, porque la cabecera Origin la pone el
 * cliente y se falsea con un curl. Lo que no se falsea es el token de sesion,
 * que lo firma Firebase.
 *
 * Despliegue: ver ../README.md
 */

const { onRequest } = require("firebase-functions/v2/https");
const { defineSecret } = require("firebase-functions/params");
const { comprobar, responderDenegado } = require("./licencia");

/* La entrega del banco vive en su propio archivo; se reexporta desde aqui
   para que quede desplegada junto con el proxy. */
exports.banco = require("./banco").banco;

const ANTHROPIC_API_KEY = defineSecret("ANTHROPIC_API_KEY");

/* Dominios autorizados a usar la funcion. Es una barrera de cortesia contra
   el uso desde otra pagina, no una de seguridad: la de verdad es la licencia. */
const ORIGENES_PERMITIDOS = [
  "https://examen-residentado.web.app",
  "https://examen-residentado.firebaseapp.com",
  "https://leidercostoshotel-code.github.io",
  "http://localhost:5000",
  "http://127.0.0.1:5500",
];

/* Solo estos modelos pueden pedirse, para que nadie use tu cuenta
   para lanzar peticiones caras desde la consola del navegador. */
const MODELOS_PERMITIDOS = ["claude-haiku-4-5", "claude-sonnet-5"];

const MAX_TOKENS_TOPE = 1200;

/* Limitador simple por IP en memoria. Suficiente para uso normal;
   si esperas mucho trafico, migra el contador a Firestore. */
const golpes = new Map();
const VENTANA_MS = 60 * 1000;
const MAX_POR_VENTANA = 20;

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

/* Limpieza periodica para que el Map no crezca sin control. */
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

exports.explicar = onRequest(
  { secrets: [ANTHROPIC_API_KEY], region: "us-central1", memory: "256MiB", timeoutSeconds: 60 },
  async (req, res) => {
    const origenOk = aplicarCors(req, res);

    if (req.method === "OPTIONS") return res.status(204).send("");
    if (req.method !== "POST") return res.status(405).json({ error: { message: "Usa POST." } });
    if (!origenOk) return res.status(403).json({ error: { message: "Origen no autorizado." } });

    const ip = req.headers["x-forwarded-for"]?.split(",")[0]?.trim() || req.ip || "desconocida";
    if (limitado(ip)) {
      return res.status(429).json({ error: { message: "Demasiadas consultas seguidas. Espera un minuto." } });
    }

    /* Sin licencia activa en este aparato no se gasta un centavo. No se
       reclama el aparato desde aqui: eso lo hace la funcion del banco, que es
       la puerta de entrada. Aqui solo se comprueba. */
    try {
      await comprobar(req, { reclamar: false });
    } catch (e) {
      return responderDenegado(res, e);
    }

    const cuerpo = req.body || {};
    const modelo = MODELOS_PERMITIDOS.includes(cuerpo.model) ? cuerpo.model : MODELOS_PERMITIDOS[0];

    if (!Array.isArray(cuerpo.messages) || cuerpo.messages.length === 0) {
      return res.status(400).json({ error: { message: "Falta el arreglo messages." } });
    }

    /* Reconstruimos la peticion en lugar de reenviar el cuerpo tal cual:
       asi el navegador no puede inyectar parametros que no queremos pagar. */
    const peticion = {
      model: modelo,
      max_tokens: Math.min(Number(cuerpo.max_tokens) || 900, MAX_TOKENS_TOPE),
      messages: cuerpo.messages,
    };
    if (typeof cuerpo.system === "string") peticion.system = cuerpo.system;
    if (modelo !== "claude-haiku-4-5") peticion.output_config = { effort: "low" };

    try {
      const r = await fetch("https://api.anthropic.com/v1/messages", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-api-key": ANTHROPIC_API_KEY.value(),
          "anthropic-version": "2023-06-01",
        },
        body: JSON.stringify(peticion),
      });

      const datos = await r.json();
      if (!r.ok) {
        console.error("Error de Anthropic:", r.status, datos?.error?.message);
        return res.status(r.status).json({
          error: { message: datos?.error?.message || "Error al consultar el modelo." },
        });
      }
      return res.status(200).json(datos);
    } catch (e) {
      console.error("Fallo de red:", e);
      return res.status(502).json({ error: { message: "No se pudo contactar al servicio de IA." } });
    }
  }
);
