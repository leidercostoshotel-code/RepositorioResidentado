#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Saca el banco de preguntas de index.html. Es el paso que enciende la
proteccion: mientras el banco siga dentro del archivo, cualquiera que lo
guarde lo usa sin licencia, y la puerta le abre igual para no dejar sin app a
nadie durante la mudanza.

    python3 tools/quitar-banco.py            # muestra que pasaria
    python3 tools/quitar-banco.py --aplicar  # lo quita

NO lo ejecutes hasta haber hecho, en este orden:

  1. firebase deploy --only functions,firestore:rules
  2. python3 tools/subir-banco.py --aplicar
  3. crear tu propia licencia en Firestore y comprobar que entras

Si lo haces antes, la app queda sin preguntas para todo el mundo, incluido tu.
El script lo verifica hasta donde puede y avisa.

Para volver atras: git checkout index.html. El banco sigue en el historial.
"""

import argparse
import io
import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
INDEX = RAIZ / "index.html"

PAT = re.compile(r"^let BANK = (\{.*\});$", re.M)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--aplicar", action="store_true", help="escribe los cambios")
    args = ap.parse_args()

    html = io.open(INDEX, encoding="utf-8").read()
    m = PAT.search(html)
    if not m:
        if re.search(r"^let BANK = null;$", html, re.M):
            print("El banco ya está fuera de index.html. No hay nada que hacer.")
            return 0
        sys.exit("No se encontró el banco dentro de index.html.")

    bank = json.loads(m.group(1))
    total = sum(len(l) for a in bank.values() for l in a.values())
    antes = len(html.encode())
    nuevo = html[: m.start()] + "let BANK = null;" + html[m.end():]
    despues = len(nuevo.encode())

    print(f"Preguntas que salen : {total}")
    print(f"index.html          : {antes/1024:.0f} KB → {despues/1024:.0f} KB")
    print()
    print("A partir de aquí la app no tiene preguntas propias: las pide a la")
    print("nube y solo las recibe quien tenga licencia activa en su aparato.")
    print()
    print("Antes de aplicarlo tienes que haber hecho:")
    print("  1. firebase deploy --only functions,firestore:rules")
    print("  2. python3 tools/subir-banco.py --aplicar")
    print("  3. crear tu licencia en Firestore y comprobar que entras")

    if not args.aplicar:
        print("\n(simulación — usa --aplicar para quitarlo)")
        return 0

    resp = input("\n¿Los tres pasos están hechos y comprobados? Escribe SI: ").strip()
    if resp != "SI":
        print("No se tocó nada.")
        return 1

    io.open(INDEX, "w", encoding="utf-8").write(nuevo)
    print(f"\nHecho. index.html quedó en {despues/1024:.0f} KB, sin preguntas dentro.")
    print("Recuerda que el historial de git sí las conserva: para que dejen de")
    print("ser públicas, el repositorio tiene que pasar a privado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
