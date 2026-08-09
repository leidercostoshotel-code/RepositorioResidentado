#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Convierte el cuadernillo resuelto en PDF al formato de texto de fuentes/.

    pip install pymupdf
    python3 tools/pdf-a-fuente.py fuentes/2025-A.pdf > fuentes/2025-A.txt

Despues hay que poner a mano las cabeceras "@ Area / Especialidad" (el PDF no
trae esa informacion) y recien ahi correr tools/importar-examen.py.

Esta escrito contra los cuadernillos resueltos que circulan del examen del
CONAREME, que tienen tres rarezas:

1. Todo el texto esta dibujado dos veces, una encima de la otra: es el truco
   de negrita falsa de algunos conversores de Word. La copia aparece unas
   veces como otra linea a la misma altura y otras como trozos encabalgados
   dentro de la misma linea. Por eso se pega solapando —del trozo nuevo solo
   se anade lo que no repite el final de lo ya acumulado— y se descarta la
   linea que ya esta contenida en lo acumulado. Las dos copias no caen
   exactamente a la misma altura (se han visto 2.7 puntos de diferencia), asi
   que las lineas se agrupan por cercania y no por su coordenada exacta.

2. La respuesta correcta no viene en una clave aparte: esta marcada dentro
   del enunciado, en negrita y con resaltado amarillo. Se usa la negrita,
   atribuida a la linea donde aparece. Contrastado con el resaltado amarillo
   en las 100 preguntas de 2025: coinciden en las 91 donde el resaltado quedo
   alineado con su texto, y en las otras 9 el resaltado esta corrido.
   Atribuir la negrita por linea es imprescindible: hay preguntas con dos
   alternativas impresas una encima de otra.

3. El documento fue dictado. "coma", "punto" y "dos puntos" aparecen escritos
   como palabras. Se convierten solo cuando lo que sigue empieza en
   minuscula, para no romper "el punto D" del POP-Q ni un "coma" que sea el
   estado de conciencia.

