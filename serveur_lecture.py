"""Petit serveur local qui lit à voix haute le grec envoyé par l'extension Chrome (dossier extension/).

  .venv-pocket/bin/python serveur_lecture.py        (ou double-clic sur « Lancer le lecteur.command »)

Moteur : Pocket TTS Greek, assez rapide pour lire à la demande (pas de réglage d'émotion).
Chaque morceau lu est gardé dans audio/extension.cache : une relecture est immédiate.
"""
import hashlib
import io
import threading
from pathlib import Path

import numpy as np
import soundfile as sf
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from annotation import monotonique
from lire_discours import PAUSE_COUPURE_MS, chemin_voix, couper, generer
from moteurs import MoteurPocket
from nettoyage import fondus

PORT = 8766
VOIX = ["spyros", "kostas", "athina", "katerina"]
EXPRESSION = 0.5  # température moyenne : ni monocorde ni instable
CACHE = Path(__file__).parent / "audio" / "extension.cache"
CACHE.mkdir(parents=True, exist_ok=True)

app = FastAPI()
verrou = threading.Lock()  # un seul calcul à la fois : le modèle n'est pas partagé entre fils
moteur = None


class Demande(BaseModel):
    texte: str
    voix: str = "spyros"


@app.get("/etat")
def etat():
    return {"pret": moteur is not None, "voix": VOIX}


@app.post("/lire")
def lire(d: Demande):
    if d.voix not in VOIX:
        raise HTTPException(400, "voix inconnue")
    texte = monotonique(d.texte)
    if not texte:
        raise HTTPException(400, "texte vide")
    cle = hashlib.sha1(f"{moteur.nom}|{d.voix}|{texte}".encode()).hexdigest()[:16]
    fichier = CACHE / f"{cle}.wav"
    if not fichier.exists():
        with verrou:
            moteur.choisir_voix(chemin_voix(d.voix))
            morceaux = []
            for i, bout in enumerate(couper(texte)):
                if i:
                    morceaux.append(np.zeros(int(moteur.sr * PAUSE_COUPURE_MS / 1000), np.float32))
                y, _ = generer(moteur, bout, EXPRESSION, 0.5)
                morceaux.append(fondus(y, moteur.sr))
            audio = np.concatenate(morceaux)
            audio = audio / max(np.max(np.abs(audio)), 1e-6) * 0.89
            tampon = io.BytesIO()
            sf.write(tampon, audio.astype(np.float32), moteur.sr, format="WAV", subtype="PCM_16")
            fichier.write_bytes(tampon.getvalue())
    return Response(fichier.read_bytes(), media_type="audio/wav")


if __name__ == "__main__":
    print("Chargement de la voix grecque (Pocket TTS)…", flush=True)
    moteur = MoteurPocket(chemin_voix(VOIX[0]))
    print(f"Lecteur prêt (port {PORT}). Laisse cette fenêtre ouverte pendant la lecture.", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
