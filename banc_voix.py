"""Compare des voix de référence sur une même phrase, avec un moteur donné.

  .venv/bin/python banc_voix.py torch voix/cc0/*.wav
  .venv-pocket/bin/python banc_voix.py pocket voix/cc0/*.wav
"""
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf

from annotation import monotonique
from moteurs import MOTEURS

# Platon, Apologie de Socrate, 17a (The Greek Library / Perseus, CC BY-SA 4.0)
PHRASE = ("ὅτι μὲν ὑμεῖς, ὦ ἄνδρες Ἀθηναῖοι, πεπόνθατε ὑπὸ τῶν ἐμῶν κατηγόρων, οὐκ οἶδα· "
          "ἐγὼ δʼ οὖν καὶ αὐτὸς ὑπʼ αὐτῶν ὀλίγου ἐμαυτοῦ ἐπελαθόμην, οὕτω πιθανῶς ἔλεγον. "
          "καίτοι ἀληθές γε ὡς ἔπος εἰπεῖν οὐδὲν εἰρήκασιν.")

moteur_nom, voix = sys.argv[1], sys.argv[2:]
Path("comparaison").mkdir(exist_ok=True)
texte = monotonique(PHRASE)
for chemin in voix:
    t0 = time.time()
    moteur = MOTEURS[moteur_nom](chemin)
    chargement = time.time() - t0
    t0 = time.time()
    y = moteur.generer(texte, 0.5, 0.5)
    calcul = time.time() - t0
    y = y / max(np.max(np.abs(y)), 1e-6) * 0.89
    nom = f"comparaison/{moteur_nom}_{Path(chemin).stem}.wav"
    sf.write(nom, y, moteur.sr)
    duree = len(y) / moteur.sr
    print(f"{nom} : {duree:.1f} s d'audio, {calcul:.1f} s de calcul (×{calcul / duree:.2f}), "
          f"chargement {chargement:.0f} s", flush=True)
