#!/bin/zsh
# Double-clic : lance le lecteur grec utilisé par l'extension Chrome (laisser la fenêtre ouverte).
cd "$(dirname "$0")"
.venv-pocket/bin/python serveur_lecture.py
