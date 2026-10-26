"""Format d'annotation émotionnelle pour la lecture de textes grecs.

Le texte grec est recopié tel quel, avec des marques entre ses mots :

  {émotion}            change l'émotion à partir de là (voir EMOTIONS)
  {émotion, vitesse}   change aussi la vitesse : lent, posé, normal, vif, rapide
  |   ||   |||         micro-pause, pause, longue pause
  ||||                 silence dramatique (moments forts, à utiliser rarement)
  [souffle]            temps de respiration (silence plus long qu'une pause)
  [[Νόμος]]            intertitre non lu (lecture d'une loi, témoins) : silence
  §12                  repère de section, ignoré à la lecture
  # ...                ligne de commentaire
"""
import re
import unicodedata

# émotion -> (exaggeration, cfg_weight) de Chatterbox ; cfg bas = débit plus lent et posé
EMOTIONS = {
    "neutre": (0.5, 0.5),
    "narratif": (0.45, 0.5),
    "calme": (0.4, 0.5),
    "solennel": (0.45, 0.35),
    "sincère": (0.5, 0.4),
    "persuasif": (0.6, 0.45),
    "tendre": (0.45, 0.35),
    "nostalgique": (0.5, 0.35),
    "triste": (0.35, 0.3),
    "troublé": (0.65, 0.4),
    "inquiet": (0.6, 0.4),
    "joueur": (0.7, 0.5),
    "ironique": (0.65, 0.45),
    "méprisant": (0.75, 0.4),
    "ferme": (0.6, 0.45),
    "amer": (0.7, 0.35),
    "indigné": (0.85, 0.35),
    "colère": (1.0, 0.3),
    "menaçant": (0.8, 0.3),
    "suppliant": (0.7, 0.3),
    "triomphant": (0.8, 0.45),
}

# vitesse -> facteur de tempo appliqué après génération (hauteur inchangée)
VITESSES = {"lent": 0.88, "posé": 0.94, "normal": 1.0, "vif": 1.07, "rapide": 1.14}

PAUSES_MS = {"|": 250, "||": 600, "|||": 1200, "||||": 2000}
INTERTITRE_MS = 2000  # loi ou témoins lus par le greffier
LOCUTEUR_MS = 700  # changement de locuteur au théâtre
INTERTITRES_LECTURE = {"Νόμος", "Νόμοι", "Μάρτυρες", "Μαρτυρία", "Μαρτυρίαι", "Ψήφισμα", "Ὅρκος"}

JETONS = re.compile(r"\{[^}]*\}|\[\[[^\]]*\]\]|\[souffle\]|\|{1,4}|§[\w.–-]+")
MARQUES_PAUSE = ["|", "||", "|||", "||||", "[souffle]"]


def evenements(chemin):
    """Découpe une annotation en événements :
    ("texte", texte, émotion, vitesse, section), ("pause", ms), ("souffle",)."""
    emotion, vitesse, section = "neutre", "normal", ""
    lignes = [l for l in open(chemin, encoding="utf-8") if not l.lstrip().startswith("#")]
    source = " ".join(lignes)
    sortie, pos = [], 0

    def texte(fragment):
        fragment = " ".join(fragment.split())
        if fragment:
            sortie.append(("texte", fragment, emotion, vitesse, section))

    for m in JETONS.finditer(source):
        texte(source[pos:m.start()])
        pos = m.end()
        jeton = m.group()
        if jeton.startswith("§"):
            section = jeton
        elif jeton.startswith("{"):
            morceaux = [p.strip() for p in jeton[1:-1].split(",")]
            emotion = morceaux[0]
            vitesse = morceaux[1] if len(morceaux) > 1 else "normal"
            if emotion not in EMOTIONS or vitesse not in VITESSES:
                raise ValueError(f"{section} : marque inconnue {jeton}")
        elif jeton.startswith("[["):
            sortie.append(("pause", INTERTITRE_MS if jeton[2:-2] in INTERTITRES_LECTURE else LOCUTEUR_MS))
        elif jeton == "[souffle]":
            sortie.append(("souffle",))
        else:
            sortie.append(("pause", PAUSES_MS[jeton]))
    texte(source[pos:])
    return sortie


