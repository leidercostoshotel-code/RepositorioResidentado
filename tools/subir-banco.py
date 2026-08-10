#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sube el banco de preguntas a Firestore, para que deje de viajar dentro de
index.html y solo baje a quien tiene licencia.

    pip install firebase-admin
    python3 tools/subir-banco.py            # muestra que subiria
    python3 tools/subir-banco.py --aplicar  # lo sube

Para que pueda escribir en Firestore hace falta identificarse. Dos caminos:

  a) Desde Cloud Shell o con la CLI de Google instalada, lo mas simple y lo
     mas seguro, porque no descarga ninguna clave:

         gcloud auth application-default login

  b) Con una clave de servicio, si no hay CLI a mano:

         export GOOGLE_APPLICATION_CREDENTIALS=/ruta/clave.json

     Se saca de la consola de Firebase, en Configuracion del proyecto ->
     Cuentas de servicio -> Generar nueva clave privada. **Esa clave abre el
     proyecto entero: no va al repositorio y conviene borrarla al terminar.**

Como queda guardado:

    banco/meta            version, total de preguntas y lista de partes
    banco/parte-0 .. n    el banco en JSON, partido para no pasar el limite
                          de 1 MiB por documento

Se parte por tamaño y no por area para que ninguna parte quede cerca del
limite aunque una area crezca mucho. La funcion "banco" las vuelve a juntar.

La version es la huella del contenido: si el banco no cambio, subirlo otra vez
no toca nada y los navegadores que ya lo tienen no vuelven a bajarlo.
"""

import argparse
import hashlib
import io
import json
import os
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
INDEX = RAIZ / "index.html"

# 900 KB por parte: el limite de Firestore es 1 MiB y conviene dejar aire para
# la sobrecarga del propio documento.
TOPE = 900_000


def leer_banco():
    html = io.open(INDEX, encoding="utf-8").read()
    # "let" y no "const" desde que el banco puede llegar de la nube y
    # reemplazarse en tiempo de ejecucion. Se aceptan los dos para que un
    # index.html de antes de ese cambio siga funcionando.
    m = re.search(r"((?:const|let) BANK = )(\{.*\})(;)", html)
    if not m:
        sys.exit("No se encontro el banco dentro de index.html")
    return json.loads(m.group(2))


def partir(bank):
    """Reparte las especialidades en partes que quepan en un documento."""
    partes, actual, tam = [], {}, 0
    for area in bank:
        for sp, preguntas in bank[area].items():
            trozo = json.dumps({area: {sp: preguntas}}, ensure_ascii=False, separators=(",", ":"))
            if tam and tam + len(trozo.encode()) > TOPE:
                partes.append(actual)
                actual, tam = {}, 0
            actual.setdefault(area, {})[sp] = preguntas
            tam += len(trozo.encode())
    if actual:
        partes.append(actual)
    return partes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--aplicar", action="store_true", help="sube de verdad")
    ap.add_argument("--proyecto", default="examen-residentado")
    args = ap.parse_args()

    bank = leer_banco()
    total = sum(len(l) for a in bank.values() for l in a.values())
    crudo = json.dumps(bank, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    version = hashlib.sha256(crudo.encode()).hexdigest()[:16]
    partes = partir(bank)

    print(f"Preguntas : {total}")
    print(f"Versión   : {version}")
    print(f"Partes    : {len(partes)}")
    for i, p in enumerate(partes):
        js = json.dumps(p, ensure_ascii=False, separators=(",", ":"))
        n = sum(len(preguntas) for area in p.values() for preguntas in area.values())
        print(f"   parte-{i}: {len(js.encode())/1024:7.1f} KB · {n} preguntas")

    if not args.aplicar:
        print("\n(simulación — usa --aplicar para subirlo)")
        return 0

    try:
        import firebase_admin
        from firebase_admin import credentials, firestore
    except ImportError:
        sys.exit("Falta firebase-admin. Instalalo con:  pip install firebase-admin")

    try:
        if not firebase_admin._apps:
            firebase_admin.initialize_app(credentials.ApplicationDefault(),
                                          {"projectId": args.proyecto})
        db = firestore.client()
        # Una lectura barata para que un problema de permisos salga aqui y no
        # a mitad de la subida.
        db.collection("banco").document("meta").get()
    except Exception as e:
        sys.exit(
            "No se pudo entrar a Firestore.\n\n"
            f"  {type(e).__name__}: {e}\n\n"
            "Identificate de una de estas dos formas y vuelve a intentarlo:\n"
            "  gcloud auth application-default login\n"
            "  export GOOGLE_APPLICATION_CREDENTIALS=/ruta/clave.json"
        )

    meta_ref = db.collection("banco").document("meta")
    previo = meta_ref.get()
    if previo.exists and previo.to_dict().get("version") == version:
        print("\nEl banco que ya está subido es idéntico. No se toca nada.")
        return 0

    nombres = []
    lote = db.batch()
    for i, p in enumerate(partes):
        nombre = f"parte-{i}"
        nombres.append(nombre)
        lote.set(db.collection("banco").document(nombre),
                 {"json": json.dumps(p, ensure_ascii=False, separators=(",", ":"))})
    lote.set(meta_ref, {"version": version, "total": total, "partes": nombres})
    lote.commit()

    # Partes de una subida anterior que ya no se usan.
    for doc in db.collection("banco").stream():
        if doc.id != "meta" and doc.id not in nombres:
            doc.reference.delete()
            print(f"   se borró la parte sobrante {doc.id}")

    print(f"\nSubido: {total} preguntas en {len(partes)} partes, versión {version}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
