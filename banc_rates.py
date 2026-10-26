"""Taux de ratés (durée anormale) de Chatterbox MLX sur 12 phrases de Lysias, 3 séries de tirages.

  LECTEUR_MODELE_MLX=mlx-community/chatterbox-fp16 .venv-mlx/bin/python banc_rates.py
"""
import time

import numpy as np

from annotation import evenements, monotonique
from lire_discours import CARACTERES_PAR_SECONDE, fusionner, recoller_courts
from moteurs import MODELE_MLX, MoteurMLX
from nettoyage import adoucir, compresser_trous

segments = [e for e in recoller_courts(fusionner(evenements("annotations/lysias1.txt"))) if e[0] == "texte"]
moyens = [monotonique(e[1]) for e in segments if 25 <= len(e[1]) <= 200][20:32]
courts = [monotonique(e[1]) for e in segments if len(e[1]) < 40][:12]

t0 = time.time()
m = MoteurMLX("voix/homme2_propre.wav")
print(f"{MODELE_MLX} chargé en {time.time() - t0:.0f} s", flush=True)
for nom, textes in [("phrases moyennes", moyens), ("morceaux courts", courts)]:
    for serie in range(1, 4):
        rates, rapports, t0 = 0, [], time.time()
        for t in textes:
            y, _ = compresser_trous(adoucir(m.generer(t, 0.5, 0.5), m.sr), m.sr)
            rapport = len(y) / m.sr / (len(t) / CARACTERES_PAR_SECONDE)
            rapports.append(rapport)
            rates += not (0.7 <= rapport <= 1.45)
        print(f"{nom}, série {serie} : ratés {rates}/{len(textes)}, durée médiane ×{np.median(rapports):.2f} "
              f"({time.time() - t0:.0f} s)", flush=True)
