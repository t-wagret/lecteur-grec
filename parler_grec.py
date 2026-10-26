"""Génère un fichier audio en grec moderne avec Chatterbox Multilingual.

Exemples :
  .venv/bin/python parler_grec.py "Γεια σου! Τι κάνεις;" -o essai.wav
  .venv/bin/python parler_grec.py "Ο δράκος ξύπνησε..." -o drakos.wav --voix homme.wav --expression 0.8
"""
import argparse
import time
from pathlib import Path

import torch
import torchaudio
from chatterbox.mtl_tts import ChatterboxMultilingualTTS

parser = argparse.ArgumentParser(description="Texte grec -> fichier audio")
parser.add_argument("texte", help="le texte grec à lire")
parser.add_argument("-o", "--sortie", default="sortie.wav", help="fichier audio produit (.wav)")
VOIX_DEFAUT = Path(__file__).parent / "voix" / "homme2_propre.wav"  # Google FLEURS, CC-BY 4.0
parser.add_argument("--voix", default=str(VOIX_DEFAUT), help="enregistrement (~10 s) de la voix à imiter")
parser.add_argument("--expression", type=float, default=0.5, help="0.25 = calme, 0.5 = normal, 1.0+ = très expressif")
parser.add_argument("--cfg", type=float, default=0.5, help="plus bas (0.3) = débit plus lent et posé")
args = parser.parse_args()

device = "mps" if torch.backends.mps.is_available() else "cpu"
print(f"Chargement du modèle sur {device}...")
model = ChatterboxMultilingualTTS.from_pretrained(device=device)

start = time.time()
wav = model.generate(
    args.texte,
    language_id="el",
    audio_prompt_path=args.voix,
    exaggeration=args.expression,
    cfg_weight=args.cfg,
)
torchaudio.save(args.sortie, wav, model.sr)
print(f"OK : {args.sortie} ({wav.shape[-1] / model.sr:.1f} s d'audio, généré en {time.time() - start:.1f} s)")
