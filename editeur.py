"""Éditeur d'annotation émotionnelle des textes grecs de The Greek Library.

  .venv/bin/python editeur.py        puis ouvrir http://localhost:8765
"""
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

import tgl
from annotation import EMOTIONS, MARQUES_PAUSE, VITESSES, modele_depuis_annotation, serialiser
from suggestions import ErreurClaude, suggerer

ICI = Path(__file__).parent
# moteur de lecture : PyTorch par défaut (moins de ratés) ; LECTEUR_MOTEUR=mlx pour Chatterbox MLX,
# 8 fois plus rapide mais qui rate encore les morceaux courts (voir moteurs.py)
MOTEUR_LECTURE = os.environ.get("LECTEUR_MOTEUR", "torch")
PYTHON_LECTURE = ICI / ".venv-mlx" / "bin" / "python" if MOTEUR_LECTURE == "mlx" else Path(sys.executable)
ANNOTATIONS = ICI / "annotations" / "oeuvres"
AUDIO = ICI / "audio"
TRAVAUX = ICI / "travaux"
for d in (ANNOTATIONS, AUDIO, TRAVAUX):
    d.mkdir(parents=True, exist_ok=True)

app = FastAPI()
travaux = {}  # identifiant -> état d'un travail long (suggestion ou lecture)
verrou_lecture = threading.Lock()


def _fichier(identifiant):
    if not re.fullmatch(r"[\w.]+", identifiant):
        raise HTTPException(400, "identifiant invalide")
    return ANNOTATIONS / f"{identifiant}.txt"


def _elements_source(o):
    elements = []
    for u in o["unites"]:
        if tgl.est_intertitre(u):
            elements.append({"intertitre": u["texte"], "section": u["ref"]})
        else:
            for mot in u["texte"].split():
                elements.append({"mot": mot, "section": u["ref"], "emotion": "neutre",
                                 "vitesse": "normal", "apres": []})
    return elements


def _par_section(elements):
    groupes = {}
    for e in elements:
        groupes.setdefault(e["section"], []).append(e)
    return groupes


def _fusionner_sauvegarde(source, chemin):
    """Reprend les annotations enregistrées, section par section, si le texte n'a pas changé."""
    if not chemin.exists():
        return source, 0
    tout = modele_depuis_annotation(chemin.read_text(encoding="utf-8"))
    mots_source = [e for e in source if "mot" in e]
    mots_sauves = [e for e in tout if "mot" in e]
    if "".join(e["mot"] for e in mots_source) == "".join(e["mot"] for e in mots_sauves):
        # même texte du début à la fin (même si les mots sont découpés autrement) :
        # on aligne caractère par caractère, quelles que soient les références de section
        debuts, fins, pos = {}, {}, 0
        for k, a in enumerate(mots_sauves):
            debuts[pos] = k
            pos += len(a["mot"])
            fins[pos] = k

        def copier(e, a, apres):
            e.update(emotion=a["emotion"], vitesse=a["vitesse"], apres=list(apres))
            e.pop("voix", None)
            if a.get("voix"):
                e["voix"] = a["voix"]

        # groupes de mots source couverts par un même mot enregistré
        groupes, pos, k = [], 0, 0
        for e in mots_source:
            if pos in debuts:
                k = debuts[pos]
                groupes.append((k, []))
            groupes[-1][1].append(e)
            pos += len(e["mot"])
            if pos in fins and len(groupes[-1][1]) == 1:
                # mot source plus long que le mot enregistré (« πέντε,ὡς ») : pauses du dernier morceau
                groupes[-1] = (k, groupes[-1][1], fins[pos])
        for groupe in groupes:
            k, mots = groupe[0], groupe[1]
            a = mots_sauves[k]
            if len(mots) == 1:
                fin = mots_sauves[groupe[2]] if len(groupe) > 2 else a
                copier(mots[0], a, fin["apres"])
                continue
            # un mot enregistré qui couvrait plusieurs mots (« ἔσονται;ἔγωγε. », répliques collées) :
            # sa pause va à la fin de phrase, et la suite prend le style du mot enregistré suivant
            coupe = next((i for i, m in enumerate(mots[:-1]) if m["mot"][-1] in ".;·;!"), len(mots) - 1)
            suivant = mots_sauves[k + 1] if k + 1 < len(mots_sauves) else a
            for i, m in enumerate(mots):
                copier(m, a if i <= coupe else suivant, a["apres"] if i == coupe else [])
        return source, len(_par_section(source))
    sauve = _par_section(tout)
    repris = 0
    for section, elems in _par_section(source).items():
        anciens = sauve.get(section)
        mots = [e for e in elems if "mot" in e]
        anciens_mots = [e for e in (anciens or []) if "mot" in e]
        if anciens and [e["mot"] for e in mots] == [e["mot"] for e in anciens_mots]:
            for e, a in zip(mots, anciens_mots):
                e.update(emotion=a["emotion"], vitesse=a["vitesse"], apres=a["apres"])
                if a.get("voix"):
                    e["voix"] = a["voix"]
            repris += 1
    return source, repris


