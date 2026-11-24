"""Tests de conteneur de l'API (phase 6), sans cloud : Docker local uniquement.

Vérifie l'image telle qu'elle serait déployée sur GCP : exécution sans privilèges et en
lecture seule, refus de démarrer en mode cloud sans CA, sonde de vie indépendante de la base,
sonde de disponibilité en échec sans base, nombre de workers configurable, absence de secrets
dans l'image.

    python scripts/test_api_container.py            # construit l'image
    python scripts/test_api_container.py --no-build # réutilise electionhub-api:test
"""

import subprocess
import sys
import time
import unittest
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMAGE = "electionhub-api:test"
RUN_ID = uuid.uuid4().hex[:8]
CONTAINERS: list[str] = []
PASSWORD = "unit-test-password-0123456789"  # valeur de test, pas un secret
# Bundle CA du système de l'image : un fichier PEM valide pour satisfaire verify-full.
CA_IN_IMAGE = "/etc/ssl/certs/ca-certificates.crt"

BASE_ENV = {
    "APP_ENV": "cloud",
    "POSTGRES_HOST": "127.0.0.1",
    "POSTGRES_PORT": "9",  # rien n'écoute : la base est volontairement injoignable
    "POSTGRES_PASSWORD": PASSWORD,
    "POSTGRES_SSLMODE": "verify-full",
    "POSTGRES_SSLROOTCERT": CA_IN_IMAGE,
    "POSTGRES_CONNECT_TIMEOUT_SECONDS": "1",
    "MOCK_SMS_DIRECTORY": "/tmp/electionhub-sms",
}


def docker(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", *args], capture_output=True, text=True, check=check, encoding="utf-8"
    )


def run_api(name: str, env: dict[str, str], detach: bool = True) -> str:
    args = ["run", "--name", name, "--read-only", "--tmpfs", "/tmp"]
    args += ["--cap-drop", "ALL", "--security-opt", "no-new-privileges"]
    if detach:
        args += ["-d", "-p", "127.0.0.1:0:8000"]
    for key, value in env.items():
        args += ["-e", f"{key}={value}"]
    CONTAINERS.append(name)
    result = docker(*args, IMAGE, check=False)
    if detach and result.returncode != 0:
        raise RuntimeError(result.stderr)
    return name


def http_get(name: str, path: str) -> int:
    port = docker("port", name, "8000/tcp").stdout.split(":")[-1].strip()
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}{path}", timeout=5
        ) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code


def wait_ready(name: str, path: str = "/openapi.json") -> None:
    for _ in range(60):
        try:
            http_get(name, path)
            return
        except OSError:
            time.sleep(0.5)
    raise RuntimeError(
        f"{name} inaccessible : {docker('logs', name, check=False).stderr}"
    )


class ApiContainerTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        for name in CONTAINERS:
            docker("rm", "-f", name, check=False)

    def test_cloud_mode_refuses_to_start_without_ca(self):
        env = {k: v for k, v in BASE_ENV.items() if k != "POSTGRES_SSLROOTCERT"}
        name = run_api(f"api-noca-{RUN_ID}", env, detach=False)
        state = docker("inspect", "-f", "{{.State.ExitCode}}", name).stdout.strip()
        logs = docker("logs", name, check=False)
        self.assertNotEqual(state, "0")
        self.assertIn("POSTGRES_SSLROOTCERT", logs.stdout + logs.stderr)
        self.assertNotIn(PASSWORD, logs.stdout + logs.stderr)  # aucun secret journalisé

    def test_cloud_mode_refuses_weaker_tls(self):
        env = {**BASE_ENV, "POSTGRES_SSLMODE": "require"}
        name = run_api(f"api-tls-{RUN_ID}", env, detach=False)
        logs = docker("logs", name, check=False)
        self.assertNotEqual(
            docker("inspect", "-f", "{{.State.ExitCode}}", name).stdout.strip(), "0"
        )
        self.assertIn("verify-full", logs.stdout + logs.stderr)

    def test_liveness_survives_database_outage_but_readiness_fails(self):
        name = run_api(f"api-live-{RUN_ID}", BASE_ENV)
        wait_ready(name)
        self.assertEqual(http_get(name, "/openapi.json"), 200)  # sonde de vie (MIG)
        self.assertEqual(http_get(name, "/health"), 503)  # sonde de disponibilité (LB)

    def test_runs_unprivileged_and_read_only(self):
        name = run_api(f"api-user-{RUN_ID}", BASE_ENV)
        wait_ready(name)
        uid = docker("exec", name, "id", "-u").stdout.strip()
        self.assertNotEqual(uid, "0")
        write = docker("exec", name, "sh", "-c", "touch /workspace/x", check=False)
        self.assertNotEqual(write.returncode, 0)  # système de fichiers en lecture seule

    def test_worker_count_is_configurable(self):
        name = run_api(f"api-workers-{RUN_ID}", {**BASE_ENV, "UVICORN_WORKERS": "2"})
        wait_ready(name)
        processes = docker("top", name).stdout
        workers = [line for line in processes.splitlines() if "spawn_main" in line]
        self.assertEqual(len(workers), 2, processes)

    def test_image_contains_no_secret_files(self):
        listing = docker(
            "run",
            "--rm",
            "--entrypoint",
            "sh",
            IMAGE,
            "-c",
            "find /workspace -name '.env*' -o -name '*.pem' -o -name '*.tfstate' -o -name '*.key'",
        ).stdout.strip()
        self.assertEqual(listing, "")


if __name__ == "__main__":
    if "--no-build" in sys.argv:
        sys.argv.remove("--no-build")
    else:
        docker(
            "build", "-t", IMAGE, "-f", str(ROOT / "backend" / "Dockerfile"), str(ROOT)
        )
    unittest.main(verbosity=2)
