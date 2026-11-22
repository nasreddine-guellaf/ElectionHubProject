"""Active explicitement le simulateur SMS local ; ne révèle aucun secret."""

import argparse
import secrets
from pathlib import Path

parser = argparse.ArgumentParser(description="Configurer la simulation OTP locale.")
group = parser.add_mutually_exclusive_group(required=True)
group.add_argument("--enable", action="store_true")
group.add_argument("--disable", action="store_true")
args = parser.parse_args()
env_path = Path(__file__).resolve().parents[1] / ".env"
if not env_path.exists():
    parser.error("Exécutez d'abord scripts/init_env.py.")
keys = {
    "CITIZEN_OTP_ENABLED",
    "OTP_HMAC_KEY",
    "DEV_API_ENABLED",
    "DEV_API_KEY",
    "DEV_ACTOR_ID",
}
lines = [
    line
    for line in env_path.read_text(encoding="utf-8").splitlines()
    if line.split("=", 1)[0].strip() not in keys
]
lines.append(f"CITIZEN_OTP_ENABLED={'true' if args.enable else 'false'}")
if args.enable:
    lines.append(f"OTP_HMAC_KEY={secrets.token_urlsafe(32)}")
env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("Simulation OTP configurée. Recréez l'API pour appliquer ce changement.")
