"""
Regole dei test (vedi CLAUDE.md):
- nessuna rete: socket bloccati; OpenAI, Superb, server licenze e WhatsApp sono finti;
- mai la config vera: ogni test lavora su una copia dei file di fabbrica in una cartella temporanea.
"""
import shutil
import socket
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import logicaBE as L  # noqa: E402

FACTORY_CONFIG = ROOT / "installer_files" / "config"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def guard(*_a, **_k):
        raise OSError("Rete bloccata nei test")
    monkeypatch.setattr(socket.socket, "connect", guard)
    monkeypatch.setattr(socket, "create_connection", guard)


@pytest.fixture(autouse=True)
def cfg_dir(tmp_path, monkeypatch):
    """Cartella config temporanea con i file di fabbrica dell'installer."""
    d = tmp_path / "config"
    d.mkdir()
    for name in ("template.txt", "template_default.txt", "config.json"):
        shutil.copy2(FACTORY_CONFIG / name, d / name)
    monkeypatch.setattr(L, "BASE_DIR", tmp_path)
    monkeypatch.setattr(L, "DATA_DIR", tmp_path)
    monkeypatch.setattr(L, "_DATA_WARNING", None)
    monkeypatch.setattr(L, "CONFIG_DIR", d)
    monkeypatch.setattr(L, "CONFIG_FILE", d / "config.json")
    monkeypatch.setattr(L, "TEMPLATE_FILE", d / "template.txt")
    monkeypatch.setattr(L, "DEFAULT_TEMPLATE_FILE", d / "template_default.txt")
    monkeypatch.setattr(L, "get_base_dir", lambda: tmp_path)
    monkeypatch.setattr(L, "RUNTIME_TEMPLATE", None)
    monkeypatch.setattr(L, "_CONFIG_WARNING", None)
    monkeypatch.setattr(L, "client", None)

    def _openai_vietato(*_a, **_k):
        raise AssertionError("Un test ha provato a creare un client OpenAI vero")
    monkeypatch.setattr(L, "OpenAI", _openai_vietato)
    return d


class FakeLLM:
    """Client OpenAI finto: restituisce le risposte preparate, in ordine."""

    def __init__(self, risposte):
        # ogni risposta: stringa (finish_reason "stop") oppure (contenuto, finish_reason)
        self._coda = [r if isinstance(r, tuple) else (r, "stop") for r in risposte]
        self.chiamate = []
        self.chat = SimpleNamespace(completions=self)

    def create(self, **kwargs):
        self.chiamate.append(kwargs)
        if not self._coda:
            raise AssertionError("FakeLLM: nessuna risposta preparata per questa chiamata")
        contenuto, finish = self._coda.pop(0)
        msg = SimpleNamespace(content=contenuto)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg, finish_reason=finish)])


@pytest.fixture
def fake_llm(monkeypatch):
    def _install(*risposte):
        fake = FakeLLM(list(risposte))
        monkeypatch.setattr(L, "client", fake)
        return fake
    return _install


class FakeResponse:
    def __init__(self, status=200, json_data=None, json_error=False):
        self.status_code = status
        self._json = json_data
        self._json_error = json_error

    def json(self):
        if self._json_error:
            raise ValueError("non è JSON")
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise L._requests.HTTPError(f"HTTP {self.status_code}")


@pytest.fixture
def fake_http(monkeypatch):
    """Sostituisce requests.get/post di logicaBE. Ritorna l'elenco delle chiamate."""
    chiamate = []

    def _install(get=None, post=None):
        def _get(url, **kw):
            chiamate.append(("GET", url, kw))
            if get is None:
                raise AssertionError("GET non previsto")
            return get(url, **kw) if callable(get) else get

        def _post(url, **kw):
            chiamate.append(("POST", url, kw))
            if post is None:
                raise AssertionError("POST non previsto")
            return post(url, **kw) if callable(post) else post

        monkeypatch.setattr(L._requests, "get", _get)
        monkeypatch.setattr(L._requests, "post", _post)
        return chiamate
    return _install


@pytest.fixture
def api(monkeypatch):
    """Istanza vera di main.Api, con WhatsApp/apertura file/browser finti."""
    import main as M
    aperti = []
    monkeypatch.setattr(M.os, "startfile", lambda p: aperti.append(p), raising=False)
    monkeypatch.setattr(M.webbrowser, "open", lambda u: aperti.append(u))
    a = M.Api()
    a._aperti = aperti
    return a