def _verifier_texte(identifiant, elements):
    """Garantit que seules les marques ont changé, jamais le texte grec."""
    attendu = [e.get("mot") or e.get("intertitre") for e in _elements_source(tgl.oeuvre(identifiant))]
    recu = [e.get("mot") or e.get("intertitre") for e in elements]
    if attendu != recu:
        raise HTTPException(400, "Le texte grec ne correspond plus à la source : enregistrement refusé.")
    for e in elements:
        if "mot" in e and (e["emotion"] not in EMOTIONS or e["vitesse"] not in VITESSES
                           or any(p not in MARQUES_PAUSE for p in e["apres"])):
            raise HTTPException(400, f"Marque inconnue près de « {e['mot']} »")


def _entete(o):
    return (f"# {o['auteur']}, {o['titre']}\n# Source : The Greek Library, {o['id']}"
            f" ({o['licence'] or 'licence non précisée'})\n# {o['source'] or ''}\n")


@app.get("/", response_class=HTMLResponse)
def page():
    return (ICI / "static" / "editeur.html").read_text(encoding="utf-8")


@app.get("/api/config")
def config():
    return {"emotions": list(EMOTIONS), "vitesses": list(VITESSES), "pauses": MARQUES_PAUSE}


@app.get("/api/oeuvres")
def oeuvres(q: str = ""):
    resultats = tgl.chercher(q) if q.strip() else []
    for r in resultats:
        r["annotee"] = _fichier(r["id"]).exists()
    return resultats


@app.get("/api/oeuvre/{identifiant}")
def ouvrir(identifiant: str):
    try:
        o = tgl.oeuvre(identifiant)
    except StopIteration:
        raise HTTPException(404, "œuvre introuvable")
    elements, repris = _fusionner_sauvegarde(_elements_source(o), _fichier(identifiant))
    return {"id": o["id"], "auteur": o["auteur"], "titre": o["titre"], "titreGrec": o["titreGrec"],
            "licence": o["licence"], "source": o["source"], "elements": elements, "sectionsReprises": repris}


class Enregistrement(BaseModel):
    elements: list


@app.post("/api/oeuvre/{identifiant}/enregistrer")
def enregistrer(identifiant: str, corps: Enregistrement):
    _verifier_texte(identifiant, corps.elements)
    o = tgl.oeuvre(identifiant)
    chemin = _fichier(identifiant)
    chemin.write_text(serialiser(corps.elements, _entete(o)), encoding="utf-8")
    return {"fichier": str(chemin.relative_to(ICI))}


class Plage(BaseModel):
    elements: list
    debut: int
    fin: int


