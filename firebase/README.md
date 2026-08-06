# Firebase

El proyecto conectado es **`examen-residentado`**. Firebase cumple dos papeles distintos e independientes:

| Parte | Para qué sirve | Requisitos |
|---|---|---|
| **Cuenta en la nube** (Auth + Firestore) | Que el progreso del estudiante lo siga entre el celular y la computadora | Activarla en la consola. Gratis, entra en la capa gratuita |
| **Hosting** | Publicar la app en `examen-residentado.web.app` | Un comando. Gratis |
| **Tutor IA** (Cloud Function) | Guardar la clave de Anthropic fuera del navegador | Plan Blaze y desplegar la función |

Las tres son independientes: puedes activar una sin las otras. Sin ninguna, la app funciona completa en modo local.

Todos los comandos de esta guía se corren **desde la raíz del repositorio**. El proyecto ya viene fijado en `.firebaserc`, así que no hace falta enlazarlo a mano.

---

# 1. Cuenta en la nube

La configuración web ya está escrita en `index.html`:

```js
const FB_CFG={ apiKey:"AIza…", authDomain:"examen-residentado.firebaseapp.com", … };
```

**Esa `apiKey` no es un secreto.** A diferencia de la de Anthropic, solo identifica al proyecto: no autoriza nada. Google la publica a propósito en todos sus ejemplos. Lo que protege los datos son las reglas de Firestore, no esconderla.

## Pasos en la consola

**1. Habilita el ingreso con Google**

