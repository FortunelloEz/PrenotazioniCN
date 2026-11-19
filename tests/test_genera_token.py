"""genera_token: i token generati prima non si perdono più."""
import json

import pytest

import genera_token as G


def test_aggiunge_senza_perdere(tmp_path):
    f = tmp_path / "tokens_generati.json"
    f.write_text(json.dumps([{"token": "VECCHIO", "hash": "h", "expires": "2026-01-01"}]), encoding="utf-8")
    raw, h, exp = G.genera(10)
    totale = G.salva_aggiungendo([{"token": raw, "hash": h, "expires": exp}], f)
    assert totale == 2
    dati = json.loads(f.read_text(encoding="utf-8"))
    assert dati[0]["token"] == "VECCHIO" and dati[1]["token"] == raw
    assert len(list(tmp_path.glob("tokens_generati.backup_*.json"))) == 1


def test_file_nuovo(tmp_path):
    f = tmp_path / "tokens_generati.json"
    assert G.salva_aggiungendo([{"token": "A"}], f) == 1


def test_file_rotto_non_viene_toccato(tmp_path):
    f = tmp_path / "tokens_generati.json"
    f.write_text("{rotto", encoding="utf-8")
    with pytest.raises(ValueError):
        G.salva_aggiungendo([{"token": "A"}], f)
    assert f.read_text(encoding="utf-8") == "{rotto"


def test_formato_token():
    raw, h, exp = G.genera(30)
    parti = raw.split("-")
    assert len(parti) == 4 and all(len(p) == 6 for p in parti)
    import hashlib
    assert h == hashlib.sha256(raw.encode()).hexdigest()
