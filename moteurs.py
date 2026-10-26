"""Moteurs de synthèse Chatterbox interchangeables : MLX (rapide, puces Apple) ou PyTorch.

Chaque moteur expose `sr` et `generer(texte, expression, cfg) -> np.ndarray` (grec, voix modèle fixée).
MLX tourne dans .venv-mlx, PyTorch dans .venv : chaque module n'est importé qu'à l'usage.
"""
import os

import numpy as np

MODELE_MLX = os.environ.get("LECTEUR_MODELE_MLX", "mlx-community/chatterbox-8bit")


JETONS_PAR_SECONDE = 25  # Chatterbox produit 25 jetons de parole par seconde d'audio


class MoteurMLX:
    nom = f"MLX ({MODELE_MLX.split('/')[-1]})"
    essais_max = 8  # rate environ 6 fois sur 10, mais chaque essai ne coûte que quelques secondes

    def __init__(self, voix):
        from mlx_audio.tts.utils import load_model

        self.model = load_model(MODELE_MLX)
        self.sr = self.model.sample_rate
        self.conds = self.model.prepare_conditionals(voix, self.sr)

    def generer(self, texte, expression, cfg, duree_max=None):
        # plafond de jetons : un essai qui s'emballe est coupé tôt au lieu de bavarder 40 s
        plafond = int(duree_max * JETONS_PAR_SECONDE) + 20 if duree_max else 1000
        morceaux = self.model.generate(texte, conds=self.conds, lang_code="el", exaggeration=expression,
                                       cfg_weight=cfg, repetition_penalty=2.0, max_new_tokens=plafond,
                                       verbose=False)
        return np.concatenate([np.array(r.audio, dtype=np.float32) for r in morceaux])


class MoteurTorch:
    nom = "PyTorch"
    essais_max = 4

    def __init__(self, voix):
        import torch
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS

        device = "mps" if torch.backends.mps.is_available() else "cpu"
        self.model = ChatterboxMultilingualTTS.from_pretrained(device=device)
        self.model.prepare_conditionals(voix)
        self.sr = self.model.sr

    def generer(self, texte, expression, cfg, duree_max=None):
        wav = self.model.generate(texte, language_id="el", exaggeration=expression, cfg_weight=cfg)
        return wav.squeeze(0).cpu().numpy()


MOTEURS = {"mlx": MoteurMLX, "torch": MoteurTorch}
