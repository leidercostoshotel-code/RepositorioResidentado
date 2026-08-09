#!/usr/bin/env python3
"""
Importa un examen nuevo al banco de preguntas incrustado en index.html.

Lee los archivos de texto que haya en fuentes/ (o los que se le indiquen),
los convierte a la forma que usa el banco y los agrega a index.html.

Uso:
    python3 tools/importar-examen.py                    # revisa fuentes/ y reporta
    python3 tools/importar-examen.py --aplicar          # escribe en index.html
    python3 tools/importar-examen.py fuentes/2025-A.txt # solo ese archivo

Por defecto NO escribe nada: muestra cuantas preguntas encontro, cuales estan
mal formadas y cuales ya existen en el banco.  Solo con --aplicar toca
index.html, y solo si no hay ningun error.

El formato que acepta esta explicado en fuentes/README.md.
"""

import argparse
import io
import json
import re
import sys
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
INDEX = RAIZ / "index.html"
FUENTES = RAIZ / "fuentes"

LETRAS = "ABCDE"

# --------------------------------------------------------------------------
# Reconocimiento de lineas.  Se acepta ".", ")" y "-" como separador porque el
# OCR de los cuadernillos escaneados no es consistente.
# --------------------------------------------------------------------------
RE_DIRECTIVA = re.compile(r"^\s*#\s*(a[nñ]o|area|área|especialidad|prueba)\s*:\s*(.+?)\s*$", re.I)
RE_BLOQUE = re.compile(r"^\s*@\s*(.+?)\s*$")
RE_PREGUNTA = re.compile(r"^\s*(\d{1,3})\s*[.)\-]\s+(.*)$")
RE_OPCION = re.compile(r"^\s*([A-Ea-e])\s*[.)\-]\s+(.*)$")
# Acepta cualquier letra, no solo A-E: si la clave viene corrida y dice "F",
# hay que reportarlo como respuesta invalida y no dejar que la linea se pegue
# al texto de la ultima alternativa.
RE_RESPUESTA = re.compile(r"^\s*(?:rpta|rspta|resp|respuesta|clave)\s*[:.\-]?\s*([A-Za-z])\b.*$", re.I)
RE_CABECERA_CLAVE = re.compile(r"^\s*claves?\s*(?:oficiales?)?\s*:?\s*$", re.I)
RE_PAR_CLAVE = re.compile(r"\b(\d{1,3})\s*[.)\-:]?\s*([A-Ea-e])\b")
RE_COMENTARIO = re.compile(r"^\s*(?://|;).*$")


def sin_tildes(t):
    return "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")


def clave_texto(t):
    """Forma normalizada de un enunciado, para detectar repetidos."""
    t = sin_tildes(t).lower()
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


# Comparar el enunciado completo no basta: el mismo caso clinico reaparece de
# un año a otro con el encabezado cambiado ("Paciente mujer de 30 años..." vs
# "Mujer de 30 años...") y el banco actual arrastra basura de OCR al inicio de
# varias preguntas.  Comparar tambien la cola encuentra esos casos.  Medido
# contra el banco existente, 70 caracteres no produce falsos positivos; con 60
# empieza a juntar preguntas distintas que terminan igual.
COLA = 70


def cola_texto(t):
    k = clave_texto(t)
    return k[-COLA:] if len(k) >= COLA else None


class Error(Exception):
    pass


