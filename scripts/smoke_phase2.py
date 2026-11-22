"""Compatibilité de commande : utilise désormais les sessions de phase 3."""

import runpy
from pathlib import Path

if __name__ == "__main__":
    runpy.run_path(
        str(Path(__file__).with_name("smoke_phase3.py")), run_name="__main__"
    )
