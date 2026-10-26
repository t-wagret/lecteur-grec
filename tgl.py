"""Accès à la copie locale de The Greek Library (catalogue et textes)."""
import gzip
import json
import os
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from annotation import INTERTITRES_LECTURE

# dossier contenant catalog.json.gz et works/ (copie locale de The Greek Library)
RAW = Path(os.environ.get("TGL_RAW", Path.home() / "Documents/GitHub/frequentiel-grec/data/raw"))


def _sans_accents(s):
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if not unicodedata.combining(c))


def _chemin(entree):
    return RAW / (entree["objectKey"] + ".gz")


@lru_cache(maxsize=1)
def _catalogue():
    entrees = json.load(gzip.open(RAW / "catalog.json.gz"))["entries"]
    return [e for e in entrees if _chemin(e).exists()]


def chercher(requete, limite=60):
    """Œuvres disponibles localement dont l'auteur ou le titre contient tous les mots de la requête."""
    mots = _sans_accents(requete).split()
    sortie = []
    for e in _catalogue():
        cle = _sans_accents(f"{e['author']} {e['title']} {e['editionTitle'] or ''} {e['id']}")
        if all(m in cle for m in mots):
            sortie.append({"id": e["id"], "auteur": e["author"], "titre": e["title"], "taille": e["bytes"]})
            if len(sortie) >= limite:
                break
    return sortie


def _ref(chemin_labels, bloc):
    """Référence lisible : numéros des niveaux (livre, section) + numéro de vers éventuel."""
    parties = []
    for label in chemin_labels:
        dernier = label.split()[-1] if label.split() else ""
        if re.fullmatch(r"[0-9]+[a-z]?|[ivxlc]+", dernier, re.I) and not label.startswith(("Edition", "Level-X")):
            parties.append(dernier)
    if bloc.get("ref"):
        parties.append(str(bloc["ref"]))
    return ".".join(parties)


@lru_cache(maxsize=4)
def oeuvre(identifiant):
    """Métadonnées et unités de texte (paragraphes, vers, locuteurs) d'une œuvre."""
    entree = next(e for e in _catalogue() if e["id"] == identifiant)
    d = json.load(gzip.open(_chemin(entree)))
    unites, vues = [], {}

    def parcourir(section, chemin):
        chemin = chemin + [section.get("label") or ""]
        for bloc in section.get("blocks", []):
            texte = " ".join((bloc.get("text") or "").split())
            if not texte or bloc.get("type") == "note":
                continue
            if bloc.get("type") == "speaker":  # prendra la référence du vers qui suit
                unites.append({"ref": None, "type": "speaker", "texte": texte})
                continue
            ref = _ref(chemin, bloc) or str(len(unites) + 1)
            if texte in INTERTITRES_LECTURE:  # « Νόμος » partage la référence de sa section
                unites.append({"ref": ref, "type": bloc.get("type"), "texte": texte})
                continue
            # références en double (plusieurs paragraphes d'une même section) : suffixe
            vues[ref] = vues.get(ref, 0) + 1
            if vues[ref] > 1:
                ref = f"{ref}-{vues[ref]}"
            unites.append({"ref": ref, "type": bloc.get("type"), "texte": texte})
        for enfant in section.get("children", []):
            parcourir(enfant, chemin)

    for s in d["sections"]:
        parcourir(s, [])
    suivante = ""
    for u in reversed(unites):
        if u["ref"] is None:
            u["ref"] = suivante
        suivante = u["ref"]
    licence = (d.get("origin") or {}).get("licence") or (d.get("license") or {}).get("text")
    return {"id": identifiant, "auteur": entree["author"], "titre": entree["title"],
            "titreGrec": d.get("titleGreek") or d.get("title"), "source": d.get("sourceCitationShort"),
            "licence": licence, "unites": unites}


def est_intertitre(unite):
    """Unité non lue : nom de locuteur au théâtre, ou titre de pièce lue par le greffier."""
    return unite["type"] == "speaker" or unite["texte"] in INTERTITRES_LECTURE
