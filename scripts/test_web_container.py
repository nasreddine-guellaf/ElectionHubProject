"""Tests de conteneur du frontend (phase 7), sans cloud : Docker local uniquement.

Construit l'image web, démarre un faux backend dans un réseau Docker jetable, puis vérifie
/healthz, le repli React, les en-têtes de sécurité, le proxy /api/, l'amont indisponible,
la configuration par API_UPSTREAM et l'exécution sans privilèges.

    python scripts/test_web_container.py            # construit l'image
    python scripts/test_web_container.py --no-build # réutilise electionhub-web:test
"""

import json
import subprocess
import sys
import time
import unittest
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMAGE = "electionhub-web:test"
STUB_IMAGE = "python:3.11-slim"
RUN_ID = uuid.uuid4().hex[:8]
NETWORK = f"eh-web-test-{RUN_ID}"
STUB = f"stubapi-{RUN_ID}"
CONTAINERS: list[str] = []

STUB_CODE = (
    "import json, http.server\n"
    "class H(http.server.BaseHTTPRequestHandler):\n"
    "    def do_GET(self):\n"
    "        body = json.dumps({'path': self.path, 'host': self.headers.get('Host'),\n"
    "                           'xff': self.headers.get('X-Forwarded-For')}).encode()\n"
    "        self.send_response(200)\n"
    "        self.send_header('Content-Type', 'application/json')\n"
    "        self.send_header('Content-Length', str(len(body)))\n"
    "        self.end_headers()\n"
    "        self.wfile.write(body)\n"
    "    def log_message(self, *a): pass\n"
    "http.server.HTTPServer(('0.0.0.0', 8000), H).serve_forever()\n"
)


def docker(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", *args], capture_output=True, text=True, check=check, encoding="utf-8"
    )


def start_web(name: str, env: dict[str, str] | None = None) -> str:
    """Démarre le conteneur avec les mêmes contraintes que Compose ; renvoie l'URL hôte."""
    args = [
        "run", "-d", "--name", name, "--network", NETWORK,
        "--read-only", "--tmpfs", "/tmp", "--tmpfs", "/etc/nginx/conf.d:uid=101,gid=101,mode=0755",
        "-p", "127.0.0.1:0:8080",
    ]
    for key, value in (env or {}).items():
        args += ["-e", f"{key}={value}"]
    docker(*args, IMAGE)
    CONTAINERS.append(name)
    port = docker("port", name, "8080/tcp").stdout.split(":")[-1].strip()
    url = f"http://127.0.0.1:{port}"
    for _ in range(40):
        try:
            urllib.request.urlopen(f"{url}/healthz", timeout=2).read()
            return url
        except OSError:
            time.sleep(0.5)
    raise RuntimeError(f"{name} inaccessible : {docker('logs', name, check=False).stderr}")


def get(url: str) -> tuple[int, dict[str, str], str]:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return response.status, dict(response.headers), response.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers), error.read().decode()


class WebContainerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        docker("network", "create", NETWORK)
        docker(
            # L'alias « api » reproduit le nom de service Compose utilisé par défaut.
            "run", "-d", "--name", STUB, "--network", NETWORK, "--network-alias", "api",
            STUB_IMAGE,
            "python", "-c", STUB_CODE,
        )
        CONTAINERS.append(STUB)
        time.sleep(2)
        cls.proxied = start_web(
            f"web-proxied-{RUN_ID}",
            {"API_UPSTREAM": f"http://{STUB}:8000", "API_HOST_HEADER": "api.example.test"},
        )
        cls.proxied_name = f"web-proxied-{RUN_ID}"

    @classmethod
    def tearDownClass(cls):
        for name in CONTAINERS:
            docker("rm", "-f", name, check=False)
        docker("network", "rm", NETWORK, check=False)

    def test_healthz(self):
        status, _, body = get(f"{self.proxied}/healthz")
        self.assertEqual((status, body.strip()), (200, "ok"))

    def test_react_deep_link_falls_back_to_index(self):
        status, headers, body = get(f"{self.proxied}/admin/utilisateurs")
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers.get("Content-Type", ""))
        self.assertIn('<div id="root">', body)

    def test_security_headers(self):
        _, headers, _ = get(f"{self.proxied}/")
        self.assertIn("connect-src 'self'", headers["Content-Security-Policy"])
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(headers["Referrer-Policy"], "no-referrer")
        self.assertNotRegex(headers.get("Server", ""), r"nginx/\d")

    def test_api_is_proxied_with_configured_host_header(self):
        status, _, body = get(f"{self.proxied}/api/v1/ping?x=1")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["path"], "/api/v1/ping?x=1")
        self.assertEqual(data["host"], "api.example.test")
        self.assertIsNone(data["xff"])  # X-Forwarded-For vide : jamais relayé au backend

    def test_unavailable_api_returns_json_503(self):
        name = f"web-down-{RUN_ID}"
        url = start_web(
            name, {"API_UPSTREAM": "http://127.0.0.1:9", "API_HOST_HEADER": "$host"}
        )
        status, headers, body = get(f"{url}/api/v1/anything")
        self.assertEqual(status, 503)
        self.assertIn("application/json", headers.get("Content-Type", ""))
        self.assertEqual(json.loads(body), {"detail": "API indisponible."})
        self.assertEqual(get(f"{url}/healthz")[0], 200)  # le portail reste servi

    def test_default_upstream_preserves_compose_behaviour(self):
        name = f"web-default-{RUN_ID}"
        start_web(name)
        rendered = docker("exec", name, "nginx", "-T").stdout
        self.assertIn("proxy_pass http://api:8000;", rendered)
        self.assertIn("proxy_set_header Host $host;", rendered)

    def test_nginx_variables_are_not_substituted(self):
        rendered = docker("exec", self.proxied_name, "nginx", "-T").stdout
        self.assertIn("try_files $uri $uri/ /index.html;", rendered)

    def test_runs_without_privileges(self):
        uid = docker("exec", self.proxied_name, "id", "-u").stdout.strip()
        self.assertNotEqual(uid, "0")


if __name__ == "__main__":
    if "--no-build" in sys.argv:
        sys.argv.remove("--no-build")
    else:
        docker("build", "-t", IMAGE, str(ROOT / "frontend"))
    unittest.main(verbosity=2)
