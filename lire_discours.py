"""Lit un discours annoté (format décrit dans annotation.py) et produit un fichier audio.

  .venv/bin/python lire_discours.py annotations/lysias1.txt -o lysias1.wav
  .venv/bin/python lire_discours.py annotations/lysias1.txt -o essai.wav --de 11 --a 13
  .venv-mlx/bin/python lire_discours.py annotations/lysias1.txt -o rapide.wav --moteur mlx   (8x plus rapide, plus de ratés)

Chaque segment est généré, débruité, débarrassé de ses trous parasites, puis contrôlé :
s'il est anormalement long ou court pour son texte (raté du modèle), il est régénéré.
"""
import argparse
import hashlib
import os
import re
import time
from pathlib import Path

import numpy as np
import soundfile as sf

from annotation import EMOTIONS, VITESSES, evenements, monotonique
from moteurs import MOTEURS
from nettoyage import adoucir, compresser_trous, fondus

MAX_CARACTERES = 280  # au-delà, le segment est coupé aux fins de phrase
PAUSE_COUPURE_MS = 350
SOUFFLE_MS = 450  # [souffle] = respiration silencieuse, plus longue qu'une pause simple
CARACTERES_PAR_SECONDE = 14.5  # débit moyen mesuré sur cette voix
ESSAIS_MAX = 4


def tempo(y, facteur, n=1024):
    """Change la vitesse sans changer la hauteur (WSOLA)."""
    if facteur == 1.0 or len(y) < 4 * n:
        return y
    hs = n // 2
    ha = hs * facteur
    tol = n // 4
    fenetre = np.hanning(n)
    y = np.pad(y, (n, n + tol))
    nb = int((len(y) - 2 * n - tol) / ha)
    sortie = np.zeros(nb * hs + n)
    poids = np.zeros_like(sortie)
    prec = 0
    for k in range(nb):
        cible = int(k * ha) + n
        if k == 0:
            pos = cible
        else:
            # cherche autour de la position idéale le cadre qui prolonge le mieux le précédent
            suite = y[prec + hs: prec + hs + n]
            debut = max(cible - tol, 0)
            zone = y[debut: cible + tol + n]
            corr = np.correlate(zone, suite, mode="valid")
            pos = debut + int(np.argmax(corr))
        sortie[k * hs: k * hs + n] += y[pos: pos + n] * fenetre
        poids[k * hs: k * hs + n] += fenetre
        prec = pos
    sortie /= np.maximum(poids, 1e-3)
    return sortie[n: n + int((len(y) - 2 * n - tol) / facteur)]


def couper(texte):
    """Coupe un texte trop long aux fins de phrase ou de membre de phrase."""
    if len(texte) <= MAX_CARACTERES:
        return [texte]
    phrases = re.split(r"(?<=[.;·,])\s+", texte)
    morceaux, courant = [], ""
    for p in phrases:
        if courant and len(courant) + len(p) > MAX_CARACTERES:
            morceaux.append(courant)
            courant = p
        else:
            courant = f"{courant} {p}".strip()
    morceaux.append(courant)
    return morceaux


def dans_plage(section, de, a):
    if de is None and a is None:
        return True
    m = re.match(r"§(\d+)", section or "")
    if not m:
        return False
    n = int(m.group(1))
    return (de is None or n >= de) and (a is None or n <= a)


def fusionner(evts):
    """Réunit les textes consécutifs de même émotion et vitesse (ex. une phrase à cheval sur deux
    sections ou deux vers) pour que la voix les dise d'un seul souffle."""
    sortie = []
    for e in evts:
        prec = sortie[-1] if sortie else None
        if e[0] == "texte" and prec and prec[0] == "texte" and prec[2:4] == e[2:4] and prec[5] == e[5]:
            sortie[-1] = ("texte", f"{prec[1]} {e[1]}", prec[2], prec[3], prec[4], prec[5])
        else:
            sortie.append(e)
    return sortie


MIN_CARACTERES = 18  # en dessous, le modèle bafouille ou invente : on colle au voisin


def recoller_courts(evts):
    """Un morceau trop court (un ou deux mots isolés entre des pauses) est réuni au texte voisin
    à travers la pause la plus courte qui l'en sépare ; cette pause est alors remplacée par la
    respiration naturelle de la voix sur la ponctuation. Le style du morceau le plus long l'emporte."""
    evts = list(evts)
    i = 0
    while i < len(evts):
        e = evts[i]
        if e[0] != "texte" or len(e[1]) >= MIN_CARACTERES:
            i += 1
            continue
        choix = []
        for sens in (-1, 1):
            j, pauses = i + sens, 0
            while 0 <= j < len(evts) and evts[j][0] == "pause":
                pauses += evts[j][1]
                j += sens
            # jamais à travers un changement de voix : chaque locuteur garde ses répliques
            if 0 <= j < len(evts) and evts[j][0] == "texte" and evts[j][5] == e[5] and pauses <= 600:
                choix.append((pauses, sens, j))
        if not choix:
            i += 1
            continue
        _, sens, j = min(choix)
        a, b = (j, i) if sens == -1 else (i, j)
        long_ = evts[a] if len(evts[a][1]) >= len(evts[b][1]) else evts[b]
        texte_a = evts[a][1] if evts[a][1][-1] in ",.;·" else evts[a][1] + ","
        evts[a:b + 1] = [("texte", f"{texte_a} {evts[b][1]}", long_[2], long_[3], evts[a][4], e[5])]
        i = a
    return evts


