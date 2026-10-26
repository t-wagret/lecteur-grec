# Lecteur grec

Lecture à voix haute **expressive** de textes grecs anciens, avec une voix de synthèse.

Les textes viennent de [The Greek Library](https://thegreeklibrary.pages.lisn.upsaclay.fr/). Chacun reçoit une **annotation émotionnelle** : des émotions, des vitesses, des pauses et des respirations. Une voix de synthèse ([Chatterbox Multilingual](https://huggingface.co/ResembleAI/chatterbox), de Resemble AI) lit ensuite le texte en respectant ces marques.

Le projet comprend :
- un **éditeur** dans le navigateur. On y choisit une œuvre, Claude propose une annotation, on la corrige en quelques clics, puis on l'écoute ;
- un **lecteur** en ligne de commande, qui transforme une annotation en fichier audio ;
- une **annotation complète de Lysias 1**, *Sur le meurtre d'Ératosthène*, faite à la main.

> ⚠️ **Prononciation moderne.** Le modèle ne connaît que le grec **moderne**. Avant la lecture, le texte polytonique est converti en monotonique : les esprits et le iota souscrit disparaissent, et chaque mot garde un seul accent. Le grec ancien est donc lu **avec la prononciation moderne**, ni restituée ni érasmienne.

## Installation

Il faut Python 3.11, de préférence [uv](https://docs.astral.sh/uv/), et une copie locale de The Greek Library : `catalog.json.gz` et le dossier `works/`.

```bash
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -r requirements.txt
export TGL_RAW=/chemin/vers/the-greek-library/raw   # dossier contenant catalog.json.gz et works/
```

Le modèle Chatterbox (environ 3 Go) se télécharge tout seul au premier usage.

## L'éditeur

```bash
.venv/bin/python editeur.py      # puis ouvrir http://localhost:8765
```

1. **Chercher** une œuvre, par exemple « lysias eratosth », « homer ilias » ou « sophocles aiax ».
2. **Sélectionner** des mots à la souris, puis choisir une **émotion** (21 couleurs), une **vitesse** ou une **pause** après la sélection.
   - Raccourcis : `1`–`5` pour les pauses, `⌫` pour les effacer, `⌘Z` pour annuler, `⌘S` pour enregistrer.
   - À l'écran, un passage lent a des lettres espacées, un passage vif ou rapide est en italique.
3. **✦ Suggérer avec Claude** : annote la sélection, ou la page si rien n'est sélectionné.
4. **▶ Écouter** : génère l'audio de la sélection, téléchargeable en m4a ou en wav.

Les suggestions passent par le programme [`claude`](https://docs.claude.com/en/docs/claude-code) avec ton compte Claude. Connecte-le une fois avec `claude auth login`, puis colle dans le terminal le code affiché par le navigateur.

**Le texte grec n'est jamais modifié.** Claude ne renvoie que des numéros de mots. À chaque enregistrement, le serveur compare le texte à la source et refuse le moindre écart. Les annotations sont enregistrées dans `annotations/oeuvres/<identifiant TGL>.txt`.

## Le lecteur en ligne de commande

```bash
.venv/bin/python lire_discours.py annotations/lysias1.txt -o lysias1.wav
.venv/bin/python lire_discours.py annotations/lysias1.txt -o extrait.wav --de 23 --a 26
.venv/bin/python verifier.py annotations/lysias1.txt textes/lysias1.txt   # texte intact ? marques valides ?
```

Le lecteur traite chaque morceau de texte dans l'ordre suivant :
- il **génère** le morceau avec les réglages de son émotion (`exaggeration`, `cfg_weight` de Chatterbox) ;
- il le **nettoie** : filtres doux, silences propres, trous parasites raccourcis ;
- il **ajuste la vitesse** sans changer la hauteur de la voix (WSOLA) ;
- il le **contrôle**, et le **régénère** si sa durée est anormale (bafouillage, troncature, trou).

Les morceaux trop courts sont d'abord réunis à leurs voisins, car le modèle les rate souvent.

## Format d'annotation

Le texte grec est recopié tel quel, avec des marques placées entre les mots :

| Marque | Effet |
|---|---|
| `{indigné}`, `{triste, lent}` | change l'émotion (et la vitesse) à partir de là |
| `\|` `\|\|` `\|\|\|` | micro-pause, pause, longue pause |
| `\|\|\|\|` | silence dramatique, à réserver aux moments forts |
| `[souffle]` | temps de respiration |
| `[[Νόμος]]` | intertitre non lu : loi lue par le greffier (2 s), ou nom du locuteur au théâtre |
| `§12` | repère de section |

- Émotions : neutre, narratif, calme, solennel, sincère, persuasif, tendre, nostalgique, triste, troublé, inquiet, joueur, ironique, méprisant, ferme, amer, indigné, colère, menaçant, suppliant, triomphant.
- Vitesses : lent, posé, normal, vif, rapide.

Exemple, tiré de Lysias 1, §11–12 :

```
||||
{amer, lent} ὁ γὰρ ἄνθρωπος | ἔνδον ἦν· ||
§12 {amer, posé} ὕστερον γὰρ ἅπαντα ἐπυθόμην. |||
```

## Vitesse de calcul

Sur un MacBook Air M5, le moteur PyTorch demande environ **8 secondes de calcul par seconde lue**, régénérations comprises. Il faut donc compter à peu près 2 h pour les 18 minutes de Lysias 1.

Le moteur **MLX** (puces Apple) est environ 8 fois plus rapide. Mais dans sa version 8 bits, il rate beaucoup plus souvent les morceaux courts. Il reste donc **facultatif**, dans un environnement à part :

```bash
uv venv --python 3.11 .venv-mlx
uv pip install --python .venv-mlx/bin/python -r requirements-mlx.txt
.venv-mlx/bin/python lire_discours.py annotations/lysias1.txt -o rapide.wav --moteur mlx
LECTEUR_MOTEUR=mlx .venv/bin/python editeur.py      # l'éditeur avec MLX
```

Le modèle MLX se choisit avec `LECTEUR_MODELE_MLX` (par défaut `mlx-community/chatterbox-8bit`).

## Fichiers

| Fichier | Rôle |
|---|---|
| `annotation.py` | format d'annotation, conversion polytonique → monotonique |
| `lire_discours.py` | lecteur : génération, contrôle, régénération, assemblage |
| `moteurs.py` | moteurs Chatterbox PyTorch et MLX |
| `nettoyage.py` | filtres, silences, trous parasites |
| `editeur.py`, `static/editeur.html` | éditeur web |
| `suggestions.py` | suggestions d'annotation par Claude |
| `tgl.py` | lecture du catalogue et des œuvres de The Greek Library |
| `verifier.py` | contrôle d'une annotation par rapport au texte source |
| `parler_grec.py` | lecture rapide d'une phrase grecque |
| `classer_voix.py`, `banc_rates.py` | choix de la voix de référence, mesure des ratés |

## Licences et crédits

- **Code** : MIT (voir `LICENSE`).
- **Textes et annotations** : The Greek Library / Perseus Digital Library, CC BY-SA 4.0 (voir `textes/LICENCE.md` et `annotations/LICENCE.md`).
- **Voix de référence** : Google FLEURS, CC BY 4.0 (voir `voix/LICENCE.md`). Toute publication des audios doit mentionner : « Voix de référence : Google FLEURS (CC BY 4.0) ».
- **Modèle de synthèse** : [Chatterbox](https://github.com/resemble-ai/chatterbox) de Resemble AI (MIT). Chaque audio produit contient un filigrane inaudible (PerthNet), qui signale une voix de synthèse.
