"""Activation locale explicite. Ne jamais afficher la clé générée."""

import argparse
import secrets
from pathlib import Path

parser = argparse.ArgumentParser(
    description="Configurer l'accès de développement phase 2."
)
group = parser.add_mutually_exclusive_group(required=True)
group.add_argument("--enable", action="store_true")
group.add_argument("--disable", action="store_true")
args = parser.parse_args()
env_path = Path(__file__).resolve().parents[1] / ".env"
if not env_path.exists():
    parser.error("Exécutez d'abord scripts/init_env.py.")

keys = {"DEV_API_ENABLED", "DEV_API_KEY", "DEV_ACTOR_ID"}
lines = [
    line
    for line in env_path.read_text(encoding="utf-8").splitlines()
    if line.split("=", 1)[0].strip() not in keys
]
lines.append(f"DEV_API_ENABLED={'true' if args.enable else 'false'}")
if args.enable:
    lines.extend(
        [
            f"DEV_API_KEY={secrets.token_urlsafe(32)}",
            "DEV_ACTOR_ID=30000000-0000-4000-8000-000000000001",
        ]
    )
env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("Configuration locale mise à jour. Recréez le conteneur API pour l'appliquer.")
