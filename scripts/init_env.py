"""Initialise .env sans écraser de configuration existante ni afficher le secret."""

import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[1]
template = (root / ".env.example").read_text(encoding="utf-8")
try:
    with (root / ".env").open("x", encoding="utf-8") as output:
        output.write(
            template.replace(
                "replace-with-generated-local-password", secrets.token_hex(24)
            )
        )
    print("Fichier .env local créé avec un mot de passe aléatoire.")
except FileExistsError:
    print("Fichier .env existant conservé.")
