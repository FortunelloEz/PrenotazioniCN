"""Cartella dati in %APPDATA%, migrazione verificata, chiave con DPAPI, guardia alla chiusura."""
import base64
import json
import sys

import pytest

import logicaBE as L
import main as M

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="DPAPI solo su Windows")

CHIAVE_FINTA = "sk-finta-0123456789"


# ---------------- DPAPI ----------------

def test_dpapi_andata_e_ritorno():
    cifrata = L.protect_api_key(CHIAVE_FINTA)
    assert CHIAVE_FINTA not in cifrata
    assert base64.b64encode(CHIAVE_FINTA.encode()).decode() not in cifrata
    assert L.unprotect_api_key(cifrata) == CHIAVE_FINTA


def test_dpapi_valore_manomesso_non_si_decifra():
    cifrata = bytearray(base64.b64decode(L.protect_api_key(CHIAVE_FINTA)))
    cifrata[-5] ^= 0xFF
    with pytest.raises(OSError):
        L.unprotect_api_key(base64.b64encode(bytes(cifrata)).decode())


def _cfg(cfg_dir, d):
    (cfg_dir / "config.json").write_text(json.dumps(d), encoding="utf-8")


def _letto(cfg_dir):
    return json.loads((cfg_dir / "config.json").read_text(encoding="utf-8"))


def test_migrazione_chiave_base64_verso_dpapi(cfg_dir):
    vecchia = base64.b64encode(CHIAVE_FINTA.encode()).decode()
    _cfg(cfg_dir, {"api_key_encrypted": vecchia, "license_token": "T", "superb_session": "S"})
    assert L.migrate_api_key() is True
    cfg = _letto(cfg_dir)
    assert "api_key_encrypted" not in cfg and cfg["api_key_dpapi"]
    assert cfg["license_token"] == "T" and cfg["superb_session"] == "S"   # nient'altro perso
    assert L.load_api_key_new() == CHIAVE_FINTA
    assert L.migrate_api_key() is False   # seconda volta: niente da fare


def test_migrazione_chiave_fallita_non_perde_la_vecchia(cfg_dir, monkeypatch):
    vecchia = base64.b64encode(CHIAVE_FINTA.encode()).decode()
    _cfg(cfg_dir, {"api_key_encrypted": vecchia})

    def _rotta(_k):
        raise OSError("DPAPI non disponibile")
    monkeypatch.setattr(L, "protect_api_key", _rotta)
    assert L.migrate_api_key() is False
    assert _letto(cfg_dir) == {"api_key_encrypted": vecchia}
    assert L.load_api_key_new() == CHIAVE_FINTA


def test_migrazione_chiave_con_verifica_sbagliata_non_scrive(cfg_dir, monkeypatch):
    vecchia = base64.b64encode(CHIAVE_FINTA.encode()).decode()
    _cfg(cfg_dir, {"api_key_encrypted": vecchia})
    monkeypatch.setattr(L, "unprotect_api_key", lambda _v: "diversa")
    assert L.migrate_api_key() is False
    assert _letto(cfg_dir) == {"api_key_encrypted": vecchia}


def test_chiave_di_altro_utente_avvisa(cfg_dir):
    _cfg(cfg_dir, {"api_key_dpapi": base64.b64encode(b"non-dpapi").decode()})
    assert L.load_api_key_new() == ""
    assert "Reinseriscila" in L.get_config_warning()


def test_nuova_chiave_rimuove_la_vecchia(api, cfg_dir):
    _cfg(cfg_dir, {"api_key_encrypted": base64.b64encode(b"vecchia").decode()})
    assert api.set_api_key(CHIAVE_FINTA)["ok"]
    cfg = _letto(cfg_dir)
    assert set(cfg) == {"api_key_dpapi"}
    assert api.get_stato_app()["api_key_cifrata"] is True


# ---------------- cartella dati ----------------

def _vecchia_config(base):
    d = base / "programma" / "config"
    d.mkdir(parents=True)
    (d / "config.json").write_text('{"license_token": "T"}', encoding="utf-8")
    (d / "template.txt").write_text("Ciao {nome}", encoding="utf-8")
    (d / "template_20260101_000000.bak.txt").write_text("vecchio {nome}", encoding="utf-8")
    return d


def test_migrazione_cartella_dati(tmp_path):
    vecchia = _vecchia_config(tmp_path)
    dati = tmp_path / "AppData" / "PrenotazioniCN"
    out = L.prepare_data_dir(dati, vecchia)
    assert out == dati and L.CONFIG_FILE == dati / "config" / "config.json"
    for f in ("config.json", "template.txt", "template_20260101_000000.bak.txt"):
        assert (dati / "config" / f).read_bytes() == (vecchia / f).read_bytes()
        assert (vecchia / f).exists()                       # l'originale resta
    assert "NON è stata cancellata" in (dati / "MIGRAZIONE.txt").read_text(encoding="utf-8")
    assert L.load_config() == {"license_token": "T"}
    assert L.get_data_warning() is None


