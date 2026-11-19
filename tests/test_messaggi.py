"""Costruzione del messaggio al cliente: nome, giorno, pasto, orario, persone."""
import json
from urllib.parse import unquote

import pytest

import logicaBE as L

TPL = "Buongiorno {nome}, prenotazione {giorno} a {pasto} per {ospiti} {persone} alle {orario}."


@pytest.fixture(autouse=True)
def _template(monkeypatch):
    monkeypatch.setattr(L, "RUNTIME_TEMPLATE", TPL)


@pytest.mark.parametrize("scelta, atteso", [
    ("lunedi", "di questo lunedì"),
    ("martedi", "di questo martedì"),
    ("mercoledi", "di questo mercoledì"),
    ("giovedi", "di questo giovedì"),
    ("venerdi", "di questo venerdì"),
    ("sabato", "di questo sabato"),
    ("domenica", "di questa domenica"),
    ("Lunedì", "di questo lunedì"),
])
def test_giorni_della_settimana_con_accento(scelta, atteso):
    """Regressione: dal menu «Giorno» arrivava «di questo lunedi» senza accento."""
    msg = L.build_message("Mario Rossi", scelta, "pranzo", 2, "12:30")
    assert atteso in msg


@pytest.mark.parametrize("data_iso, atteso", [
    ("2026-11-16", "lunedì"), ("2026-11-17", "martedì"), ("2026-11-18", "mercoledì"),
    ("2026-11-19", "giovedì"), ("2026-11-20", "venerdì"), ("2026-11-21", "sabato"),
    ("2026-11-22", "domenica"),
])
def test_frase_giorno_da_data(data_iso, atteso):
    from datetime import date
    assert L.frase_giorno(date.fromisoformat(data_iso)) == atteso


def test_oggi_cena_diventa_questa_sera():
    assert "prenotazione di questa sera a cena" in L.build_message("Mario", "oggi", "cena", 2, "20:00")


def test_oggi_pranzo():
    assert "prenotazione di oggi a pranzo" in L.build_message("Mario", "oggi", "pranzo", 2, "12:30")


def test_giorno_vuoto():
    assert "prenotazione di oggi a pranzo" in L.build_message("Mario", "", "pranzo", 2, "12:30")


def test_giorno_libero():
    assert "prenotazione a Natale a pranzo" in L.build_message("Mario", "Natale", "pranzo", 2, "12:30")


def test_aperitivo_con_articolo():
    msg = L.build_message("Mario", "sabato", "aperitivo", 2, "18:00")
    assert "per l'aperitivo" in msg and "a aperitivo" not in msg


def test_una_persona_al_singolare():
    assert "per 1 persona alle" in L.build_message("Mario", "oggi", "cena", 1, "20:00")
    assert "per 1 persona alle" in L.build_message("Mario", "oggi", "cena", "1", "20:00")


def test_zero_ospiti_resta_zero():
    """0 è un valore vero: non deve diventare «?»."""
    assert "per 0 persone" in L.build_message("Mario", "oggi", "cena", 0, "20:00")


@pytest.mark.parametrize("ospiti", [None, "", "  "])
def test_ospiti_mancanti_diventano_punto_interrogativo(ospiti):
    """Regressione: con ospiti "" il messaggio diceva «per  persone»."""
    assert "per ? persone" in L.build_message("Mario", "oggi", "cena", ospiti, "20:00")


def test_solo_primo_nome():
    assert L.build_message("Maria Grazia Bianchi", "oggi", "cena", 2, "20:00").startswith("Buongiorno Maria,")


def test_orario_e_pasto_mancanti():
    msg = L.build_message("Mario", "oggi", None, 2, None)
    assert "a ? per 2 persone alle ?" in msg


def test_graffe_vere_nel_template(monkeypatch):
    monkeypatch.setattr(L, "RUNTIME_TEMPLATE", "Ciao {nome} {{ok}}")
    assert L.build_message("Mario", "oggi", "cena", 2, "20:00") == "Ciao Mario {ok}"


# ---- recompute_records: ciò che la tabella rimanda al backend dopo una modifica ----

def test_recompute_normalizza_telefono_e_link():
    out = L.recompute_records([{"nome": "Mario", "telefono": "333 123 4567", "orario": "20:00",
                                "ospiti": 2, "giorno": "oggi"}])[0]
    assert out["telefono"] == "+393331234567"
    assert out["telefono_wa"] == "393331234567"
    assert out["link_whatsapp"].startswith("https://wa.me/393331234567?text=")
    assert unquote(out["link_whatsapp"].split("text=")[1]) == out["messaggio"]


def test_recompute_senza_telefono_niente_link():
    out = L.recompute_records([{"nome": "Mario", "telefono": "", "orario": "20:00", "ospiti": 2}])[0]
    assert out["telefono_wa"] == "" and out["link_whatsapp"] == "#"


def test_esperienza_personalizzata_vince():
    """Regressione: «Esperienza personalizzata» veniva ignorata (brunch alle 20 → cena)."""
    out = L.recompute_records([{"nome": "Mario", "telefono": "+393331234567", "orario": "20:00",
                                "ospiti": 2, "giorno": "sabato", "pasto_personalizzato": "brunch"}])[0]
    assert out["pasto"] == "brunch"
    assert "a brunch" in out["messaggio"]


def test_pasto_scelto_a_mano_nella_tabella():
    out = L.recompute_records([{"nome": "Mario", "orario": "20:00", "ospiti": 2, "pasto": "pranzo"}])[0]
    assert out["pasto"] == "pranzo"


def test_recompute_conserva_i_campi_extra():
    rec = {"nome": "Mario", "orario": "20:00", "ospiti": 2, "tavolo": "7", "_colonne": ["nome"],
           "data_servizio_label": "Sabato 21 novembre", "chatOpened": True}
    out = L.recompute_records([rec])[0]
    for k in ("tavolo", "_colonne", "data_servizio_label", "chatOpened"):
        assert out[k] == rec[k]


def test_api_ricalcola_json_rotto_non_svuota_la_tabella(api):
    """Regressione: prima restituiva [] e il frontend svuotava la tabella."""
    with pytest.raises(ValueError):
        api.ricalcola_messaggi("{rotto")
    assert api.ricalcola_messaggi(json.dumps([{"nome": "Mario", "orario": "20:00"}]))[0]["pasto"] == "cena"


# ---- _mancanti: dati che nel messaggio diventerebbero «?» (solo quelli usati dal template) ----

def test_mancanti_solo_se_il_template_li_usa(monkeypatch):
    rec = [{"nome": "Neri", "telefono": "3330000004", "orario": "10:30", "ospiti": None}]
    out = L.recompute_records(rec)[0]
    assert out["_mancanti"] == ["pasto", "ospiti"]          # TPL usa {pasto} e {ospiti}
    monkeypatch.setattr(L, "RUNTIME_TEMPLATE", "Ciao {nome}, ti aspettiamo alle {orario}.")
    assert L.recompute_records(rec)[0]["_mancanti"] == []    # il template non li usa: nessun «?»


def test_mancanti_zero_ospiti_non_manca():
    out = L.recompute_records([{"nome": "A", "orario": "20:00", "ospiti": 0}])[0]
    assert out["_mancanti"] == []


def test_mancanti_completi():
    out = L.recompute_records([{"nome": "A", "orario": "", "ospiti": 2, "pasto": "cena"}])[0]
    assert out["_mancanti"] == ["orario"]
