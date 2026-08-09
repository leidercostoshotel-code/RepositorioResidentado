# Como agregar un examen nuevo al banco

Aqui van los examenes en texto plano antes de entrar al banco. El importador
los lee, los valida y los agrega a `index.html`.

```bash
python3 tools/importar-examen.py            # revisa y reporta, no toca nada
python3 tools/importar-examen.py --aplicar  # escribe en index.html
python3 tools/limpiar-ocr.py --aplicar      # arregla erratas tipicas del escaneo
```

El importador **nunca escribe si hay un solo error**. Primero corre sin
`--aplicar`, lee el reporte, arregla lo que marque y recien despues aplica.

## El formato

Un archivo `.txt` por prueba. Llamalo por el año y la prueba: `2025-A.txt`.

```
# año: 2025
# prueba: A

@ Clínicas / Cardiología

1. Varon de 62 años con dolor toracico opresivo de 40 minutos, irradiado al
   brazo izquierdo, con sudoracion. El electrocardiograma muestra elevacion
   del segmento ST en DII, DIII y aVF. ¿Cual es la conducta inmediata?
A. Angioplastia primaria
B. Prueba de esfuerzo
C. Ecocardiograma transesofagico
D. Holter de 24 horas
Rpta: A

2. ...
```

Reglas, todas cortas:

- **`# año: 2025`** — obligatorio. Si el archivo se llama `2025-A.txt` se toma
  de ahi y puedes omitirlo.
- **`@ Área / Especialidad`** — cambia a que carpeta van las preguntas que
  siguen. Ponlo cada vez que cambie el tema. Si el examen no viene separado
  por especialidad, tendras que ir marcandolo tu.
- **Pregunta** — empieza con el numero: `1.`, `1)` o `1 -`.
- **Alternativas** — en orden desde la `A`. Se aceptan **cuatro** (`A`–`D`,
  que es lo que usa el CONAREME desde 2023) o **cinco** (`A`–`E`, como hasta
  2022). Si solo encuentra tres, lo marca como error: casi siempre significa
  que al pasar el cuadernillo a texto se perdio una linea.
- **Respuesta** — `Rpta: A` (tambien acepta `Respuesta:`, `Clave:`).
- **Texto largo** — puedes partirlo en varias lineas; se pega solo.
- **`// comentario`** — las lineas que empiezan con `//` se ignoran.

## Si la clave viene aparte

Muchos cuadernillos traen las preguntas primero y las respuestas al final. En
ese caso no pongas `Rpta:` en cada pregunta: agrega al final del archivo una
seccion `CLAVES` y el importador la cruza por numero de pregunta.

```
CLAVES
1 A   2 C   3 E   4 B   5 D
6 C   7 A   8 D   9 B  10 E
```

## Areas y especialidades validas

Tienen que escribirse igual, con tildes:

- **Clínicas** — Cardiología, Dermatología, Endocrinología, Gastroenterología,
  Hematología, Infectología, Nefrología, Neumología, Neurología, Psiquiatría,
  Reumatología, UCI
- **Cirugía** — Anestesiología, Cirugía General, Cirugía Pediátrica,
  Cirugía de Cabeza y Cuello, Cirugía de Trauma, Cirugía de Tórax y
  Cardiovascular, Neurocirugía, Oftalmología, Otorrinolaringología,
  Traumatología, Urología
- **Gineco-Obstetricia** — Ginecología, Ginecología Oncológica, Obstetricia
- **Pediatría** — Neonatología, Pediatría
- **Salud Pública** — Demografía, Epidemiología, Estadística,
  Gestión en Salud, Salud Comunitaria, Ética
- **Ciencias Básicas** — Anatomía Humana, Bioquímica, Embriología,
  Farmacología, Histología, Inmunología, Microbiología

Para crear una especialidad que no esta en la lista hay que pasar
`--nueva-especialidad`. Es a proposito: un tilde mal puesto no debe terminar
creando "Cardiologia" al lado de "Cardiología".

## Que revisa antes de aceptar una pregunta

- Que el area y la especialidad existan.
- Que tenga año.
- Que tenga cuatro o cinco alternativas y ninguna vacia.
- Que la respuesta corresponda a una de sus alternativas.
- Que el enunciado no este ya en el banco, ni repetido dentro del mismo
  archivo. Compara sin tildes ni puntuacion, y ademas compara el final del
  enunciado: el mismo caso clinico reaparece de un año a otro con el
  encabezado cambiado ("Paciente mujer de 30 años..." / "Mujer de 30
  años...") y asi tambien lo detecta.

Las repetidas no son un error: las omite y te dice cuales.