# --------------------------------------------------------------------------
# Lectura de un archivo fuente
# --------------------------------------------------------------------------
def leer(ruta):
    """Devuelve (preguntas, avisos).  Cada pregunta es un dict sin id todavia."""
    texto = io.open(ruta, encoding="utf-8").read()
    lineas = texto.replace("\r\n", "\n").split("\n")

    ctx = {"anio": None, "area": None, "esp": None, "prueba": None}
    # El año tambien puede venir en el nombre: 2025-A.txt
    m = re.search(r"(19|20)\d{2}", ruta.name)
    if m:
        ctx["anio"] = int(m.group(0))

    preguntas = []
    avisos = []
    actual = None
    campo = None          # ('q', None) o ('o', indice)
    en_claves = False
    claves = {}

    def cerrar():
        if actual is not None:
            preguntas.append(actual)

    for nlin, linea in enumerate(lineas, 1):
        if RE_COMENTARIO.match(linea):
            continue

        m = RE_DIRECTIVA.match(linea)
        if m:
            k, v = m.group(1).lower(), m.group(2)
            if k.startswith("a") and k not in ("area", "área"):
                ctx["anio"] = int(re.search(r"\d{4}", v).group(0))
            elif k in ("area", "área"):
                ctx["area"] = v
            elif k == "especialidad":
                ctx["esp"] = v
            else:
                ctx["prueba"] = v
            continue

        if RE_CABECERA_CLAVE.match(linea):
            cerrar()
            actual, campo, en_claves = None, None, True
            continue

        if en_claves:
            if linea.strip():
                for num, letra in RE_PAR_CLAVE.findall(linea):
                    claves[int(num)] = letra.upper()
            continue

        m = RE_BLOQUE.match(linea)
        if m:
            partes = [p.strip() for p in re.split(r"[/>|]", m.group(1)) if p.strip()]
            if len(partes) >= 2:
                ctx["area"], ctx["esp"] = partes[0], partes[1]
            elif partes:
                ctx["esp"] = partes[0]
            continue

        m = RE_PREGUNTA.match(linea)
        if m:
            cerrar()
            actual = {
                "n": int(m.group(1)),
                "y": ctx["anio"],
                "q": m.group(2).strip(),
                "o": [],
                "c": None,
                "area": ctx["area"],
                "sp": ctx["esp"],
                "linea": nlin,
                "fuente": ruta.name,
            }
            campo = ("q", None)
            continue

        m = RE_RESPUESTA.match(linea)
        if m and actual is not None:
            actual["c"] = m.group(1).upper()
            campo = None
            continue

        m = RE_OPCION.match(linea)
        # Una linea "A. ..." solo es opcion si ya empezo una pregunta y la letra
        # es la que toca; si no, es texto que empieza por letra y punto.
        if m and actual is not None:
            letra = m.group(1).upper()
            esperada = LETRAS[len(actual["o"])] if len(actual["o"]) < 5 else None
            if letra == esperada:
                actual["o"].append([letra, m.group(2).strip()])
                campo = ("o", len(actual["o"]) - 1)
                continue

        # Continuacion: pertenece al ultimo campo abierto.
        if actual is not None and campo is not None and linea.strip():
            pedazo = linea.strip()
            if campo[0] == "q":
                actual["q"] = (actual["q"] + " " + pedazo).strip()
            else:
                actual["o"][campo[1]][1] = (actual["o"][campo[1]][1] + " " + pedazo).strip()
            continue

        if linea.strip() and actual is None and not en_claves:
            avisos.append(f"{ruta.name}:{nlin}: linea suelta ignorada: {linea.strip()[:70]}")

    cerrar()

    # La clave de respuestas del final gana sobre lo que no tenia respuesta.
    for p in preguntas:
        if p["c"] is None and p["n"] in claves:
            p["c"] = claves[p["n"]]

    sobrantes = sorted(set(claves) - {p["n"] for p in preguntas})
    if sobrantes:
        avisos.append(
            f"{ruta.name}: la clave trae respuestas para preguntas que no aparecen: "
            + ", ".join(str(s) for s in sobrantes[:15])
            + (" ..." if len(sobrantes) > 15 else "")
        )

    return preguntas, avisos


# --------------------------------------------------------------------------
# Validacion
# --------------------------------------------------------------------------
def validar(preguntas, bank, nueva_esp):
    """Devuelve (buenas, errores, repetidas)."""
    validas_area = set(bank)
    esp_por_area = {a: set(bank[a]) for a in bank}

    existentes, colas = set(), set()
    for area in bank.values():
        for lista in area.values():
            for q in lista:
                existentes.add(clave_texto(q["q"]))
                c = cola_texto(q["q"])
                if c:
                    colas.add(c)

    buenas, errores, repetidas = [], [], []
    vistas, vistas_cola = {}, {}

    for p in preguntas:
        donde = f"{p['fuente']}:{p['linea']} (pregunta {p['n']})"

        if not p["area"]:
            errores.append(f"{donde}: falta el area. Usa '# area: Clínicas' o '@ Clínicas / Cardiología'.")
            continue
        if p["area"] not in validas_area:
            errores.append(
                f"{donde}: el area '{p['area']}' no existe. Las validas son: "
                + ", ".join(sorted(validas_area))
            )
            continue
        if not p["sp"]:
            errores.append(f"{donde}: falta la especialidad.")
            continue
        if p["sp"] not in esp_por_area[p["area"]] and not nueva_esp:
            errores.append(
                f"{donde}: la especialidad '{p['sp']}' no existe dentro de '{p['area']}'. "
                f"Usa --nueva-especialidad si de verdad quieres crearla. Existentes: "
                + ", ".join(sorted(esp_por_area[p["area"]]))
            )
            continue
        if not p["y"]:
            errores.append(f"{donde}: falta el año. Usa '# año: 2025' o nombra el archivo 2025-A.txt.")
            continue
        if len(p["q"]) < 15:
            errores.append(f"{donde}: el enunciado esta demasiado corto ({len(p['q'])} caracteres).")
            continue
        # El CONAREME uso cinco alternativas hasta 2022 y desde 2023 usa cuatro,
        # asi que ambas son validas.  Tres casi siempre significa que al pasar
        # el cuadernillo a texto se perdio una linea.
        if len(p["o"]) not in (4, 5):
            errores.append(
                f"{donde}: tiene {len(p['o'])} alternativas. Deben ser 4 (A a D, como "
                f"desde 2023) o 5 (A a E, como hasta 2022); revisa si se perdio alguna linea."
            )
            continue
        if any(not o[1] for o in p["o"]):
            errores.append(f"{donde}: hay una alternativa vacia.")
            continue
        if not p["c"]:
            errores.append(f"{donde}: no tiene respuesta. Pon 'Rpta: C' debajo o agrega la seccion CLAVES.")
            continue
        if p["c"] not in [o[0] for o in p["o"]]:
            errores.append(
                f"{donde}: la respuesta '{p['c']}' no corresponde a ninguna de sus "
                f"{len(p['o'])} alternativas ({', '.join(o[0] for o in p['o'])})."
            )
            continue

        k = clave_texto(p["q"])
        c = cola_texto(p["q"])
        if k in existentes:
            repetidas.append(f"{donde}: ya estaba en el banco, se omite.")
            continue
        if c and c in colas:
            repetidas.append(f"{donde}: casi identica a una que ya esta en el banco, se omite.")
            continue
        if k in vistas:
            repetidas.append(f"{donde}: repetida dentro de la misma fuente ({vistas[k]}), se omite.")
            continue
        if c and c in vistas_cola:
            repetidas.append(
                f"{donde}: casi identica a otra de la misma fuente ({vistas_cola[c]}), se omite."
            )
            continue
        vistas[k] = donde
        if c:
            vistas_cola[c] = donde
        buenas.append(p)

    return buenas, errores, repetidas


# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("archivos", nargs="*", help="archivos a importar (por defecto, todo fuentes/)")
    ap.add_argument("--aplicar", action="store_true", help="escribe los cambios en index.html")
    ap.add_argument("--nueva-especialidad", action="store_true",
                    help="permite crear especialidades que aun no existen")
    args = ap.parse_args()

    if args.archivos:
        rutas = [Path(a) for a in args.archivos]
    else:
        if not FUENTES.is_dir():
            sys.exit(f"No existe la carpeta {FUENTES}. Crea fuentes/ y pon ahi el examen en .txt")
        rutas = sorted(list(FUENTES.glob("*.txt")) + list(FUENTES.glob("*.md")))
        rutas = [r for r in rutas if r.name.lower() not in ("readme.md", "plantilla.txt")]

    if not rutas:
        sys.exit("No hay nada que importar. Pon el examen como fuentes/2025-A.txt "
                 "(el formato esta en fuentes/README.md).")

    faltan = [r for r in rutas if not r.is_file()]
    if faltan:
        sys.exit("No existe: " + ", ".join(str(f) for f in faltan))

    html = io.open(INDEX, encoding="utf-8").read()
    m = re.search(r"(const BANK = )(\{.*\})(;)", html)
    if not m:
        sys.exit("No se encontro el banco dentro de index.html")
    bank = json.loads(m.group(2))

    antes = sum(len(l) for a in bank.values() for l in a.values())
    siguiente = max(q["id"] for a in bank.values() for l in a.values() for q in l) + 1

    todas, avisos = [], []
    for r in rutas:
        p, av = leer(r)
        todas += p
        avisos += av
        print(f"{r.name}: {len(p)} preguntas leidas")

    buenas, errores, repetidas = validar(todas, bank, args.nueva_especialidad)

    for a in avisos:
        print("  aviso  :", a)
    for r in repetidas:
        print("  omitida:", r)
    for e in errores:
        print("  ERROR  :", e)

    print()
    print(f"Leidas    : {len(todas)}")
    print(f"Repetidas : {len(repetidas)}")
    print(f"Con error : {len(errores)}")
    print(f"Nuevas    : {len(buenas)}")

    if buenas:
        resumen = {}
        for p in buenas:
            resumen[(p["y"], p["area"], p["sp"])] = resumen.get((p["y"], p["area"], p["sp"]), 0) + 1
        print("\nDetalle:")
        for (y, area, sp), n in sorted(resumen.items()):
            print(f"    {y}  {area} / {sp}: {n}")

    if errores:
        print("\nNo se escribio nada: corrige los errores de arriba y vuelve a correrlo.")
        return 1

    if not buenas:
        print("\nNada nuevo que agregar.")
        return 0

    if not args.aplicar:
        print("\n(simulacion — usa --aplicar para escribir los cambios)")
        return 0

    for p in buenas:
        bank.setdefault(p["area"], {}).setdefault(p["sp"], []).append({
            "id": siguiente,
            "n": p["n"],
            "y": p["y"],
            "q": p["q"],
            "o": p["o"],
            "c": p["c"],
        })
        siguiente += 1

    despues = sum(len(l) for a in bank.values() for l in a.values())
    nuevo = json.dumps(bank, ensure_ascii=False, separators=(",", ":"))
    io.open(INDEX, "w", encoding="utf-8").write(html[: m.start(2)] + nuevo + html[m.end(2):])
    print(f"\nindex.html actualizado: {antes} -> {despues} preguntas.")
    print("Ahora corre  python3 tools/limpiar-ocr.py  por si el texto trae erratas de escaneo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
