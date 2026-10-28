"""Annote automatiquement toute une œuvre de The Greek Library avec Claude, et l'enregistre
au même endroit que l'éditeur (annotations/oeuvres/<identifiant>.txt), prête à relire dans l'éditeur.

  .venv/bin/python annoter_oeuvre.py tlg0059.tlg002.local001
"""
import sys
import time

import tgl
from editeur import _elements_source, _entete, _fichier, _verifier_texte
from annotation import serialiser
from suggestions import suggerer

identifiant = sys.argv[1]
o = tgl.oeuvre(identifiant)
elements = _elements_source(o)
mots = sum(1 for e in elements if "mot" in e)
print(f"{o['auteur']}, {o['titre']} : {mots} mots", flush=True)

t0 = time.time()
suggerer(elements, 0, len(elements), o["auteur"], o["titre"],
         progression=lambda m: print(f"  {m} ({time.time() - t0:.0f} s)", flush=True))
_verifier_texte(identifiant, elements)
chemin = _fichier(identifiant)
chemin.write_text(serialiser(elements, _entete(o) + "# Annotation proposée par Claude, à relire.\n"), encoding="utf-8")
print(f"OK : {chemin} ({(time.time() - t0) / 60:.0f} min)")
