"""Moteurs de synthèse interchangeables : Chatterbox (PyTorch ou MLX) et Pocket TTS Greek.

Chaque moteur expose `sr`, `generer(texte, expression, cfg, duree_max) -> np.ndarray` (en grec) et
`choisir_voix(chemin)` pour changer de voix de référence en cours de lecture (les voix déjà
préparées sont gardées en mémoire). Chaque moteur tourne dans son propre environnement
(.venv, .venv-mlx, .venv-pocket) : ses modules ne sont importés qu'à l'usage.
"""
import copy
import os

import numpy as np

MODELE_MLX = os.environ.get("LECTEUR_MODELE_MLX", "mlx-community/chatterbox-8bit")


JETONS_PAR_SECONDE = 25  # Chatterbox produit 25 jetons de parole par seconde d'audio


class _AvecVoix:
    """Garde une préparation par voix ; sous-classes : _preparer(chemin) et _activer(preparation)."""

    def choisir_voix(self, chemin):
        if chemin == getattr(self, "_voix_active", None):
            return
        if chemin not in self._voix:
            self._voix[chemin] = self._preparer(chemin)
        self._activer(self._voix[chemin])
        self._voix_active = chemin


class MoteurMLX(_AvecVoix):
    nom = f"MLX ({MODELE_MLX.split('/')[-1]})"
    essais_max = 8  # rate environ 6 fois sur 10, mais chaque essai ne coûte que quelques secondes

    def __init__(self, voix):
        from mlx_audio.tts.utils import load_model

        self.model = load_model(MODELE_MLX)
        self.sr = self.model.sample_rate
        self._voix = {}
        self.choisir_voix(voix)

    def _preparer(self, chemin):
        return self.model.prepare_conditionals(chemin, self.sr)

    def _activer(self, conds):
        self.conds = conds

    def generer(self, texte, expression, cfg, duree_max=None):
        # plafond de jetons : un essai qui s'emballe est coupé tôt au lieu de bavarder 40 s
        plafond = int(duree_max * JETONS_PAR_SECONDE) + 20 if duree_max else 1000
        morceaux = self.model.generate(texte, conds=self.conds, lang_code="el", exaggeration=expression,
                                       cfg_weight=cfg, repetition_penalty=2.0, max_new_tokens=plafond,
                                       verbose=False)
        return np.concatenate([np.array(r.audio, dtype=np.float32) for r in morceaux])


class MoteurTorch(_AvecVoix):
    nom = "Chatterbox PyTorch"
    essais_max = 4

    def __init__(self, voix):
        import torch
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS

        device = "mps" if torch.backends.mps.is_available() else "cpu"
        self.model = ChatterboxMultilingualTTS.from_pretrained(device=device)
        self.sr = self.model.sr
        self._voix = {}
        self.choisir_voix(voix)

    def _preparer(self, chemin):
        self.model.prepare_conditionals(chemin)
        return copy.copy(self.model.conds)

    def _activer(self, conds):
        self.model.conds = conds

    def generer(self, texte, expression, cfg, duree_max=None):
        wav = self.model.generate(texte, language_id="el", exaggeration=expression, cfg_weight=cfg)
        return wav.squeeze(0).cpu().numpy()


class MoteurPocket(_AvecVoix):
    """Pocket TTS Greek (Myned AI, CC BY 4.0) : modèle entraîné sur le seul grec, rapide sur CPU.
    Pas de réglage d'émotion : l'expression est rendue par la température (0,3 calme → 0,7 vif)."""
    nom = "Pocket TTS Greek"
    essais_max = 4

    def __init__(self, voix):
        import torch
        from pocket_tts import TTSModel

        torch.set_num_threads(4)
        self.model = TTSModel.load_model(config="hf://myned-ai/pocket-tts-greek/greek.yaml")
        self.sr = self.model.sample_rate
        self._voix = {}
        self.choisir_voix(voix)

    def _preparer(self, chemin):
        return self.model.get_state_for_audio_prompt(chemin)

    def _activer(self, etat):
        self.etat = etat

    def generer(self, texte, expression, cfg, duree_max=None):
        self.model.temp = min(max(0.3 + (expression - 0.35) * 0.6, 0.3), 0.7)
        return self.model.generate_audio(self.etat, texte).numpy().astype(np.float32)


MOTEURS = {"mlx": MoteurMLX, "torch": MoteurTorch, "pocket": MoteurPocket}
