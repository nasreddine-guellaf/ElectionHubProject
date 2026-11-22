"""HTTP réel avec sessions, RBAC et révocation, sans afficher de secret."""

import json
import secrets
import socket
import sys
import threading
import time
from importlib import import_module
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import uvicorn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
Settings = import_module("app.config").Settings
create_app = import_module("app.main").create_app
credentials_path = ROOT / ".local/demo-credentials.json"
if not credentials_path.exists():
    raise SystemExit("Exécutez d'abord python -m app.bootstrap_auth depuis backend/.")
credentials = json.loads(credentials_path.read_text(encoding="utf-8"))
server = uvicorn.Server(
    uvicorn.Config(create_app(Settings()), log_level="error", proxy_headers=False)
)
listener = socket.socket()
listener.bind(("127.0.0.1", 0))
listener.listen()
base = f"http://127.0.0.1:{listener.getsockname()[1]}"
thread = threading.Thread(
    target=server.run, kwargs={"sockets": [listener]}, daemon=True
)
tokens = {}


def request(path, method="GET", body=None, role=None):
    headers = {"Content-Type": "application/json"}
    if role:
        headers["Authorization"] = "Bearer " + tokens[role]
    data = None if body is None else json.dumps(body).encode()
    try:
        with urlopen(
            Request(base + path, data=data, headers=headers, method=method), timeout=10
        ) as res:
            raw = res.read()
            return res.status, json.loads(raw) if raw else None
    except HTTPError as error:
        return error.code, json.loads(error.read())


election_id = None
try:
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert server.started, "Uvicorn ne démarre pas."
    assert request("/health")[0] == 200
    assert request("/api/v1/reports")[0] == 401
    for role in ("agent", "admin", "validator"):
        username = "demo-" + role
        status, token = request(
            "/api/v1/auth/login",
            "POST",
            {"username": username, "password": credentials[username]},
        )
        assert status == 200, (
            "Connexion refusée : vérifier comptes, mots de passe et limites d'essais."
        )
        tokens[role] = token["access_token"]
        assert request("/api/v1/auth/me", role=role)[1]["role"] == role.upper()
    assert request("/api/v1/accounts", role="agent")[0] == 403
    assert request("/api/v1/reports", role="agent")[0] == 200
    assert request("/api/v1/reports", role="validator")[0] == 200
    data = {
        "code": "DEMO-HTTP-" + secrets.token_hex(4).upper(),
        "name": "Scrutin fictif HTTP",
        "start_date": "2026-11-01",
        "end_date": "2026-11-01",
    }
    assert request("/api/v1/elections", "POST", data, "agent")[0] == 403
    status, election = request("/api/v1/elections", "POST", data, "admin")
    assert status == 201
    election_id = election["id"]
    data["name"] = "Scrutin fictif HTTP modifié"
    assert request(f"/api/v1/elections/{election_id}", "PUT", data, "admin")[0] == 200
    assert request(f"/api/v1/elections/{election_id}", "DELETE", role="admin")[0] == 204
    election_id = None
    assert request("/api/v1/auth/logout", "POST", role="agent")[0] == 204
    assert request("/api/v1/auth/me", role="agent")[0] == 401
    tokens.pop("agent")
    print("HTTP réel : login, rôles, refus d'accès, CRUD autorisé et logout vérifiés.")
finally:
    try:
        if election_id is not None and "admin" in tokens:
            request(f"/api/v1/elections/{election_id}", "DELETE", role="admin")
        for role in tokens:
            request("/api/v1/auth/logout", "POST", role=role)
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()
        if thread.is_alive():
            raise RuntimeError("Le serveur de test ne s'est pas arrêté.")
