#!/usr/bin/env python3
"""
Limpia errores de OCR en el banco de preguntas incrustado en index.html.

El compendio original venia escaneado, y el reconocimiento de texto introdujo
dos familias de errores:

1. La letra "n" se leyo como "rt": "anos" quedo como "artos", "nino" como
   "nirto". Son 320 casos.
2. Una marca de agua con un numero de telefono se colo dentro del texto de
   39 preguntas, a mitad de frase.

Uso:
    python3 tools/limpiar-ocr.py            # muestra que cambiaria
    python3 tools/limpiar-ocr.py --aplicar  # escribe los cambios

Es idempotente: correrlo dos veces no cambia nada la segunda vez.
"""

import argparse
import io
import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
INDEX = RAIZ / "index.html"

# --------------------------------------------------------------------------
# 1. Corrupciones de la enie.  SOLO se listan formas que no existen en
#    espanol, para no tocar palabras legitimas.
#
#    Deliberadamente NO se corrigen:
#      parto / partos  -> el OCR no los daño; son partos de verdad y aparecen
#                         85 veces en obstetricia y pediatria.
#      aorta, infarto, arteria, aborto, corticoides, ...  -> su "rt" es real.
# --------------------------------------------------------------------------
ENIE = {
    "artos": "años",
    "arto": "año",
    "Artos": "Años",
    "Arto": "Año",
    "nirto": "niño",
    "nirtos": "niños",
    "nirta": "niña",
    "nirtas": "niñas",
    "Nirto": "Niño",
    "Nirtos": "Niños",
    "Nirta": "Niña",
    "Nirtas": "Niñas",
    "purto": "puño",
    "darto": "daño",
    "dartos": "daños",
    "extrarto": "extraño",
    "extrarta": "extraña",
    "Artadir": "Añadir",
    "artadir": "añadir",
    "Rirton": "Riñon",
    "Rirtón": "Riñón",
    "rirton": "riñon",
    "rirtón": "riñón",
    "rirtones": "riñones",
    "suerto": "sueño",
    "sertor": "señor",
    "sertora": "señora",
    "Sertor": "Señor",
    "Sertora": "Señora",
    "pequerto": "pequeño",
    "pequerta": "pequeña",
    "pequertos": "pequeños",
    "pequertas": "pequeñas",
    "tamarto": "tamaño",
    "murteca": "muñeca",
    "martana": "mañana",
    "sertal": "señal",
    "sertales": "señales",
    "migrarta": "migraña",
    # "diserto" es verbo real (disertar), pero en las dos apariciones del banco
    # el contexto es inequivoco: "el diserto de estudio epidemiologico".
    "diserto": "diseño",
    "Diserto": "Diseño",
}

# --------------------------------------------------------------------------
# 2. Marca de agua: un telefono del documento escaneado que quedo dentro del
#    texto.  Aparece completo ("932 404 060") o partido ("404 060").
# --------------------------------------------------------------------------
MARCA = re.compile(r"\s*\b(?:932\s+)?404\s+060\b\s*")

# --------------------------------------------------------------------------
# 3. Erratas puntuales verificadas una por una en su contexto.
# --------------------------------------------------------------------------
ERRATAS = {
    "Vasodllatación": "Vasodilatación",
    "vasodllatación": "vasodilatación",
    "Tetraciciina": "Tetraciclina",
    "tetraciciina": "tetraciclina",
    "poiidipsia": "polidipsia",
    "plaquetorias": "plaquetarias",
    "plaquetoria": "plaquetaria",
}

PAT_ENIE = re.compile(r"\b(" + "|".join(sorted(ENIE, key=len, reverse=True)) + r")\b")
PAT_ERRATAS = re.compile(r"\b(" + "|".join(sorted(ERRATAS, key=len, reverse=True)) + r")\b")


def limpiar(texto, cuenta):
    """Aplica las tres pasadas a una cadena y acumula estadisticas."""
    def _enie(m):
        cuenta["enie"] += 1
        cuenta["detalle"][m.group(0)] = cuenta["detalle"].get(m.group(0), 0) + 1
        return ENIE[m.group(0)]

    def _errata(m):
        cuenta["erratas"] += 1
        return ERRATAS[m.group(0)]

    nuevo = PAT_ENIE.sub(_enie, texto)
    nuevo = PAT_ERRATAS.sub(_errata, nuevo)

    if MARCA.search(nuevo):
        # se reemplaza por un solo espacio para no pegar dos palabras
        nuevo2 = MARCA.sub(" ", nuevo)
        cuenta["marca"] += len(MARCA.findall(nuevo))
        nuevo = re.sub(r"\s{2,}", " ", nuevo2).strip()

    return nuevo


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--aplicar", action="store_true", help="escribe los cambios en index.html")
    args = ap.parse_args()

    html = io.open(INDEX, encoding="utf-8").read()
    m = re.search(r"(const BANK = )(\{.*\})(;)", html)
    if not m:
        sys.exit("No se encontro el banco dentro de index.html")

    bank = json.loads(m.group(2))
    cuenta = {"enie": 0, "marca": 0, "erratas": 0, "preguntas": 0, "detalle": {}}

    for area in bank.values():
        for preguntas in area.values():
            for q in preguntas:
                antes = (q["q"], [o[1] for o in q["o"]])
                q["q"] = limpiar(q["q"], cuenta)
                for o in q["o"]:
                    o[1] = limpiar(o[1], cuenta)
                if antes != (q["q"], [o[1] for o in q["o"]]):
                    cuenta["preguntas"] += 1

    print(f"Enies corregidas   : {cuenta['enie']}")
    for k, v in sorted(cuenta["detalle"].items(), key=lambda x: -x[1]):
        print(f"    {k:12} -> {ENIE[k]:12} x{v}")
    print(f"Marcas de agua     : {cuenta['marca']}")
    print(f"Erratas puntuales  : {cuenta['erratas']}")
    print(f"Preguntas tocadas  : {cuenta['preguntas']}")

    if not (cuenta["enie"] or cuenta["marca"] or cuenta["erratas"]):
        print("\nNada que cambiar: el banco ya esta limpio.")
        return

    if not args.aplicar:
        print("\n(simulacion — usa --aplicar para escribir los cambios)")
        return

    nuevo = json.dumps(bank, ensure_ascii=False, separators=(",", ":"))
    io.open(INDEX, "w", encoding="utf-8").write(html[: m.start(2)] + nuevo + html[m.end(2):])
    print("\nindex.html actualizado.")


if __name__ == "__main__":
    main()
