"""Suggestions d'annotation émotionnelle par Claude (programme `claude`, compte de l'utilisateur).

L'IA ne réécrit jamais le texte : elle reçoit les mots numérotés et renvoie seulement
des indices (début des segments d'émotion, emplacements des pauses). Le grec reste intact.
"""
import json
import os
import subprocess
import tempfile

from annotation import EMOTIONS, MARQUES_PAUSE, VITESSES

MOTS_PAR_APPEL = 900

SCHEMA = {
    "type": "object",
    "properties": {
        "segments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "debut": {"type": "integer"},
                    "emotion": {"type": "string", "enum": list(EMOTIONS)},
                    "vitesse": {"type": "string", "enum": list(VITESSES)},
                },
                "required": ["debut", "emotion", "vitesse"],
            },
        },
        "pauses": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "apres": {"type": "integer"},
                    "type": {"type": "string", "enum": MARQUES_PAUSE},
                },
                "required": ["apres", "type"],
            },
        },
    },
    "required": ["segments", "pauses"],
}

CONSIGNES = """Tu prépares la lecture à voix haute expressive d'un texte grec ancien par une voix de synthèse.
Œuvre : {auteur}, {titre}.
Le texte est donné mot par mot, chaque mot précédé de son numéro (n:mot). Les lignes « § » sont des repères de section,
les lignes « [[...]] » sont des intertitres non lus (nom du locuteur au théâtre, loi lue par le greffier).

Rends uniquement des indices de mots, jamais de texte grec :
1. segments : où commence chaque passage d'une émotion et d'une vitesse donnée. Le premier segment commence au mot {premier}.
   Change d'émotion aux frontières de membres de phrase, quand le ton change vraiment (en moyenne tous les 15 à 40 mots).
   Émotions possibles : {emotions}.
   Vitesses : lent (moments graves ou décisifs), posé, normal, vif, rapide (agitation, action précipitée). Garde la plupart en normal ou posé.
2. pauses : après quel mot placer une pause.
   « | » micro-pause pour détacher un membre de phrase ou préparer un mot fort ;
   « || » pause de fin de phrase ou de changement d'idée ;
   « ||| » longue pause entre deux mouvements du texte ;
   « |||| » silence dramatique, très rare (au plus un tous les 400 mots, seulement aux sommets d'intensité) ;
   « [souffle] » temps de respiration avant une longue phrase ou un nouveau mouvement (environ tous les 60 à 120 mots).
   Ne mets pas de pause après chaque virgule : la voix marque déjà la ponctuation. Vise une lecture d'orateur ou d'acteur, vivante mais sobre.
Tiens compte du genre (discours judiciaire, épopée, dialogue, tragédie…), de qui parle et de ce qui est dit.
L'émotion en cours avant ce passage est : {emotion_prec}.

Texte :
{texte}
"""


class ErreurClaude(RuntimeError):
    pass


def _appeler_claude(prompt):
    commande = ["claude", "-p", "--output-format", "json", "--no-session-persistence",
                "--tools", "", "--json-schema", json.dumps(SCHEMA)]
    if os.environ.get("TGL_MODELE"):
        commande += ["--model", os.environ["TGL_MODELE"]]
    with tempfile.TemporaryDirectory() as dossier:
        try:
            proc = subprocess.run(commande, input=prompt, capture_output=True, text=True,
                                  cwd=dossier, timeout=900)
        except FileNotFoundError:
            raise ErreurClaude("Le programme « claude » est introuvable sur ce Mac.")
        except subprocess.TimeoutExpired:
            raise ErreurClaude("Claude n'a pas répondu à temps (15 min).")
    try:
        reponse = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise ErreurClaude(f"Réponse illisible de claude : {(proc.stderr or proc.stdout)[:300]}")
    if reponse.get("is_error"):
        message = str(reponse.get("result", ""))
        if "authenticat" in message.lower() or "login" in message.lower():
            message = ("Claude n'est pas connecté à ton compte. Ouvre le Terminal, tape « claude », "
                       "puis « /login », et réessaie.")
        raise ErreurClaude(message)
    resultat = reponse.get("structured_output")
    if resultat is None:
        resultat = json.loads(reponse.get("result", "{}"))
    return resultat


def _texte_numerote(elements, debut, fin):
    lignes, section, courante = [], None, []
    for i in range(debut, fin):
        e = elements[i]
        if e["section"] != section:
            if courante:
                lignes.append(" ".join(courante))
            section = e["section"]
            courante = [f"§{section}"]
        courante.append(f"[[{e['intertitre']}]]" if "intertitre" in e else f"{i}:{e['mot']}")
    lignes.append(" ".join(courante))
    return "\n".join(lignes)


def _decouper(elements, debut, fin):
    """Tranches d'environ MOTS_PAR_APPEL mots, coupées à une frontière de section."""
    tranches, depart = [], debut
    while depart < fin:
        limite = min(depart + MOTS_PAR_APPEL, fin)
        if limite < fin:
            section = elements[limite]["section"]
            recul = limite
            while recul > depart + MOTS_PAR_APPEL // 2 and elements[recul]["section"] == section:
                recul -= 1
            limite = recul + 1 if recul > depart + MOTS_PAR_APPEL // 2 else limite
        tranches.append((depart, limite))
        depart = limite
    return tranches


def suggerer(elements, debut, fin, auteur="", titre="", progression=None):
    """Remplit émotions, vitesses et pauses des éléments [debut, fin) (modifiés en place)."""
    tranches = _decouper(elements, debut, fin)
    emotion_prec = elements[debut - 1].get("emotion", "neutre") if debut > 0 else "neutre"
    for n, (a, b) in enumerate(tranches, 1):
        if progression:
            progression(f"Claude annote la partie {n}/{len(tranches)}…")
        premier = next((i for i in range(a, b) if "mot" in elements[i]), a)
        prompt = CONSIGNES.format(auteur=auteur, titre=titre, premier=premier,
                                  emotions=", ".join(EMOTIONS), emotion_prec=emotion_prec,
                                  texte=_texte_numerote(elements, a, b))
        r = _appeler_claude(prompt)
        segments = sorted((s for s in r.get("segments", []) if a <= s["debut"] < b
                           and s["emotion"] in EMOTIONS and s["vitesse"] in VITESSES),
                          key=lambda s: s["debut"])
        courant = {"emotion": emotion_prec, "vitesse": "normal"}
        k = 0
        for i in range(a, b):
            while k < len(segments) and segments[k]["debut"] <= i:
                courant = segments[k]
                k += 1
            if "mot" in elements[i]:
                elements[i]["emotion"], elements[i]["vitesse"] = courant["emotion"], courant["vitesse"]
                elements[i]["apres"] = []
        for p in r.get("pauses", []):
            i = p["apres"]
            if a <= i < b and "mot" in elements[i] and p["type"] in MARQUES_PAUSE:
                if p["type"] not in elements[i]["apres"]:
                    elements[i]["apres"].append(p["type"])
        emotion_prec = courant["emotion"]
    return elements
