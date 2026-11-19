"""
Server di verifica visiva — NON è l'app vera e non tocca nulla di vero.

- Serve assets/ su http://127.0.0.1:8765/ e inietta un finto window.pywebview.api
  che inoltra ogni chiamata alla VERA classe main.Api (POST /api/<metodo>).
- Config: copia dei file di fabbrica in una cartella temporanea (mai la config vera).
- OpenAI, Superb, server licenze, WhatsApp, apertura file e browser sono FINTI.
- Rete in uscita bloccata nel processo (solo 127.0.0.1 ammesso).
- Lo scenario si cambia con POST /__scenario {"llm": ..., "whatsapp": ..., "superb": ...}.

Avvio:  .venv\\Scripts\\python tools\\server_verifica.py [--port 8765]
"""
import argparse
import json
import shutil
import socket
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
ASSETS = ROOT / "assets"

# ── 1. rete bloccata (prima di importare qualsiasi client) ──
_orig_connect = socket.socket.connect


def _solo_locale(self, address):
    host = address[0] if isinstance(address, tuple) else address
    if host not in ("127.0.0.1", "localhost", "::1"):
        raise OSError(f"Rete esterna bloccata nella verifica: {host}")
    return _orig_connect(self, address)


socket.socket.connect = _solo_locale

import logicaBE as L  # noqa: E402
import main as M  # noqa: E402

# ── 2. config temporanea ──
TMP = Path(tempfile.mkdtemp(prefix="prenotazioni_verifica_"))
CFG = TMP / "config"
CFG.mkdir()
for name in ("template.txt", "template_default.txt"):
    shutil.copy2(ROOT / "installer_files" / "config" / name, CFG / name)
(CFG / "config.json").write_text(json.dumps({
    "api_key_encrypted": "c2stZmludGE=",          # "sk-finta"
    "license_token": "FINTO-TOKEN",
    "license_expires": "2099-12-31",
    "superb_session": "SESSIONE-FINTA",
    "superb_restaurant_id": "RIST-FINTO",
}), encoding="utf-8")
L.BASE_DIR = TMP
L.DATA_DIR = TMP
L.CONFIG_DIR = CFG
L.CONFIG_FILE = CFG / "config.json"
L.TEMPLATE_FILE = CFG / "template.txt"
L.DEFAULT_TEMPLATE_FILE = CFG / "template_default.txt"
L.get_base_dir = lambda: TMP

# ── 3. dati finti ──
FILE_PRENOTAZIONI = TMP / "prenotazioni_finte.txt"
FILE_PRENOTAZIONI.write_text("Prenotazioni sabato 21/11/2026 (dati inventati)\n", encoding="utf-8")

PRENOTAZIONI_FINTE = {
    "data_servizio": "2026-11-21",
    "colonne": ["nome", "telefono", "orario", "ospiti", "stato", "note", "<b>tavolo</b>"],
    "prenotazioni": [
        {"nome": "ROSSI MARIO", "telefono": "333 000 0001", "orario": "20:00", "ospiti": 2, "stato": "C",
         "note": "Tavolo vicino alla finestra", "<b>tavolo</b>": "7"},
        {"nome": "bianchi anna", "telefono": "+39 347 000 0002", "orario": "12.30", "ospiti": 1, "stato": "N"},
        {"nome": "Verdi Luca", "orario": "19:30", "ospiti": 4, "stato": "C", "allergie": "Noci"},
        {"nome": "Neri Giulia", "telefono": "0039 320 000 0004", "orario": "10:30", "ospiti": 0, "stato": "PS"},
        {"nome": "Gallo Paolo Maria", "telefono": "+33 6 00 00 00 05", "orario": "18:00", "ospiti": 3,
         "stato": "<img src=x onerror=alert(1)>"},
    ],
}

SCENARIO = {"llm": "ok", "whatsapp": "ok", "superb": "ok"}
REGISTRO = {"whatsapp": [], "browser": [], "file": []}
_lock = threading.Lock()


class FakeLLM:
    def __init__(self):
        self.chat = SimpleNamespace(completions=self)

    def create(self, **_kw):
        mode = SCENARIO["llm"]
        if mode == "errore_rete":
            raise RuntimeError("APIConnectionError: Connection error.")
        content, finish = {
            "ok": (json.dumps(PRENOTAZIONI_FINTE), "stop"),
            "vuoto": ('{"data_servizio": null, "colonne": [], "prenotazioni": []}', "stop"),
            "json_rotto": ('{"prenotazioni": [{"nome": ', "stop"),
            "troncato": ('{"prenotazioni": [{"nome": "Ro', "length"),
        }[mode]
        msg = SimpleNamespace(content=content)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg, finish_reason=finish)])


