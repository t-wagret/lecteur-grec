# Voix de référence

`homme2.wav` est un enregistrement de lecture en grec moderne (locuteur masculin) tiré du jeu
de données **FLEURS** de Google (`google/fleurs`, configuration `el_gr`, partie `dev`,
fichier `3410933003310671562.wav`), distribué sous licence
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).

`homme2_propre.wav` en est une version rééchantillonnée à 24 kHz et débruitée
(script `nettoyage.py`, fonction `debruiter`).

Attribution à reprendre dans toute publication des audios produits :
« Voix de référence : Google FLEURS (CC BY 4.0) ».

Conneau et al., *FLEURS: Few-shot Learning Evaluation of Universal Representations of Speech*, 2022.

## Voix CC0 (`cc0/`)

`athina.wav`, `katerina.wav`, `spyros.wav` et `kostas.wav` sont les voix de référence de
[Pocket TTS Greek](https://huggingface.co/myned-ai/pocket-tts-greek) (Myned AI), assemblées par
l'auteur du modèle à partir d'enregistrements Mozilla Common Voice 27.0 en grec (**CC0**) ;
le détail des enregistrements sources est dans `cc0/voices.md`. Merci de ne pas chercher à
identifier les contributeurs. Le modèle Pocket TTS Greek lui-même est sous **CC BY 4.0** :
toute publication d'audios produits avec lui doit mentionner
« Pocket TTS Greek, Myned AI (CC BY 4.0) ».

`propre/spyros.wav` et `propre/kostas.wav` sont des versions débruitées des voix CC0 du même nom
(script `nettoyage.py`, fonction `debruiter`) ; `lire_discours.py` les préfère quand elles existent.
