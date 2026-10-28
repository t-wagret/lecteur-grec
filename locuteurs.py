"""Attribue des répliques à une autre voix dans une annotation enregistrée par l'éditeur.

  .venv/bin/python locuteurs.py tlg0059.tlg002.local001 kostas repliques/apologie_meletos.txt

Le fichier de répliques donne une réplique par ligne : « section | texte grec exact | émotion »
(émotion facultative, « ferme » par défaut). Les répliques sont cherchées dans l'ordre, chacune
après la précédente ; chacune reçoit une micro-pause avant et une pause après, pour marquer
le changement de locuteur.
"""
import sys

import tgl
from annotation import serialiser
from editeur import _entete, _fichier, _verifier_texte, ouvrir

identifiant, voix, fichier = sys.argv[1:4]
o = ouvrir(identifiant)
elements = o["elements"]
repliques = [[c.strip() for c in l.split("|")] for l in open(fichier, encoding="utf-8")
             if l.strip() and not l.lstrip().startswith("#")]

depart, manquantes = 0, []
for section, texte, *reste in repliques:
    cible, emotion = texte.split(), (reste[0] if reste and reste[0] else "ferme")
    trouve = False
    for i in range(depart, len(elements) - len(cible) + 1):
        bloc = elements[i:i + len(cible)]
        if bloc[0]["section"] == section and [e.get("mot") for e in bloc] == cible:
            for e in bloc:
                e.update(voix=voix, emotion=emotion, vitesse="normal", apres=[])
            bloc[-1]["apres"] = ["||"]
            prec = next((e for e in reversed(elements[:i]) if "mot" in e), None)
            if prec is not None and not prec["apres"]:
                prec["apres"] = ["|"]
            depart, trouve = i + len(cible), True
            break
    if not trouve:
        manquantes.append(f"§{section} {texte.strip()}")

if manquantes:
    raise SystemExit("Répliques introuvables (rien n'est enregistré) :\n  " + "\n  ".join(manquantes))
_verifier_texte(identifiant, elements)
entete = _entete(tgl.oeuvre(identifiant)) + "# Annotation proposée par Claude, à relire.\n"
_fichier(identifiant).write_text(serialiser(elements, entete), encoding="utf-8")
print(f"OK : {len(repliques)} répliques attribuées à {voix}")