def test_migrazione_non_sovrascrive_dati_esistenti(tmp_path):
    vecchia = _vecchia_config(tmp_path)
    dati = tmp_path / "AppData" / "PrenotazioniCN"
    (dati / "config").mkdir(parents=True)
    (dati / "config" / "config.json").write_text('{"license_token": "NUOVO"}', encoding="utf-8")
    L.prepare_data_dir(dati, vecchia)
    assert L.load_config() == {"license_token": "NUOVO"}
    assert not (dati / "MIGRAZIONE.txt").exists()


def test_migrazione_fallita_usa_la_vecchia_cartella(tmp_path, monkeypatch):
    vecchia = _vecchia_config(tmp_path)
    dati = tmp_path / "AppData" / "PrenotazioniCN"

    def _disco_pieno(*_a, **_k):
        raise OSError("disco pieno")
    monkeypatch.setattr(L.shutil, "copytree", _disco_pieno)
    out = L.prepare_data_dir(dati, vecchia)
    assert out == vecchia.parent
    assert L.CONFIG_FILE == vecchia / "config.json"
    assert L.load_config() == {"license_token": "T"}
    assert "nessun dato è stato perso" in L.get_data_warning()
    assert not (dati / "config").exists()


def test_installazione_nuova_senza_vecchia_config(tmp_path):
    dati = tmp_path / "AppData" / "PrenotazioniCN"
    L.prepare_data_dir(dati, tmp_path / "manca")
    assert (dati / "config").is_dir()
    assert L.load_config() == {}


def test_template_di_fabbrica_dalla_cartella_programma(tmp_path, monkeypatch):
    prog = tmp_path / "programma"
    (prog / "config").mkdir(parents=True)
    (prog / "config" / "template_default.txt").write_text("Fabbrica {nome}", encoding="utf-8")
    monkeypatch.setattr(L, "BASE_DIR", prog)
    dati = tmp_path / "dati"
    (dati / "config").mkdir(parents=True)
    L.use_data_dir(dati)
    L.reset_template_to_default()
    assert (dati / "config" / "template.txt").read_text(encoding="utf-8") == "Fabbrica {nome}"


def test_cartella_dati_predefinita(monkeypatch, tmp_path):
    monkeypatch.setattr(L.sys, "frozen", True, raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.delenv("PRENOTAZIONICN_DATA_DIR", raising=False)
    assert L.default_data_dir() == tmp_path / "PrenotazioniCN"
    monkeypatch.setenv("PRENOTAZIONICN_DATA_DIR", str(tmp_path / "altro"))
    assert L.default_data_dir() == tmp_path / "altro"
    monkeypatch.delenv("PRENOTAZIONICN_DATA_DIR")
    monkeypatch.setattr(L.sys, "frozen", False, raising=False)
    assert L.default_data_dir() == L.BASE_DIR   # in sviluppo: come sempre


# ---------------- chiusura ----------------

class _FintaFinestra:
    def __init__(self):
        self.js = []
        self.distrutta = False

    def run_js(self, s):
        self.js.append(s)

    def destroy(self):
        self.distrutta = True


def _api_con_finestra():
    a = M.Api()
    a._window = _FintaFinestra()
    return a


def _attendi(cond):
    import time
    for _ in range(100):
        if cond():
            return True
        time.sleep(0.01)
    return False


def test_chiusura_senza_modifiche_passa():
    a = _api_con_finestra()
    assert a._on_closing() is None


def test_chiusura_con_modifiche_chiede_conferma():
    a = _api_con_finestra()
    a.set_modifiche_in_sospeso(True)
    assert a._on_closing() is False
    assert _attendi(lambda: a._window.js)
    assert "chiediConfermaChiusura" in a._window.js[0]


def test_conferma_chiude():
    a = _api_con_finestra()
    a.set_modifiche_in_sospeso(True)
    a._on_closing()
    a.ack_chiusura()
    a.conferma_chiusura()
    assert _attendi(lambda: a._window.distrutta)
    assert a._on_closing() is None   # il destroy passa dal gestore: non deve bloccarlo


def test_annulla_resta_aperta():
    a = _api_con_finestra()
    a.set_modifiche_in_sospeso(True)
    a._on_closing()
    a.ack_chiusura()
    a.annulla_chiusura()
    assert a._on_closing() is False


def test_valvola_di_sicurezza_se_il_js_non_risponde(monkeypatch):
    a = _api_con_finestra()
    a.set_modifiche_in_sospeso(True)
    t = [1000.0]
    monkeypatch.setattr(M.time, "monotonic", lambda: t[0])
    assert a._on_closing() is False          # primo tentativo: chiede
    t[0] += 0.5
    assert a._on_closing() is False          # troppo presto: chiede ancora
    t[0] += M.CLOSE_ACK_TIMEOUT_S + 1
    assert a._on_closing() is None           # nessuna risposta dal JS: si chiude


def test_nessuna_valvola_se_la_conferma_e_visibile(monkeypatch):
    a = _api_con_finestra()
    a.set_modifiche_in_sospeso(True)
    t = [1000.0]
    monkeypatch.setattr(M.time, "monotonic", lambda: t[0])
    a._on_closing()
    a.ack_chiusura()
    t[0] += 60
    assert a._on_closing() is False          # la finestra di conferma è aperta: decide l'utente
