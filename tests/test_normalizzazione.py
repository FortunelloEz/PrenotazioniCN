"""Telefoni, orari, pasti, nomi."""
import pytest

import logicaBE as L


@pytest.mark.parametrize("grezzo, atteso", [
    ("+39 333 123 4567", "+393331234567"),
    ("+393331234567", "+393331234567"),
    ("(+39) 333-1234567", "+393331234567"),
    ("0039 333 1234567", "+393331234567"),
    ("393331234567", "+393331234567"),
    ("333 123 4567", "+393331234567"),        # regressione #5: prima +3331234567
    ("3331234567", "+393331234567"),
    ("02 1234567", "+39021234567"),           # fisso italiano senza prefisso
    ("+33 6 12 34 56 78", "+33612345678"),    # estero col +: invariato
    ("+32 2 123 45 67", "+3221234567"),       # belga 10 cifre che inizia per 3: il + vince
    ("0041 79 123 45 67", "+41791234567"),
    ("", ""), (None, ""), ("n.d.", ""),
])
def test_normalize_phone(grezzo, atteso):
    assert L.normalize_phone(grezzo) == atteso


def test_normalize_phone_idempotente():
    for n in ("333 123 4567", "+33 6 12 34 56 78", "02 1234567"):
        once = L.normalize_phone(n)
        assert L.normalize_phone(once) == once


def test_prefisso_predefinito_configurabile(monkeypatch):
    """Impostazione DEFAULT_COUNTRY_CODE: cambia il prefisso aggiunto ai numeri senza prefisso."""
    assert L.normalize_phone("3331234567") == "+393331234567"
    monkeypatch.setattr(L, "DEFAULT_COUNTRY_CODE", "41")
    assert L.normalize_phone("3331234567") == "+413331234567"


@pytest.mark.parametrize("orario, ora", [
    ("19:30", 19), ("19.30", 19), ("19h30", 19), ("19", 19), (" 9:05 ", 9),
    ("7:30 PM", 19), ("12:00 am", 0), ("12:15 pm", 12), ("25:00", None), ("sera", None),
    ("", None), (None, None), (20, 20),
])
def test_parse_hour(orario, ora):
    assert L.parse_hour(orario) == ora


@pytest.mark.parametrize("orario, pasto", [
    ("11:00", "pranzo"), ("15:59", "pranzo"), ("16:00", "aperitivo"), ("18:30", "aperitivo"),
    ("19:00", "cena"), ("23:30", "cena"), ("19.30", "cena"),  # regressione: "19.30" non era riconosciuto
    ("10:30", None), ("00:30", None), ("", None),
])
def test_infer_pasto_da_orario(orario, pasto):
    assert L.infer_pasto(orario, None) == pasto


@pytest.mark.parametrize("dichiarato, atteso", [
    ("Lunch", "pranzo"), ("dinner", "cena"), ("Aperitif", "aperitivo"), ("CENA", "cena"),
])
def test_infer_pasto_dichiarato_vince_sull_orario(dichiarato, atteso):
    assert L.infer_pasto("12:00", dichiarato) == atteso


def test_fasce_pasti_configurabili(monkeypatch):
    """Impostazione MEAL_HOUR_RANGES: cambiando le fasce cambia il pasto riconosciuto."""
    assert L.infer_pasto("10:30", None) is None
    monkeypatch.setattr(L, "MEAL_HOUR_RANGES", (("pranzo", 10, 15), ("aperitivo", 16, 18), ("cena", 19, 23)))
    assert L.infer_pasto("10:30", None) == "pranzo"


@pytest.mark.parametrize("grezzo, atteso", [
    ("mario rossi", "Mario Rossi"), ("ROSSI M.", "Rossi M."), ("N", ""), ("PS", ""),
    ("12/05", ""), ("Bianchi -", "Bianchi"), ("", ""),
])
def test_clean_name(grezzo, atteso):
    assert L.clean_name(grezzo) == atteso


def test_nome_breve():
    assert L.nome_breve("Anna-Maria Rossi") == "Anna-Maria"
    assert L.nome_breve("D'Angelo Luca") == "D'Angelo"
    assert L.nome_breve("") == ""


def test_etichetta_data_in_italiano():
    from datetime import date
    assert L.format_data_label(date(2026, 1, 17)) == "Sabato 17 gennaio"
    assert L.format_data_label(None) is None