def generer(moteur, texte, expression, cfg):
    """Génère un segment propre ; régénère en cas de raté (trou parasite, troncature, bafouillage)."""
    attendu = max(len(texte) / CARACTERES_PAR_SECONDE, 0.6)
    meilleur, meilleur_ecart = None, None
    essais_max = getattr(moteur, "essais_max", ESSAIS_MAX)
    for essai in range(1, essais_max + 1):
        y = adoucir(moteur.generer(texte, expression, cfg, duree_max=attendu * 1.8), moteur.sr)
        y, trou = compresser_trous(y, moteur.sr)
        duree = len(y) / moteur.sr
        rapport = duree / attendu
        ecart = abs(np.log(max(rapport, 1e-3))) + max(trou - 0.8, 0)
        if meilleur is None or ecart < meilleur_ecart:
            meilleur, meilleur_ecart = y, ecart
        # une vraie pause de virgule ne dépasse pas ~0,8 s ; au-delà, le modèle a déraillé
        if 0.7 <= rapport <= 1.45 and trou < 0.9:
            return meilleur, essai
        print(f"      raté (durée ×{rapport:.2f}, trou de {trou:.1f} s) : nouvel essai", flush=True)
    print(f"      ⚠ aucun essai correct sur {essais_max} : le moins mauvais est gardé", flush=True)
    return meilleur, essais_max


def chemin_voix(voix):
    """Un nom de voix (« kostas ») ou un chemin de fichier .wav -> chemin du fichier."""
    if voix.endswith(".wav") or "/" in voix:
        return voix
    for dossier in ("voix/propre", "voix/cc0", "voix"):  # voix/propre : versions débruitées
        chemin = Path(__file__).parent / dossier / f"{voix}.wav"
        if chemin.exists():
            return str(chemin)
    raise SystemExit(f"Voix introuvable : {voix} (voix/cc0/{voix}.wav)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("annotation")
    parser.add_argument("-o", "--sortie", default="lecture.wav")
    parser.add_argument("--voix", default=str(Path(__file__).parent / "voix" / "homme2_propre.wav"),
                        help="voix principale : un fichier .wav ou un nom de voix/cc0 (ex. spyros)")
    parser.add_argument("--de", type=int, help="première section à lire")
    parser.add_argument("--a", type=int, help="dernière section à lire")
    parser.add_argument("--moteur", choices=MOTEURS, default=os.environ.get("LECTEUR_MOTEUR", "torch"))
    parser.add_argument("--cache", help="dossier où garder chaque morceau généré, pour reprendre un long "
                                        "calcul interrompu (par défaut : <sortie>.morceaux)")
    args = parser.parse_args()

    evts, section = [], ""
    for e in evenements(args.annotation):
        if e[0] == "texte":
            section = e[4]
        if dans_plage(section, args.de, args.a):
            evts.append(e)
    evts = recoller_courts(fusionner(evts))

    print(f"Chargement du modèle ({MOTEURS[args.moteur].nom})...", flush=True)
    moteur = MOTEURS[args.moteur](chemin_voix(args.voix))
    sr = moteur.sr

    cache = Path(args.cache or f"{args.sortie}.morceaux")
    cache.mkdir(parents=True, exist_ok=True)
    morceaux = []
    nb_textes = sum(1 for e in evts if e[0] == "texte")
    fait = rates = 0
    start = time.time()
    for e in evts:
        if e[0] == "pause":
            morceaux.append(np.zeros(int(sr * e[1] / 1000)))
        elif e[0] == "souffle":
            morceaux.append(np.zeros(int(sr * SOUFFLE_MS / 1000)))
        else:
            _, texte, emotion, vitesse, section, voix = e
            moteur.choisir_voix(chemin_voix(voix or args.voix))
            fait += 1
            expression, cfg = EMOTIONS[emotion]
            for i, bout in enumerate(couper(monotonique(texte))):
                if i:
                    morceaux.append(np.zeros(int(sr * PAUSE_COUPURE_MS / 1000)))
                qui = f" [{voix}]" if voix else ""
                print(f"[{fait}/{nb_textes}] {section}{qui} {emotion}/{vitesse} : {bout[:45]}...", flush=True)
                cle = hashlib.sha1(f"{moteur.nom}|{chemin_voix(voix or args.voix)}|{bout}|{expression}|{cfg}|"
                                   f"{vitesse}".encode()).hexdigest()[:16]
                fichier = cache / f"{cle}.npy"
                if fichier.exists():  # déjà fait lors d'un calcul précédent
                    morceaux.append(np.load(fichier))
                    continue
                y, essais = generer(moteur, bout, expression, cfg)
                rates += essais - 1
                y = fondus(tempo(y, VITESSES[vitesse]), sr).astype(np.float32)
                np.save(fichier, y)
                morceaux.append(y)

    audio = np.concatenate(morceaux)
    audio = (audio / max(np.max(np.abs(audio)), 1e-6) * 0.89).astype(np.float32)  # crête à -1 dBFS
    sf.write(args.sortie, audio, sr)
    print(f"OK : {args.sortie} ({len(audio) / sr / 60:.1f} min d'audio, généré en {(time.time() - start) / 60:.0f} min, "
          f"{rates} segment(s) régénéré(s))")


if __name__ == "__main__":
    main()
