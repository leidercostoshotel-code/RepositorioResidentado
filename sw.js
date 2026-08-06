/**
 * Service worker del banco de preguntas.
 *
 * Objetivo: que la app abra al instante y siga sirviendo aunque no haya red,
 * sin quedarse nunca con una version vieja pegada.
 *
 * Estrategia por tipo de peticion:
 *
 *   - index.html          red primero, cache de respaldo.  Asi una version
 *                         nueva llega apenas hay conexion, y sin conexion se
 *                         abre la ultima que se guardo.
 *   - assets y manifiesto  cache primero.  Casi nunca cambian.
 *   - fuentes de Google    cache primero, y si no estan se pide a la red en
 *                         segundo plano.  Nunca deben frenar el arranque.
 *   - todo lo demas        se deja pasar sin tocar.
 *
 * Importante: las llamadas al tutor de IA (api.anthropic.com o la Cloud
 * Function) y las de la cuenta en la nube (Firebase Auth y Firestore) NO se
 * interceptan ni se guardan.  Son respuestas distintas cada vez y llevan
 * datos y credenciales del usuario.
 */

const VERSION = "v1";
const CACHE = "residentado-" + VERSION;

/* Lo minimo para que la app arranque sin red. */
const ESENCIALES = [
  "./",
  "./index.html",
  "./manifest.webmanifest",
  "./assets/icon-192.png",
  "./assets/icon-512.png",
  "./assets/apple-touch-icon.png",
];

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches
      .open(CACHE)
      // addAll falla entero si un recurso falla; se agregan de a uno para que
      // un icono ausente no impida instalar el worker.
      .then((c) => Promise.all(ESENCIALES.map((u) => c.add(u).catch(() => null))))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches
      .keys()
      .then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

/** Guarda una copia sin romper la respuesta que se devuelve. */
function guardar(req, res) {
  if (res && res.ok && res.type === "basic") {
    const copia = res.clone();
    caches.open(CACHE).then((c) => c.put(req, copia)).catch(() => {});
  }
  return res;
}

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;

  const url = new URL(req.url);

  /* Ni el tutor de IA ni la cuenta en la nube se cachean o interceptan: son
     respuestas distintas cada vez y llevan datos y credenciales del usuario.
     La regla de mismo origen de mas abajo ya las dejaria pasar, pero se
     nombran aparte para que ningun cambio futuro las arrastre por descuido. */
  if (
    url.hostname === "api.anthropic.com" ||
    url.pathname.includes("cloudfunctions.net") ||
    url.hostname.endsWith(".run.app") ||
    url.hostname.endsWith(".googleapis.com") ||
    url.hostname.endsWith(".firebaseapp.com")
  ) {
    return;
  }

  /* Fuentes de Google: si ya estan guardadas se usan, y si no se piden. */
  if (url.hostname === "fonts.googleapis.com" || url.hostname === "fonts.gstatic.com") {
    e.respondWith(
      caches.match(req).then(
        (hit) =>
          hit ||
          fetch(req)
            .then((res) => {
              // son respuestas opacas: se guardan igual, sirven para el proximo arranque
              const copia = res.clone();
              caches.open(CACHE).then((c) => c.put(req, copia)).catch(() => {});
              return res;
            })
            .catch(() => new Response("", { status: 504 }))
      )
    );
    return;
  }

  /* Solo se administra lo que vive en el mismo origen. */
  if (url.origin !== self.location.origin) return;

  const esDocumento = req.mode === "navigate" || url.pathname.endsWith(".html") || url.pathname.endsWith("/");

  if (esDocumento) {
    /* Red primero: asi una version nueva se ve apenas hay conexion. */
    e.respondWith(
      fetch(req)
        .then((res) => guardar(req, res))
        .catch(() => caches.match(req).then((hit) => hit || caches.match("./index.html")))
    );
    return;
  }

  /* Resto de recursos propios: cache primero. */
  e.respondWith(
    caches.match(req).then(
      (hit) =>
        hit ||
        fetch(req)
          .then((res) => guardar(req, res))
          .catch(() => new Response("", { status: 504 }))
    )
  );
});