def texte_brut(chemin):
    """Le texte grec seul, sans aucune marque (pour le comparer à la source)."""
    return " ".join(e[1] for e in evenements(chemin) if e[0] == "texte")


# ---------- modèle mot à mot, utilisé par l'éditeur ----------
# Une liste d'éléments :
#   {"mot": "ἐγὼ", "section": "5", "emotion": "sincère", "vitesse": "normal", "apres": ["||"]}
#   {"intertitre": "Νόμος", "section": "29"}


def modele_depuis_annotation(texte):
    """Annotation (texte à marques) -> modèle mot à mot."""
    source = " ".join(l for l in texte.splitlines() if not l.lstrip().startswith("#"))
    emotion, vitesse, section = "neutre", "normal", ""
    elements, pos = [], 0

    def mots(fragment):
        for m in fragment.split():
            elements.append({"mot": m, "section": section, "emotion": emotion, "vitesse": vitesse, "apres": []})

    def dernier_mot():
        return next((e for e in reversed(elements) if "mot" in e), None)

    for m in JETONS.finditer(source):
        mots(source[pos:m.start()])
        pos = m.end()
        jeton = m.group()
        if jeton.startswith("§"):
            section = jeton[1:]
        elif jeton.startswith("{"):
            morceaux = [p.strip() for p in jeton[1:-1].split(",")]
            emotion = morceaux[0] if morceaux[0] in EMOTIONS else "neutre"
            vitesse = morceaux[1] if len(morceaux) > 1 and morceaux[1] in VITESSES else "normal"
        elif jeton.startswith("[["):
            elements.append({"intertitre": jeton[2:-2], "section": section})
        elif (prec := dernier_mot()) is not None:
            prec["apres"].append(jeton)
    mots(source[pos:])
    return elements


def serialiser(elements, entete=""):
    """Modèle mot à mot -> annotation (texte à marques), une ligne par section."""
    lignes = [entete.rstrip()] if entete else []
    courante, emotion, vitesse, section = [], None, None, None
    for e in elements:
        if e["section"] != section:
            if courante:
                lignes.append(" ".join(courante))
            section = e["section"]
            courante = [f"§{section}"] if section else []
        if "intertitre" in e:
            courante.append(f"[[{e['intertitre']}]]")
            continue
        if (e["emotion"], e["vitesse"]) != (emotion, vitesse):
            emotion, vitesse = e["emotion"], e["vitesse"]
            courante.append(f"{{{emotion}}}" if vitesse == "normal" else f"{{{emotion}, {vitesse}}}")
        courante.append(e["mot"])
        courante.extend(e["apres"])
    if courante:
        lignes.append(" ".join(courante))
    return "\n".join(lignes) + "\n"


# signes polytoniques inconnus du modèle : esprits, iota souscrit ; grave et circonflexe -> aigu
SUPPRIMER = {"̓", "̔", "ͅ"}
VERS_AIGU = {"̀", "͂", "́"}
# groupes vocaliques (diphtongues d'abord) pour compter les syllabes, sur texte NFD
VOYELLES = re.compile(r"(?:[αεοη]́?[υι](?!̈)|[ου]́?ι(?!̈)|[αεηιουω])́?", re.I)


def accent_unique(mot):
    """Un seul accent par mot (le premier), aucun sur les monosyllabes."""
    vu = len(VOYELLES.findall(mot)) <= 1
    sortie = []
    for c in mot:
        if c == "́":
            if vu:
                continue
            vu = True
        sortie.append(c)
    return "".join(sortie)


def monotonique(texte):
    """Polytonique -> monotonique moderne, lisible par le modèle."""
    sortie = []
    for c in unicodedata.normalize("NFD", texte):
        if c in SUPPRIMER:
            continue
        sortie.append("́" if c in VERS_AIGU else c)
    texte = re.sub(r"\w[\ẃ̈]*", lambda m: accent_unique(m.group()), "".join(sortie))
    texte = unicodedata.normalize("NFC", texte)
    texte = texte.replace("ʼ", "'").replace("’", "'").replace("·", ",")
    texte = re.sub(r"\s*[()]\s*", ", ", texte)
    return " ".join(re.sub(r",\s*,", ",", texte).split()).strip(", ")
