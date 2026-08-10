# Mudar todo a Firebase y cerrar el acceso

Guía en orden. Cada paso se puede comprobar antes de pasar al siguiente, y
hasta el paso 6 nada se rompe para quien ya usa la app.

Necesitas la CLI de Firebase:

```bash
npm install -g firebase-tools
firebase login
firebase use examen-residentado
```

---

## 1. Plan Blaze

Las Cloud Functions no existen en el plan gratuito. Consola → **Actualizar** →
**Blaze (pago por uso)**.

No te asustes: Blaze incluye la misma capa gratuita de antes. Con 100 alumnos
entrando a diario esto no llega a facturar. Ponle igual un **presupuesto de
alerta** en Google Cloud → Facturación → Presupuestos, por si acaso: US$ 5 al
mes ya te avisa de cualquier cosa rara.

---

## 2. Desplegar reglas y funciones

```bash
cd firebase/functions && npm install && cd ../..
firebase deploy --only firestore:rules,functions
```

Al terminar te imprime las URLs. La del banco tiene que quedar exactamente en:

```
https://us-central1-examen-residentado.cloudfunctions.net/banco
```

Si tu proyecto o tu región fueran otros, hay que cambiar `FN_BASE` en
`index.html`.

**Compruébalo** — sin sesión tiene que rechazarte:

```bash
curl -s -X POST https://us-central1-examen-residentado.cloudfunctions.net/banco \
  -H 'content-type: application/json' -d '{"aparato":"0000000000000000"}'
# {"error":{"motivo":"sin_sesion","message":"Inicia sesión para entrar."}}
```

Si eso responde otra cosa, para aquí.

---

## 3. Subir el banco

```bash
pip install --user firebase-admin
gcloud auth application-default login
python3 tools/subir-banco.py            # mira lo que va a subir
python3 tools/subir-banco.py --aplicar
```

`gcloud auth application-default login` te da un enlace: lo abres, eliges tu
cuenta y pegas de vuelta el código. **No descarga ninguna clave**, y por eso es
el camino preferible.

Si trabajas desde una máquina sin la CLI de Google, el otro camino es una clave
de servicio: **Configuración del proyecto → Cuentas de servicio → Generar nueva
clave privada**, y luego `export GOOGLE_APPLICATION_CREDENTIALS=/ruta/clave.json`.
Esa clave abre el proyecto entero: guárdala fuera del repositorio, no la mandes
por WhatsApp y bórrala al terminar.

---

## 4. Publicar el sitio en Firebase

```bash
firebase deploy --only hosting
```

Queda en **`https://examen-residentado.web.app`**.

Después, en la consola: **Authentication → Settings → Authorized domains** →
agrega `examen-residentado.web.app` si no está. Sin eso, entrar con Google
falla con *"Este dominio no está autorizado"*.

**Compruébalo**: abre la dirección nueva y entra con tu cuenta. Todavía no
tienes licencia, así que el banco de la nube te va a rechazar — pero como las
preguntas siguen dentro del archivo, la app abre igual. Es lo esperado.

---

## 5. Tu licencia

Firestore → colección **`licencias`** → **Agregar documento**:

- **ID del documento**: tu correo en minúsculas
- `activa` (boolean) = `true`
- `vence` (timestamp) = una fecha lejana

Recarga `examen-residentado.web.app`. En la consola del navegador
(F12 → Network) tienes que ver la llamada a `/banco` devolviendo `200` con las
preguntas. Si ves un `403`, lee el motivo: te dice exactamente qué falta.

Mira también el documento de tu licencia en Firestore: la app le habrá escrito
el campo `dispositivo` sola.

---

## 6. Sacar el banco del archivo

**Este es el paso que enciende la protección.** No lo hagas si algo de lo
anterior no funcionó.

```bash
python3 tools/quitar-banco.py --aplicar   # te pide escribir SI
firebase deploy --only hosting
```

`index.html` pasa de 1312 KB a 171 KB. A partir de aquí, sin licencia no hay
preguntas.

**Compruébalo** en una ventana de incógnito: tiene que quedarse en la pantalla
de entrada y no mostrar ni una pregunta.

---

## 7. Cerrar GitHub

El historial de git conserva el banco completo, aunque ya no esté en el
archivo. Mientras el repositorio sea público, cualquiera puede clonarlo y
sacarlo de un commit viejo.

En GitHub → **Settings** → abajo del todo → **Change repository visibility** →
**Private**.

Dos consecuencias, y conviene tenerlas claras antes:

- **`leidercostoshotel-code.github.io/RepositorioResidentado` deja de
  funcionar.** GitHub Pages no sirve repositorios privados en el plan
  gratuito. Avisa a tus estudiantes de la dirección nueva **antes** de hacerlo.
- **Quien ya clonó el repositorio mientras era público se queda con su copia.**
  Eso no hay forma de deshacerlo. Es el motivo por el que este paso conviene
  hacerlo pronto.

Cuando ya nadie use la dirección vieja, quita
`https://leidercostoshotel-code.github.io` de `ORIGENES_PERMITIDOS` en
`firebase/functions/index.js` y `firebase/functions/banco.js`, y vuelve a
desplegar las funciones.

---

## Lo que queda controlado al terminar

| Pieza | Quién puede |
|---|---|
| Las preguntas | Solo licencia activa, en su aparato registrado |
| El tutor de IA | Lo mismo. Antes bastaba con conocer la URL |
| El progreso de cada uno | Solo su propia cuenta |
| Crear o cambiar licencias | Solo tú, desde la consola |
| Reclamar un aparato | El titular, y solo si está libre. Después no puede cambiarlo |
| El sitio | Firebase Hosting, con el repositorio en privado |

## Lo que no

Que alguien con acceso legítimo copie preguntas a mano o haga capturas. Eso no
lo evita ningún sistema; conviene no prometerlo al vender.

---

## Volver atrás

Nada de esto es irreversible salvo el paso 7:

```bash
git checkout index.html      # devuelve el banco al archivo
firebase deploy --only hosting
```

Y el repositorio se puede volver a poner público cuando quieras, aunque la
dirección de GitHub Pages tarda unos minutos en revivir.
