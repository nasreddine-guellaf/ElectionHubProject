"""Vérification HTTP réelle, clé temporaire et serveur Uvicorn local éphémère."""

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

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
Settings = import_module("app.config").Settings
create_app = import_module("app.main").create_app

key = secrets.token_urlsafe(32)
settings = Settings(
    dev_api_enabled=True,
    dev_api_key=key,
    dev_actor_id="30000000-0000-4000-8000-000000000001",
)
app = create_app(settings)
server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
listener = socket.socket()
listener.bind(("127.0.0.1", 0))
listener.listen()
base = f"http://127.0.0.1:{listener.getsockname()[1]}"
thread = threading.Thread(
    target=server.run, kwargs={"sockets": [listener]}, daemon=True
)


def request(path, method="GET", body=None, authenticated=True):
    headers = {"Content-Type": "application/json"}
    if authenticated:
        headers["X-Development-Key"] = key
    data = None if body is None else json.dumps(body).encode()
    try:
        with urlopen(
            Request(base + path, data=data, headers=headers, method=method), timeout=5
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
    assert request("/api/v1/reports", authenticated=False)[0] == 403
    status, reports = request("/api/v1/reports")
    assert status == 200 and reports["total"] >= 2, "Exécutez le seed phase 2."
    status, revisions = request(
        f"/api/v1/reports/{reports['items'][0]['id']}/revisions"
    )
    assert status == 200 and revisions["total"] >= 1
    data = {
        "code": "DEMO-HTTP-" + secrets.token_hex(4).upper(),
        "name": "Scrutin fictif HTTP",
        "start_date": "2026-11-01",
        "end_date": "2026-11-01",
    }
    status, election = request("/api/v1/elections", "POST", data)
    assert status == 201
    election_id = election["id"]
    data["name"] = "Scrutin fictif HTTP modifié"
    assert request(f"/api/v1/elections/{election_id}", "PUT", data)[0] == 200
    assert request(f"/api/v1/elections/{election_id}")[1]["name"] == data["name"]
    assert request(f"/api/v1/elections/{election_id}", "DELETE")[0] == 204
    assert request(f"/api/v1/elections/{election_id}")[0] == 404
    election_id = None
    print("HTTP réel : santé, clé obligatoire, lecture PV et CRUD scrutin vérifiés.")
finally:
    try:
        if election_id is not None:
            request(f"/api/v1/elections/{election_id}", "DELETE")
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()
        if thread.is_alive():
            raise RuntimeError("Le serveur de test ne s'est pas arrêté.")