Si el PDF no cumple lo primero (texto dibujado una sola vez), el pegado con
solape no estorba: no hay nada que solapar y el texto sale igual.
"""

import argparse
import collections
import re
import sys

try:
    import pymupdf
except ImportError:
    sys.exit("Falta pymupdf. Instalalo con:  pip install pymupdf")

LETRAS = "ABCDE"


# --------------------------------------------------------------------------
# Lectura del PDF
# --------------------------------------------------------------------------
def fusion(acc, s):
    """Pega s a acc sin repetir el solape."""
    if not acc:
        return s
    for L in range(min(len(acc), len(s)), 0, -1):
        if acc[-L:] == s[:L]:
            return acc + s[L:]
    return acc + s


def normaliza(t):
    return " ".join(t.replace("\xa0", " ").split())


def lineas_pdf(ruta, negrita, desde):
    """Devuelve [(texto, [trozos en negrita])] en orden de lectura."""
    doc = pymupdf.open(ruta)
    fuera = []
    for i, pg in enumerate(doc):
        if i < desde:
            continue
        crudas = []
        for bl in pg.get_text("dict")["blocks"]:
            for ln in bl.get("lines", []):
                txt, negs = "", []
                for sp in ln["spans"]:
                    if not sp["text"].strip():
                        continue
                    txt = fusion(txt, sp["text"])
                    if negrita in sp["font"]:
                        negs.append(normaliza(sp["text"]))
                txt = normaliza(txt)
                if txt:
                    crudas.append((ln["bbox"][1], ln["bbox"][0], txt, negs))
        grupos = []
        for y0, x, txt, negs in sorted(crudas):
            if grupos and y0 - grupos[-1][0] <= 4.0:
                grupos[-1][1].append((x, txt, negs))
            else:
                grupos.append((y0, [(x, txt, negs)]))
        for _, grupo in grupos:
            acc, claves = "", []
            for x, txt, negs in sorted(grupo):
                if txt in acc:
                    continue
                acc = fusion(acc, txt)
                claves += negs
            s = normaliza(acc)
            if s and not set(s) <= set("_ –-"):
                fuera.append((s, [c for c in dict.fromkeys(claves) if c]))
    return fuera


# --------------------------------------------------------------------------
# Armado de las preguntas
# --------------------------------------------------------------------------
def mitad(s):
    n = len(s)
    return s[:n // 2] if n >= 2 and n % 2 == 0 and s[:n // 2] == s[n // 2:] else s


def colapsar(s, minimo=4):
    """Quita repeticiones adyacentes. El minimo de 4 caracteres es a proposito:
    con 2 se comia silabas reales ('Parálisis' -> 'Parális')."""
    i = 0
    while i < len(s):
        largo = 0
        for L in range((len(s) - i) // 2, minimo - 1, -1):
            if s[i:i + L] == s[i + L:i + 2 * L]:
                largo = L
                break
        if largo:
            s = s[:i + largo] + s[i + 2 * largo:]
        else:
            i += 1
    return s


SUBI = re.compile(r"\b([A-Za-z]{2,}) ?(\d) \2\b")
PREF = re.compile(r"^(\d{1,3}|[A-E])\.\s*\1\.\s*")
BASURA = re.compile(r"^(?:[vV]+[\s vV]*|_[\s_]*)$")


def limpia_linea(s, negs):
    m = PREF.match(s)
    pref = ""
    if m:
        pref = m.group(1) + ". "
        s = s[m.end():]
    s = SUBI.sub(r"\1\2", s)
    s2 = mitad(s)
    if s2 == s:
        s2 = colapsar(s)
    negs = [colapsar(mitad(PREF.sub("", n).strip())) for n in negs]
    negs = [n for n in negs if n and not re.fullmatch(r"[A-E]\.", n)]
    return pref + s2, negs


def limpia_texto(t, marca_anio):
    t = t.replace("\n", " ")
    # Marca de agua del autor y textos de cierre que se cuelan en el texto.
    t = re.sub(r"[Vv]ictor(?:\s+[Rr]amos\w*)?(?:\s+almiron)?", " ", t, flags=re.I)
    t = re.sub(r"[Vv]{3,}", " ", t)
    t = re.sub(r"\s*\d*\s*(?:0?\d\s+)?(?:de\s+)+\w+\s+\d{4}/.*?P.gina.*$", "", t, flags=re.I)
    for cola in (r"EXAMEN RESIDENTADO", r"Elaborado por", r"S.gueme en TikTok",
                 r"Para todos los futuros residentes", r".Estudia con pasi.n"):
        t = re.sub(r"\s*" + cola + r".*$", "", t, flags=re.I)
    if marca_anio:
        t = re.sub(marca_anio, " ", t)
    t = re.sub(r"\b(\d+(?:[.,]\d+)?) \1\b", r"\1", t)
    t = re.sub(r"^\s*([A-E])\.\s*", "", t)
    t = re.sub(r"\s+[A-E]\.\s*$", "", t)
    t = re.sub(r"\b(\w{1,2}) \1\b", r"\1", t)
    t = re.sub(r"\bdos puntos\b(?=\s+[a-záéíóúñ])", ":", t)
    t = re.sub(r"(?<!en )(?<!el )\bcoma\b(?=\s+[a-záéíóúñ])", ",", t)
    t = re.sub(r"(?<!el )(?<!del )\bpunto\b(?=\s+[a-záéíóúñ])", ".", t)
    t = re.sub(r"\s+([,.;:%])", r"\1", t)
    t = re.sub(r"([,.;:])(?=[^\s\d])", r"\1 ", t)
    t = re.sub(r"([A-Za-zº°’'])\s*:\s*(?=\S)", r"\1: ", t)
    # "FC: 120X’, ’," -> "FC: 120X’,": la comilla de los latidos por minuto se
    # quedo suelta al deshacer el doble dibujado.
    t = re.sub(r"(\d\s*X[’'])\s*,\s*[’']\s*,", r"\1,", t)
    return re.sub(r"\s{2,}", " ", t).strip()


def armar(crudo, total, letras, marca_anio):
    texto, tramos, pos = "", [], 0
    for s, ns in crudo:
        if texto:
            texto += "\n"
            pos += 1
        tramos.append((pos, pos + len(s), ns))
        texto += s
        pos += len(s)

    def buscar(marca, desde):
        return re.compile(r"(?:^|[\s\n])" + re.escape(marca) + r"\s*").search(texto, desde)

    preg, cursor = [], 0
    for n in range(1, total + 1):
        m = buscar(f"{n}.", cursor)
        if not m:
            print(f"# aviso: no se encontro la pregunta {n}", file=sys.stderr)
            continue
        ini, corte, opciones = m.end(), m.end(), []
        for L in letras:
            mo = buscar(f"{L}.", corte)
            if not mo:
                break
            opciones.append((L, mo.start(), mo.end()))
            corte = mo.end()
        sig = buscar(f"{n+1}.", corte) if n < total else None
        fin = sig.start() if sig else len(texto)
        enun = texto[ini:opciones[0][1]] if opciones else texto[ini:fin]
        p = {"n": n, "q": limpia_texto(enun, marca_anio), "o": [], "c": None}
        for k, (L, a, b) in enumerate(opciones):
            hasta = opciones[k + 1][1] if k + 1 < len(opciones) else fin
            cuerpo = limpia_texto(texto[b:hasta], marca_anio)
            dentro = [limpia_texto(x, marca_anio)
                      for ini2, fin2, ns in tramos if ini2 < hasta and fin2 > b for x in ns]
            if any(x == cuerpo or (len(x) >= 4 and (x in cuerpo or cuerpo in x))
                   for x in dentro if x):
                p["c"] = L
            p["o"].append((L, cuerpo))
        preg.append(p)
        cursor = fin
    return preg


# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--preguntas", type=int, default=100, help="cuantas trae el examen")
    ap.add_argument("--alternativas", type=int, default=4, help="4 desde 2023, 5 hasta 2022")
    ap.add_argument("--negrita", default="font10",
                    help="nombre (o trozo) de la fuente con que se marca la clave")
    ap.add_argument("--desde-pagina", type=int, default=2,
                    help="primera pagina con preguntas, contando desde 1")
    ap.add_argument("--anio", type=int, help="año, para la cabecera y para borrar la marca 'RM 2025 - A'")
    ap.add_argument("--prueba", default="", help="A o B")
    args = ap.parse_args()

    letras = LETRAS[:args.alternativas]
    marca = (r"\s*RM\s*" + str(args.anio) + r"\s*(?:[-–]\s*[A-Z]\s*)+") if args.anio else None

    crudo = [limpia_linea(s, ns) for s, ns in
             lineas_pdf(args.pdf, args.negrita, args.desde_pagina - 1)]
    crudo = [(s, ns) for s, ns in crudo if s and not BASURA.match(s)]
    preg = armar(crudo, args.preguntas, letras, marca)

    malas = [p["n"] for p in preg if len(p["o"]) != args.alternativas or not p["c"]]
    print(f"// {len(preg)} preguntas leidas de {args.pdf}", file=sys.stderr)
    if malas:
        print(f"// revisar a mano: {malas}", file=sys.stderr)

    print("// Sacado del PDF con tools/pdf-a-fuente.py. FALTA poner las cabeceras")
    print("// '@ Area / Especialidad' antes de importar; mira fuentes/README.md.")
    if args.anio:
        print(f"\n# año: {args.anio}")
    if args.prueba:
        print(f"# prueba: {args.prueba}")
    print("\n@ REVISAR / REVISAR")
    for p in preg:
        print(f"\n{p['n']}. {p['q']}")
        for L, t in p["o"]:
            print(f"{L}. {t}")
        print(f"Rpta: {p['c'] or '???'}")


if __name__ == "__main__":
    main()