[Authentication → Sign-in method](https://console.firebase.google.com/project/examen-residentado/authentication/providers) → **Google** → Habilitar → Guardar.

**2. Autoriza el dominio de tu sitio**

Authentication → Settings → **Authorized domains** → agrega el dominio desde el que sirves la app:

```
leidercostoshotel-code.github.io
```

Si te saltas esto, al entrar aparece el aviso *"Este dominio no esta autorizado en Firebase"*.

`localhost`, `examen-residentado.web.app` y `examen-residentado.firebaseapp.com` **vienen autorizados de fábrica**: si publicas con Firebase Hosting (sección 2), este paso no hace falta.

**3. Crea la base de datos**

[Firestore Database](https://console.firebase.google.com/project/examen-residentado/firestore) → Crear base de datos → modo **producción** → región `southamerica-east1` o `us-central1`.

**4. Publica las reglas**

```bash
firebase deploy --only firestore:rules
```

(desde la raíz del repositorio; el proyecto ya viene fijado en `.firebaserc`)

O pégalas a mano desde `firestore.rules` en la pestaña **Rules** de la consola. Dicen que cada quien solo alcanza su propio documento:

```
match /usuarios/{uid} {
  allow read, write: if request.auth != null && request.auth.uid == uid;
}
```

Sin esas reglas publicadas, la app avisa *"Firestore rechazo la operacion"* y sigue trabajando en local.

## Qué se guarda

Un solo documento por estudiante, en `usuarios/{uid}`:

```json
{ "version": 1, "guardado": 1738800000000, "stats": { "srs": {…}, "dias": {…}, "xp": 2450, … } }
```

Solo el progreso. **No** se sube el correo (ya está en la sesión de Google), **ni** ninguna clave de la API de Anthropic, **ni** las preguntas.

## Cómo se combinan dos equipos

Al entrar en un equipo nuevo, lo que hay ahí se fusiona con lo de la nube en vez de pisarse:

| Dato | Regla |
|---|---|
| Memoria de cada pregunta (repetición espaciada) | Gana el repaso **más reciente**, pregunta por pregunta |
| Logros | Se **unen** los de ambos lados |
| Racha diaria | La define el **último día completado** |
| Contadores de por vida (XP, respuestas, simulacros) | Se toma el **mayor** de los dos |

El máximo en los contadores se queda corto si estudiaste en dos equipos el mismo día sin sincronizar; sumarlos sería peor, porque duplicaría en cada sincronización. Lo que de verdad manda el repaso —la memoria por pregunta— sí se fusiona exacto.

## Costo

Nulo en la práctica. La capa gratuita de Firestore da 50 000 lecturas y 20 000 escrituras al día; esta app hace **una lectura al abrir** y **una escritura agrupada cada 8 segundos de inactividad**, nunca una por respuesta. Un simulacro de 100 preguntas gasta unas pocas escrituras, no cien.

## Si algo falla

| Aviso en la app | Qué hacer |
|---|---|
| "Este dominio no esta autorizado" | Paso 2: agregar el dominio en Authorized domains |
| "El ingreso con Google no esta habilitado" | Paso 1: habilitar el proveedor |
| "Firestore rechazo la operacion" | Paso 4: publicar las reglas |
| "No se pudo cargar Firebase" | Sin conexión. El progreso local queda intacto |

En todos los casos la app **sigue funcionando completa**: el simulacro, la repetición espaciada y la racha nunca dependieron de la nube.

---

# 2. Publicar la app (Hosting)

Sirve la app en `https://examen-residentado.web.app`. Es gratis en plan Spark y es una alternativa a GitHub Pages —o un respaldo, si Pages se atasca.

**1. Instala la CLI e inicia sesión** (una sola vez)

```bash
npm install -g firebase-tools
firebase login
```

**2. Publica**

```bash
firebase deploy --only hosting
```

Eso es todo. En menos de un minuto imprime:

```
Hosting URL: https://examen-residentado.web.app
```

## Qué se sube

Solo lo que la app necesita: `index.html`, `sw.js`, `manifest.webmanifest` y `assets/`. La configuración en `firebase.json` deja fuera `firebase/`, `tools/`, los `.md` y todo lo que empiece por punto (incluido `.git`).

## Detalles que ya están resueltos

- **Rutas relativas.** En GitHub Pages la app vive bajo `/RepositorioResidentado/` y aquí en la raíz. El manifiesto usa `start_url: "."` y los iconos son relativos, así que funciona igual en ambas sin tocar nada.
- **Caché.** `index.html`, `sw.js` y el manifiesto se sirven con `no-cache` para que una versión nueva llegue de inmediato; los iconos se cachean una semana. Sin esto, el service worker podía quedarse con una copia vieja pegada.
- **Dominio autorizado.** `examen-residentado.web.app` ya está en la lista de Firebase Auth, así que el ingreso con Google funciona sin configurar nada más.

## Publicar en los dos sitios

No hay conflicto: GitHub Pages se actualiza solo al fusionar en `main`, y Firebase Hosting cuando corres el comando. Si usas ambos, acuérdate de correr el deploy después de cada cambio para que no se desfasen.

---

# 3. Tutor IA vía Cloud Function

Esta carpeta contiene una **Cloud Function** que actúa de intermediario entre la app y la API de Claude.

## Por qué existe

`index.html` es un archivo estático. Si pegas ahí tu API key de Anthropic, **cualquiera puede verla** con "ver código fuente" y gastarte el saldo. No hay forma de esconderla en un sitio estático.

Con esta función, la clave vive en los **secretos de Firebase** (en el servidor de Google) y el navegador solo habla con tu función:

```
Navegador  →  tu Cloud Function  →  api.anthropic.com
   (sin clave)   (aquí está la clave)
```

Resultado: cualquier persona que abra la app tiene tutor IA sin configurar nada.

## Requisitos

- Una **API key de Anthropic** con saldo. Se saca en [platform.claude.com/settings/keys](https://platform.claude.com/settings/keys) y se paga por uso, aparte de cualquier suscripción de claude.ai.
- Cuenta de Google y un proyecto en [Firebase](https://console.firebase.google.com)
- **Plan Blaze** (pago por uso). Es obligatorio porque el plan gratuito no permite que una función llame a servicios externos. El uso normal de esta app cae dentro de la capa gratuita mensual de Cloud Functions; lo que sí se cobra es el consumo de la API de Anthropic.
- Node.js 22 y `firebase-tools`

## Pasos

**1. Instala la CLI e inicia sesión**

```bash
npm install -g firebase-tools
firebase login
```

**2. Enlaza tu proyecto**

El proyecto ya viene fijado en `.firebaserc`, así que no hay que enlazarlo a mano. Todos los comandos se corren **desde la raíz del repositorio**.

**3. Guarda tu API key como secreto**

```bash
firebase functions:secrets:set ANTHROPIC_API_KEY
# pega tu clave sk-ant-... cuando lo pida
```

La clave queda cifrada en Google Secret Manager. No la escribas nunca en un archivo del repositorio.

**4. Autoriza tu dominio**

Abre `firebase/functions/index.js` y edita `ORIGENES_PERMITIDOS` con las URL reales de tu sitio:

```js
const ORIGENES_PERMITIDOS = [
  "https://leidercostoshotel-code.github.io",
  "https://examen-residentado.web.app",
];
```

Si el dominio no está en esa lista, la función rechaza la petición. Es lo que impide que otros usen tu función desde sus propias páginas.

**5. Despliega**

```bash
cd firebase/functions && npm install && cd ../..
firebase deploy --only functions
```

Al terminar, la consola imprime la URL. Se ve así:

```
https://us-central1-examen-residentado.cloudfunctions.net/explicar
```

**6. Conéctala en la app**

En la página de inicio, sección **Tutor con IA** → modo **Servidor propio** → pega la URL → **Guardar y probar**.

Debería aparecer "Conexión correcta".

Si quieres que quede fija para todos los usuarios (sin que cada uno la pegue), busca esta línea en `index.html` y pon tu URL como valor por defecto:

```js
let AI={mode:'proxy',url:'',key:'',model:'claude-haiku-4-5'};
```

## Protecciones incluidas

| Riesgo | Cómo se controla |
|---|---|
| Clave expuesta al público | Vive en Secret Manager, nunca sale al navegador |
| Alguien usa tu función desde otra web | Lista blanca de orígenes (CORS) |
| Ráfagas de peticiones | Límite de 20 por minuto por IP |
| Peticiones caras inyectadas | El servidor reconstruye el cuerpo: solo acepta modelos de la lista y topa `max_tokens` en 1200 |

Aun así, **vigila tu consumo**. En [platform.claude.com](https://platform.claude.com) puedes fijar un límite de gasto mensual, y en Google Cloud puedes poner una alerta de presupuesto.

## Costo aproximado

Medido sobre las preguntas reales de este banco (mediana de 429 caracteres de enunciado más alternativas, sistema de 698, y un tope de 200 palabras de respuesta):

| Modelo | Por explicación | Con 5 USD |
|---|---|---|
| Claude Haiku 4.5 | ≈ 0.0019 USD | ≈ **2 700** explicaciones |
| Claude Sonnet 5 | ≈ 0.0055 USD | ≈ **900** explicaciones |

Las preguntas más largas del banco (percentil 90) apenas mueven la cifra: el costo lo domina la respuesta, no el enunciado.

### Cuánto gasta cada modo de explicación

En Inicio → Tutor con IA eliges cuándo aparece la explicación. Sobre un simulacro de 20 preguntas con 70 % de aciertos:

| Modo | Peticiones | Costo con Haiku |
|---|---|---|
| **Si fallo** (por defecto) | 6 | ≈ 0.011 USD |
| **Siempre** | 20 | ≈ 0.038 USD |
| **Al tocar** | las que elijas | — |

Las explicaciones se guardan en memoria durante el simulacro: volver a una pregunta ya explicada no genera una petición nueva.

### Qué pasa cuando se acaba el saldo

La app **no se rompe ni se queda cargando**. Al primer error de saldo agotado, clave inválida o permiso denegado:

1. Apaga la IA para el resto de la sesión, así no gasta una petición condenada al error en cada pregunta.
2. Muestra un aviso de **Modo local** explicando qué pasó y cómo solucionarlo.
3. El simulacro continúa normal con la retroalimentación del banco local: clave, opciones descartadas, dato de repaso e historial por especialidad.

Los errores pasajeros (429 por ráfaga de peticiones, 5xx por sobrecarga) **no** apagan nada: el botón queda disponible para reintentar.

Para reactivarla después de recargar saldo, basta con recargar la página o tocar **Guardar y probar** en Inicio → Tutor con IA.

### Si publicas la app con el proxy

Recuerda que el saldo lo pagas tú para **todos** los que usen la página. El límite de 20 peticiones por minuto por IP frena los abusos, pero no el uso legítimo: 50 estudiantes pidiendo 10 explicaciones cada uno consumen 500, es decir cerca de un dólar.

Dimensiona el saldo según cuánta gente vaya a usarla y fija un límite de gasto mensual en [platform.claude.com](https://platform.claude.com).

## La app funciona sin conexión, el tutor no

Desde que la app es instalable con service worker, conviene tener clara la separación:

| Parte | ¿Necesita internet? |
|---|---|
| Abrir la app, banco de 3 125 preguntas, retroalimentación local, repetición espaciada, racha | **No** |
| Cuenta en la nube (sincronizar entre equipos) | **Sí**, pero se pone al día sola al volver la señal |
| Tutor IA (explicaciones de Claude) | **Sí** |

Sin señal, el simulacro sigue funcionando completo y el tutor queda en pausa con un aviso. Al recuperar la conexión vuelve solo.

El service worker **nunca intercepta ni guarda** las llamadas a `api.anthropic.com`, a la Cloud Function, ni a Firebase Auth y Firestore: son respuestas distintas cada vez y llevan datos y credenciales del usuario.

## Si no quieres usar Firebase

La app funciona igual sin esto:

- **Modo local** (siempre activo, gratis): retroalimentación detallada, análisis de tu respuesta, opciones descartadas, datos de repaso e historial por especialidad.
- **Modo clave personal**: cada usuario pega su propia API key, que se guarda solo en su navegador.
