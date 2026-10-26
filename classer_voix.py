"""Classe les enregistrements masculins de FLEURS par qualité (durée, bruit de fond, hauteur de voix)."""
import csv
import sys
from pathlib import Path

import librosa
import numpy as np

dossier = Path(sys.argv[1])
wavs = {p.name: p for p in dossier.rglob("*.wav")}
resultats = []
with open(dossier / "dev.tsv", encoding="utf-8") as f:
    for ligne in csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
        nom, texte, genre = ligne[1], ligne[2], ligne[-1]
        if genre != "MALE" or nom not in wavs:
            continue
        y, sr = librosa.load(wavs[nom], sr=16000)
        duree = len(y) / sr
        if duree < 8:
            continue
        rms = librosa.feature.rms(y=y, frame_length=1024, hop_length=256)[0]
        # rapport parole / bruit : trames fortes vs trames les plus silencieuses
        snr = 20 * np.log10(np.percentile(rms, 90) / max(np.percentile(rms, 10), 1e-6))
        f0, voiced, _ = librosa.pyin(y, fmin=60, fmax=300, sr=sr)
        hauteur = float(np.nanmedian(f0[voiced])) if voiced.any() else 0
        resultats.append((snr, duree, hauteur, nom, texte))

resultats.sort(reverse=True)
for snr, duree, hauteur, nom, texte in resultats[:15]:
    print(f"{snr:5.1f} dB  {duree:5.1f} s  {hauteur:4.0f} Hz  {nom}  {texte[:50]}")
