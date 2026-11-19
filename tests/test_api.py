"""Metodi della classe Api esposti al JS (WhatsApp, chiave, stato, export)."""
import base64
import json

import pytest

import main as M


@pytest.fixture
def wa(monkeypatch):
    """Simula il registro di Windows: installed=True/False."""
    stato = {"installed": True}

    class _Key:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def _open_key(_root, name):
        if name == "whatsapp" and stato["installed"]:
            return _Key()
        raise FileNotFoundError(name)

    monkeypatch.setattr(M.winreg, "OpenKey", _open_key)
    return stato


def test_whatsapp_installato_apre_uri(api, wa):
    res = api.apri_whatsapp_app("+39 333 1234567", "Ciao Mario & co.")
    assert res == {"ok": True}
    assert api._aperti == ["whatsapp://send?phone=393331234567&text=Ciao%20Mario%20%26%20co."]


def test_whatsapp_non_installato(api, wa):
    wa["installed"] = False
    assert api.apri_whatsapp_app("393331234567", "x") == {"ok": False, "reason": "not_installed"}
    assert api._aperti == []


def test_whatsapp_errore_apertura(api, wa, monkeypatch):
    def _boom(_p):
        raise OSError("negato")
    monkeypatch.setattr(M.os, "startfile", _boom)
    res = api.apri_whatsapp_app("393331234567", "x")
    assert res["ok"] is False and "negato" in res["error"]


def test_set_api_key(api, cfg_dir):
    (cfg_dir / "config.json").write_text(json.dumps({"license_token": "T"}), encoding="utf-8")
    assert api.set_api_key("   ")["ok"] is False
    res = api.set_api_key(" sk-finta ")
    assert res["ok"] is True
    cfg = json.loads((cfg_dir / "config.json").read_text(encoding="utf-8"))
    assert cfg["license_token"] == "T"
    assert base64.b64decode(cfg["api_key_encrypted"]).decode() == "sk-finta"


def test_stato_app(api, cfg_dir):
    assert api.get_stato_app()["api_key"] is False
    (cfg_dir / "config.json").write_text(json.dumps({"api_key_encrypted": "eA==", "license_token": "T",
                                                     "license_expires": "2099-01-01"}), encoding="utf-8")
    st = api.get_stato_app()
    assert st == {"api_key": True, "license_expires": "2099-01-01", "has_license": True, "config_warning": None}


def test_stato_app_segnala_config_danneggiata(api, cfg_dir):
    (cfg_dir / "config.json").write_text("{rotto", encoding="utf-8")
    assert "danneggiato" in api.get_stato_app()["config_warning"]


def test_superb_session(api, cfg_dir):
    assert api.set_superb_session("  ", "x")["ok"] is False
    assert api.set_superb_session("S", "")["ok"] is True
    assert api.get_superb_config() == {"has_session": True, "restaurant_id": ""}
    api.set_superb_session("S2", "R")
    assert api.get_superb_config() == {"has_session": True, "restaurant_id": "R"}


def test_esporta_html_non_usa_la_cartella_corrente(api, tmp_path, monkeypatch):
    """Regressione #9 (parte): prima il file finiva nella cartella corrente."""
    altrove = tmp_path / "altrove"
    altrove.mkdir()
    monkeypatch.chdir(altrove)
    msg = api.esporta_html(json.dumps([{"nome": "Mario <b>", "telefono_wa": "39333", "link_whatsapp": "https://wa.me/39333"}]))
    assert "aperto" in msg
    out = tmp_path / "prenotazioni_wa.html"
    assert out.exists() and not (altrove / "prenotazioni_wa.html").exists()
    assert "Mario &lt;b&gt;" in out.read_text(encoding="utf-8")


def test_template_info(api):
    assert api.get_template_info()["fields"] == ["nome", "giorno", "pasto", "ospiti", "persone", "orario"]
