# Vender el acceso: licencias y dispositivos

Guía para dar y quitar acceso. Todo se hace desde la consola de Firebase; no
hace falta tocar código.

---

## Cómo funciona, en dos frases

El banco de preguntas ya no está dentro de `index.html`: vive en Firestore y
lo entrega la función `banco`, que antes comprueba tres cosas — que la cuenta
tenga licencia, que no esté vencida y que sea el mismo aparato de siempre.
Sin las tres, no baja ni una pregunta.

**Una licencia = un correo = un aparato.** El primero que entra se queda con
la licencia; el segundo recibe *"Esta cuenta ya está en uso en otro
dispositivo"*.

---

## Qué es lo que protege, y qué no

**Sí impide** que la persona a la que le vendiste le pase la cuenta a cinco
compañeros, y que el archivo de la app circule solo por WhatsApp con todo el
banco dentro.

**No impide** que alguien con acceso legítimo copie preguntas a mano o haga
capturas. Eso no lo evita ningún sistema, y conviene tenerlo claro antes de
prometerlo.

---

## Poner en marcha (una sola vez)

```bash
# 1. Las reglas y las funciones
firebase deploy --only functions,firestore:rules

# 2. El banco a la nube
pip install firebase-admin
export GOOGLE_APPLICATION_CREDENTIALS=/ruta/clave-de-servicio.json
python3 tools/subir-banco.py --aplicar

# 3. Crea tu propia licencia (abajo) y comprueba que entras

# 4. Recién ahora, saca el banco del archivo
python3 tools/quitar-banco.py --aplicar
```

La clave de servicio se descarga en **Configuración del proyecto → Cuentas de
servicio → Generar nueva clave privada**. Abre el proyecto entero: guárdala
fuera del repositorio y no la compartas.

El paso 4 es el que enciende la protección. Antes de eso el banco sigue
dentro del archivo y la app abre igual aunque la licencia falle — a propósito,
para que nadie se quede sin nada mientras montas lo demás.

---

## Dar acceso a alguien

1. Consola de Firebase → **Firestore Database**
2. Colección **`licencias`** → **Agregar documento**
3. **El ID del documento es su correo en minúsculas.** Sin espacios.
   Ejemplo: `maria.quispe@gmail.com`
4. Campos:

| Campo | Tipo | Valor |
|---|---|---|
| `activa` | boolean | `true` |
| `vence` | timestamp | la fecha en que se le corta |
| `nombre` | string | opcional, para que tú te ubiques |

No pongas `dispositivo`: ese campo lo escribe la app sola la primera vez que
la persona entra.

Ella tiene que **crear su cuenta con ese mismo correo** desde la pantalla de
entrada de la app, y **verificarlo**. Si entra con otro correo, no la vas a
encontrar en la lista.

> Si no pones `vence`, el acceso no caduca nunca. Para vender por meses,
> ponlo siempre.

---

## Cambió de celular

Le aparece *"Esta cuenta ya está en uso en otro dispositivo"*. Es lo esperado:
la licencia sigue atada al aparato viejo.

Para soltarla: Firestore → `licencias` → su correo → **borra el campo
`dispositivo`**. La próxima vez que abra la app, el aparato nuevo queda
registrado.

Lo mismo si borró los datos del navegador o reinstaló: el identificador del
aparato vive ahí y se pierde con ellos.

> El identificador es un número al azar guardado en su navegador, no una
> huella de su equipo. No se rastrea a nadie; solo sirve para saber que la
> licencia ya está en uso. Que se pierda al borrar datos es el precio de no
> espiar al usuario.

---

## No renovó

Firestore → su correo → `activa` a **`false`**. En cuanto cierre y vuelva a
abrir la app, no entra. Si ya tenía el banco descargado, la app lo borra
apenas la nube le dice que no.

También puedes dejar que caduque solo con `vence`: es lo más cómodo para
vender por meses.

---

## Ver quién está usando la app

Cada licencia guarda `visto`, la última vez que esa persona pidió el banco.
Ordena la colección por ese campo y ves quién sigue estudiando y quién no
entró nunca.

---

## Cuánto cuesta

Con el plan gratuito de Firebase:

| Recurso | Gratis al día | Lo que gasta esto |
|---|---|---|
| Lecturas de Firestore | 50 000 | 3 por persona y arranque |
| Invocaciones de funciones | 2 000 000 al mes | 1 por arranque |
| Salida de red | 5 GB al mes | ~1.2 MB la primera vez de cada persona, después 0 |

El banco baja **una sola vez por aparato** y se guarda con su número de
versión; en los arranques siguientes la nube responde "sin cambios" y no se
transfiere nada. Con 100 alumnos entrando a diario, el gasto se queda muy
adentro de lo gratuito.

Cuando actualices el banco (`subir-banco.py`), la versión cambia y todos lo
vuelven a bajar una vez.

---

## Lo que falta para cerrar del todo

El historial de git **conserva el banco completo** aunque lo saques de
`index.html`: cualquiera puede clonar el repositorio y sacarlo de un commit
viejo. Para que deje de ser accesible hay que **poner el repositorio en
privado**.

Como GitHub Pages no sirve repositorios privados en el plan gratuito, el sitio
tendría que mudarse a **Firebase Hosting**, que ya está configurado en
`firebase.json`:

```bash
firebase deploy --only hosting
```

Queda en `https://examen-residentado.web.app`. Después hay que agregar ese
dominio en **Authentication → Settings → Authorized domains**, y cambiar la
dirección que les pasas a tus compradores.

Aviso honesto: quien ya haya clonado el repositorio mientras era público se
queda con esa copia. Eso no hay forma de deshacerlo.
