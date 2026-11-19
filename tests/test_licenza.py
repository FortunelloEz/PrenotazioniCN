"""Licenza: valida, scaduta, server irraggiungibile con/senza cache, risposta malformata."""
import json
from datetime import date, timedelta

import pytest

import logicaBE as L
from conftest import FakeResponse

OGGI = date.today()
FUTURO = (OGGI + timedelta(days=30)).isoformat()
PASSATO = (OGGI - timedelta(days=1)).isoformat()
IERI = (OGGI - timedelta(days=1)).isoformat()


def _cfg(cfg_dir, **kw):
    base = {"license_token": "AAAA-BBBB", "api_key_encrypted": "CHIAVE"}
    base.update(kw)
    (cfg_dir / "config.json").write_text(json.dumps(base), encoding="utf-8")


def _letto(cfg_dir):
    return json.loads((cfg_dir / "config.json").read_text(encoding="utf-8"))


def test_valida_aggiorna_cache_senza_perdere_la_chiave(cfg_dir, fake_http):
    _cfg(cfg_dir)
    chiamate = fake_http(post=FakeResponse(200, {"valid": True, "expires": FUTURO}))
    assert L.check_license() == (True, "")
    cfg = _letto(cfg_dir)
    assert cfg["license_expires"] == FUTURO and cfg["license_last_check"] == OGGI.isoformat()
    assert cfg["api_key_encrypted"] == "CHIAVE"
    assert "AAAA" not in json.dumps(chiamate[0][2]["json"])  # si invia solo l'hash


def test_cache_di_oggi_niente_rete(cfg_dir, fake_http):
    _cfg(cfg_dir, license_expires=FUTURO, license_last_check=OGGI.isoformat())
    chiamate = fake_http()
    assert L.check_license() == (True, "")
    assert chiamate == []


def test_scaduta(cfg_dir, fake_http):
    _cfg(cfg_dir)
    fake_http(post=FakeResponse(200, {"valid": True, "expires": PASSATO}))
    ok, msg = L.check_license()
    assert not ok and "scaduta" in msg


def test_scaduta_in_cache(cfg_dir, fake_http):
    _cfg(cfg_dir, license_expires=PASSATO, license_last_check=OGGI.isoformat())
    fake_http()
    ok, msg = L.check_license()
    assert not ok and "scaduta" in msg


def test_non_valida(cfg_dir, fake_http):
    _cfg(cfg_dir)
    fake_http(post=FakeResponse(200, {"valid": False}))
    assert L.check_license() == (False, "Licenza non valida.")


def test_server_irraggiungibile_con_cache_valida(cfg_dir, fake_http):
    _cfg(cfg_dir, license_expires=FUTURO, license_last_check=IERI)

    def _giu(*_a, **_k):
        raise L._requests.ConnectionError("offline")
    fake_http(post=_giu)
    assert L.check_license() == (True, "")


def test_server_irraggiungibile_senza_cache(cfg_dir, fake_http):
    _cfg(cfg_dir)

    def _giu(*_a, **_k):
        raise L._requests.ConnectionError("offline")
    fake_http(post=_giu)
    ok, msg = L.check_license()
    assert not ok and "server licenze" in msg


@pytest.mark.parametrize("risposta", [
    FakeResponse(200, [1, 2]),
    FakeResponse(200, "ok"),
    FakeResponse(200, {"valid": "false", "expires": FUTURO}),   # stringa: non è un sì
    FakeResponse(200, {"valid": 1, "expires": FUTURO}),
    FakeResponse(200, json_error=True),
    FakeResponse(500),
])
def test_risposte_malformate_non_sbloccano(cfg_dir, fake_http, risposta):
    """Regressione: una lista faceva crollare l'avvio; "valid": "false" era considerato valido."""
    _cfg(cfg_dir)
    fake_http(post=risposta)
    ok, _ = L.check_license()
    assert ok is False


def test_valida_senza_scadenza(cfg_dir, fake_http):
    _cfg(cfg_dir)
    fake_http(post=FakeResponse(200, {"valid": True}))
    ok, msg = L.check_license()
    assert not ok and "expires" in msg


def test_inserimento_token(cfg_dir, fake_http, api):
    _cfg(cfg_dir, license_token="")
    fake_http(post=FakeResponse(200, {"valid": True, "expires": FUTURO}))
    assert api.insert_license("  NUOVO-TOKEN ") == {"ok": True, "expires": FUTURO}
    cfg = _letto(cfg_dir)
    assert cfg["license_token"] == "NUOVO-TOKEN" and cfg["api_key_encrypted"] == "CHIAVE"


def test_inserimento_token_non_valido_non_scrive(cfg_dir, fake_http, api):
    _cfg(cfg_dir, license_token="VECCHIO")
    fake_http(post=FakeResponse(200, {"valid": False}))
    res = api.insert_license("SBAGLIATO")
    assert res["ok"] is False
    assert _letto(cfg_dir)["license_token"] == "VECCHIO"
