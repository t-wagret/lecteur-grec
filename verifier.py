"""Vérifie qu'une annotation n'altère pas le texte grec source et que ses marques sont valides.

  .venv/bin/python verifier.py annotations/lysias1.txt textes/lysias1.txt
"""
import difflib
import json
import sys
from collections import Counter
from pathlib import Path

from annotation import evenements, monotonique, texte_brut

INTERTITRES = {"Νόμος", "Μάρτυρες", "Νόμοι", "Μαρτυρία", "Μαρτυρίαι"}

annotation, source = sys.argv[1], sys.argv[2]
lignes = [l.split("\t", 1)[1].strip() for l in open(source, encoding="utf-8") if "\t" in l]
attendu = "".join("".join(l.split()) for l in lignes if l not in INTERTITRES)
obtenu = "".join(texte_brut(annotation).split())

erreurs = 0
if attendu != obtenu:
    erreurs += 1
    m = difflib.SequenceMatcher(None, attendu, obtenu, autojunk=False)
    for op, a1, a2, b1, b2 in m.get_opcodes():
        if op != "equal":
            print(f"TEXTE MODIFIÉ ({op}) près de « …{attendu[max(a1 - 25, 0):a1]}… »")
            print(f"   source     : {attendu[a1:a2]!r}")
            print(f"   annotation : {obtenu[b1:b2]!r}")
else:
    print("Texte grec identique à la source ✓")

# caractères que le modèle ne connaît pas, après conversion monotonique
vocab_json = next(Path.home().glob(".cache/huggingface/hub/models--ResembleAI--chatterbox/snapshots/*/grapheme_mtl_merged_expanded_v1.json"))
vocab = set(json.load(open(vocab_json))["model"]["vocab"])
evts = evenements(annotation)
inconnus = Counter(c for e in evts if e[0] == "texte" for c in monotonique(e[1]) if c not in vocab and not c.isspace())
if inconnus:
    erreurs += 1
    print("Caractères inconnus du modèle :", dict(inconnus))

textes = [e for e in evts if e[0] == "texte"]
emotions = Counter(e[2] for e in textes)
caracteres = sum(len(e[1]) for e in textes)
print(f"{len(textes)} segments, {sum(1 for e in evts if e[0] == 'souffle')} souffles, "
      f"{sum(1 for e in evts if e[0] == 'pause')} pauses")
print("Émotions :", ", ".join(f"{k} {v}" for k, v in emotions.most_common()))
print(f"Durée estimée : ~{caracteres / 14 / 60:.0f} min d'audio")
sys.exit(1 if erreurs else 0)
