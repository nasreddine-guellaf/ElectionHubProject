"""Build mock-only Lambda ZIPs with the standard library from any working directory."""

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / ".local" / "build"
PACKAGES = {
    "pv": ("lambda_pv.py", "lambda_pv_demo.py"),
    "otp": ("lambda_otp.py",),
}


def main():
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    for name, modules in PACKAGES.items():
        destination = ARTIFACTS / f"account_b_{name}.zip"
        with ZipFile(destination, "w") as archive:
            for filename in ("__init__.py", *modules):
                entry = f"app/{filename}"
                info = ZipInfo(entry)
                info.external_attr = 0o644 << 16
                archive.writestr(info, (ROOT / "backend" / entry).read_bytes(), ZIP_DEFLATED)
        print(destination.relative_to(ROOT))


if __name__ == "__main__":
    main()
