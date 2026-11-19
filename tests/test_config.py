"""Configurazione: non deve mai perdere chiave, licenza o sessione Superb."""
import json
import os

import pytest

import logicaBE as L


def _scrivi(cfg_dir, contenuto: str):
    (cfg_dir / "config.json").write_text(contenuto, encoding="utf-8")


def test_update_conserva_le_altre_chiavi(cfg_dir):
    _scrivi(cfg_dir, json.dumps({"api_key_encrypted": "AAA", "license_token": "T"}))
    L.update_config({"superb_session": "S"})
    cfg = json.loads((cfg_dir / "config.json").read_text(encoding="utf-8"))
    assert cfg == {"api_key_encrypted": "AAA", "license_token": "T", "superb_session": "S"}


def test_file_danneggiato_viene_copiato_prima_di_scrivere(cfg_dir):
    """Regressione #1: prima load_config dava {} e il salvataggio cancellava tutto senza copia."""
    rotto = '{"api_key_encrypted": "AAA", "license_token": '  # salvataggio interrotto
    _scrivi(cfg_dir, rotto)
    assert L.load_config() == {}
    assert L.get_config_warning() and "danneggiato" in L.get_config_warning()
    L.update_config({"license_token": "NUOVO"})
    copie = list(cfg_dir.glob("config.danneggiato_*.json"))
    assert len(copie) == 1
    assert copie[0].read_text(encoding="utf-8") == rotto
    assert json.loads((cfg_dir / "config.json").read_text(encoding="utf-8")) == {"license_token": "NUOVO"}


def test_copia_del_danneggiato_non_si_moltiplica(cfg_dir):
    _scrivi(cfg_dir, "non json")
    L.load_config()
    L.load_config()
    assert len(list(cfg_dir.glob("config.danneggiato_*.json"))) == 1


def test_json_non_oggetto_e_trattato_come_danneggiato(cfg_dir):
    _scrivi(cfg_dir, "[1, 2]")
    assert L.load_config() == {}
    assert len(list(cfg_dir.glob("config.danneggiato_*.json"))) == 1


def test_file_illeggibile_non_viene_sovrascritto(cfg_dir, monkeypatch):
    _scrivi(cfg_dir, json.dumps({"api_key_encrypted": "AAA"}))

    def _bloccato(*_a, **_k):
        raise PermissionError("file in uso")
    monkeypatch.setattr(type(cfg_dir / "config.json"), "read_text", _bloccato)
    with pytest.raises(L.ConfigError):
        L.update_config({"license_token": "X"})
    monkeypatch.undo()
    assert json.loads((cfg_dir / "config.json").read_text(encoding="utf-8")) == {"api_key_encrypted": "AAA"}


def test_scrittura_atomica_se_fallisce_resta_il_vecchio(cfg_dir, monkeypatch):
    _scrivi(cfg_dir, json.dumps({"api_key_encrypted": "AAA"}))

    def _replace_fallito(*_a, **_k):
        raise OSError("disco pieno")
    monkeypatch.setattr(L.os, "replace", _replace_fallito)
    with pytest.raises(L.ConfigError):
        L.update_config({"license_token": "X"})
    monkeypatch.undo()
    assert json.loads((cfg_dir / "config.json").read_text(encoding="utf-8")) == {"api_key_encrypted": "AAA"}
    assert not [p for p in os.listdir(cfg_dir) if p.endswith(".tmp")], "file temporanei rimasti"


def test_config_mancante_vale_vuoto_senza_avvisi(cfg_dir):
    (cfg_dir / "config.json").unlink()
    assert L.load_config() == {}
    assert L.get_config_warning() is None
    L.update_config({"a": 1})
    assert json.loads((cfg_dir / "config.json").read_text(encoding="utf-8")) == {"a": 1}


def test_valori_null_non_fanno_crollare_le_letture(cfg_dir, api):
    _scrivi(cfg_dir, json.dumps({"license_token": None, "superb_session": None, "api_key_encrypted": None}))
    assert L.check_license() == (False, "Nessuna licenza inserita.")
    assert api.get_superb_config() == {"has_session": False, "restaurant_id": ""}
    assert L.load_api_key_new() == ""