def _nouveau_travail(nature):
    tid = uuid.uuid4().hex[:10]
    travaux[tid] = {"nature": nature, "etat": "en cours", "message": "Démarrage…", "debut": time.time()}
    return tid


@app.post("/api/oeuvre/{identifiant}/suggerer")
def lancer_suggestion(identifiant: str, corps: Plage):
    _verifier_texte(identifiant, corps.elements)
    o = tgl.oeuvre(identifiant)
    tid = _nouveau_travail("suggestion")

    def tache():
        t = travaux[tid]
        try:
            elements = suggerer(corps.elements, corps.debut, corps.fin, o["auteur"], o["titre"],
                                progression=lambda m: t.update(message=m))
            t.update(etat="fini", message="Suggestions prêtes", elements=elements)
        except ErreurClaude as err:
            t.update(etat="erreur", message=str(err))
        except Exception as err:  # noqa: BLE001 — l'erreur est montrée dans la page
            t.update(etat="erreur", message=f"Erreur inattendue : {err}")

    threading.Thread(target=tache, daemon=True).start()
    return {"travail": tid}


@app.post("/api/oeuvre/{identifiant}/lire")
def lancer_lecture(identifiant: str, corps: Plage):
    _verifier_texte(identifiant, corps.elements)
    if not verrou_lecture.acquire(blocking=False):
        raise HTTPException(409, "Une lecture est déjà en cours de calcul.")
    o = tgl.oeuvre(identifiant)
    tid = _nouveau_travail("lecture")
    extrait = corps.elements[corps.debut:corps.fin]
    sections = [e["section"] for e in extrait]
    nom = f"{identifiant}_{sections[0]}-{sections[-1]}_{time.strftime('%H%M%S')}".replace("/", "-")
    annotation = TRAVAUX / f"{nom}.txt"
    annotation.write_text(serialiser(extrait, _entete(o)), encoding="utf-8")
    wav = AUDIO / f"{nom}.wav"

    def tache():
        t = travaux[tid]
        try:
            proc = subprocess.Popen([str(PYTHON_LECTURE), str(ICI / "lire_discours.py"), str(annotation),
                                     "-o", str(wav), "--moteur", MOTEUR_LECTURE],
                                    cwd=ICI, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            journal = []
            for ligne in proc.stdout:
                journal.append(ligne)
                if m := re.match(r"\[(\d+)/(\d+)\]", ligne):
                    t.update(message=f"Lecture du segment {m.group(1)} sur {m.group(2)}…",
                             fraction=int(m.group(1)) / int(m.group(2)))
                elif "Chargement" in ligne:
                    t.update(message="Chargement de la voix…")
            if proc.wait() != 0 or not wav.exists():
                t.update(etat="erreur", message="La lecture a échoué : " + "".join(journal[-3:])[:400])
                return
            m4a = wav.with_suffix(".m4a")
            subprocess.run(["afconvert", "-f", "m4af", "-d", "aac@44100", "-c", "1", str(wav), str(m4a)],
                           capture_output=True)
            t.update(etat="fini", message="Lecture prête", wav=f"/audio/{wav.name}",
                     m4a=f"/audio/{m4a.name}" if m4a.exists() else None)
        finally:
            verrou_lecture.release()

    threading.Thread(target=tache, daemon=True).start()
    return {"travail": tid}


@app.get("/api/travail/{tid}")
def etat_travail(tid: str):
    if tid not in travaux:
        raise HTTPException(404, "travail inconnu")
    t = dict(travaux[tid])
    t["duree"] = int(time.time() - t["debut"])
    return t


@app.get("/audio/{nom}")
def audio(nom: str):
    chemin = AUDIO / nom
    if not re.fullmatch(r"[\w.-]+\.(wav|m4a)", nom) or not chemin.exists():
        raise HTTPException(404)
    return FileResponse(chemin, filename=nom)


if __name__ == "__main__":
    print("Éditeur prêt : http://localhost:8765")
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="warning")