L.client = FakeLLM()
L.reset_client = lambda: None   # la "nuova chiave" non deve creare un client vero


def _superb_get(url, **_kw):
    mode = SCENARIO["superb"]
    if mode == "scaduta":
        return SimpleNamespace(status_code=401, json=lambda: {})
    if mode == "offline":
        raise L._requests.ConnectionError("offline")
    data = [{"_id": f"s{i}", "arrival": f"2026-11-21T{h}:00:00.000Z", "guests": g,
             "subStatuses": ["C"], "user": {"name": {"full": n}, "mobile": t}}
            for i, (n, t, h, g) in enumerate([
                ("Superb Uno", "+393330000011", "11", 2),
                ("Superb Due", "3330000012", "18", 5)])]
    return SimpleNamespace(status_code=200, json=lambda: {"success": True, "data": data})


def _http_vietato(*_a, **_k):
    raise AssertionError("HTTP POST non previsto nella verifica")


L._requests.get = _superb_get
L._requests.post = _http_vietato


class _RegKey:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


_wa_count = {"n": 0}


def _open_key(_root, name):
    if SCENARIO["whatsapp"] == "not_installed":
        raise FileNotFoundError(name)
    return _RegKey()


def _startfile(target):
    target = str(target)
    if target.startswith("whatsapp://"):
        _wa_count["n"] += 1
        if SCENARIO["whatsapp"] == "fail_some" and _wa_count["n"] % 2 == 0:
            raise OSError("apertura WhatsApp fallita (simulata)")
        REGISTRO["whatsapp"].append(target)
    else:
        REGISTRO["file"].append(target)


# winreg finto SOLO per main.py: il modulo vero serve a pywebview
M.winreg = SimpleNamespace(OpenKey=_open_key, HKEY_CLASSES_ROOT=M.winreg.HKEY_CLASSES_ROOT)
M.os.startfile = _startfile
M.webbrowser.open = lambda u: REGISTRO["browser"].append(u)

API = M.Api()
API.scegli_file = lambda: str(FILE_PRENOTAZIONI)
API.chiudi_finestra = lambda: {"ok": True}

SHIM = """<script>
(() => {
  const call = async (name, args) => {
    const r = await fetch('/api/' + name, {method: 'POST', body: JSON.stringify(args)});
    const j = await r.json();
    if (!j.ok) { const e = new Error(j.error); e.name = j.type || 'Error'; throw e; }
    return j.result;
  };
  const api = new Proxy({}, {get: (_t, name) => (...args) => call(name, args)});
  window.pywebview = {api};
  // window.open finto: niente navigazione verso wa.me
  window.__opened = [];
  window.open = (url) => { window.__opened.push(url); return {closed: false}; };
  document.addEventListener('DOMContentLoaded', () =>
    setTimeout(() => window.dispatchEvent(new Event('pywebviewready')), 50));
})();
</script>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_a):
        pass

    def _send(self, code, body: bytes, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0].lstrip("/") or "index.html"
        if path == "favicon.ico":
            return self._send(204, b"", "image/x-icon")
        if path == "__registro":
            return self._send(200, json.dumps(REGISTRO).encode(), "application/json")
        f = (ASSETS / path).resolve()
        if ASSETS not in f.parents or not f.is_file():
            return self._send(404, b"not found", "text/plain")
        data = f.read_bytes()
        if f.suffix == ".html":
            data = data.decode("utf-8").replace("<head>", "<head>" + SHIM, 1).encode("utf-8")
        ctype = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
                 ".css": "text/css; charset=utf-8"}.get(f.suffix, "application/octet-stream")
        self._send(200, data, ctype)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"null")
        if self.path == "/__scenario":
            SCENARIO.update(body or {})
            _wa_count["n"] = 0
            if (body or {}).get("reset_registro"):
                for v in REGISTRO.values():
                    v.clear()
            return self._send(200, json.dumps(SCENARIO).encode(), "application/json")
        if not self.path.startswith("/api/"):
            return self._send(404, b"{}", "application/json")
        name = self.path[len("/api/"):]
        fn = getattr(API, name, None)
        if fn is None or name.startswith("_"):
            out = {"ok": False, "error": f"Metodo API inesistente: {name}", "type": "AttributeError"}
            return self._send(200, json.dumps(out).encode(), "application/json")
        try:
            with _lock:
                res = fn(*(body or []))
            out = {"ok": True, "result": res}
        except Exception as e:  # come pywebview: l'eccezione diventa un errore JS
            out = {"ok": False, "error": str(e), "type": type(e).__name__}
        self._send(200, json.dumps(out, default=str).encode(), "application/json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args()
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    print(f"Server verifica su http://127.0.0.1:{a.port}/  (config temporanea: {TMP})", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
