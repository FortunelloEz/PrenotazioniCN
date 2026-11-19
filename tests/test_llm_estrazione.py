"""Estrazione dal file con LLM finto: errori dichiarati, mai «0 prenotazioni» per finta."""
import json

import pytest

import logicaBE as L

TPL = "Ciao {nome}, {giorno} a {pasto} per {ospiti} {persone} alle {orario}."


@pytest.fixture(autouse=True)
def _template(monkeypatch):
    monkeypatch.setattr(L, "RUNTIME_TEMPLATE", TPL)


def _txt(tmp_path, testo="Prenotazioni sabato 21/11/2026\nRossi Mario 20:00 2 pax 3331234567\n"):
    p = tmp_path / "prenotazioni.txt"
    p.write_text(testo, encoding="utf-8")
    return p


RISPOSTA_OK = json.dumps({
    "data_servizio": "2026-11-21",
    "colonne": ["nome", "telefono", "orario", "ospiti"],
    "prenotazioni": [
        {"nome": "ROSSI MARIO", "telefono": "333 123 4567", "orario": "20:00", "ospiti": 2},
        {"nome": "bianchi anna", "telefono": "+39 347 765 4321", "orario": "12.30", "ospiti": 1},
    ],
})


def test_estrazione_completa(tmp_path, fake_llm):
    fake = fake_llm(RISPOSTA_OK)
    enriched, html_path = L.main(str(_txt(tmp_path)))
    assert len(enriched) == 2
    r0, r1 = enriched
    assert r0["nome"] == "Rossi Mario" and r0["telefono"] == "+393331234567" and r0["telefono_wa"] == "393331234567"
    assert r0["pasto"] == "cena" and r0["giorno"] == "sabato"
    assert r0["messaggio"] == "Ciao Rossi, di questo sabato a cena per 2 persone alle 20:00."
    assert r1["pasto"] == "pranzo" and "1 persona" in r1["messaggio"]
    assert r0["data_servizio_label"] == "Sabato 21 novembre"
    assert r0["_colonne"] == ["nome", "telefono", "orario", "ospiti"]
    assert fake.chiamate[0]["model"] == L.MODEL
    # l'HTML va accanto al programma (BASE_DIR), non nella cartella corrente
    assert html_path == str(tmp_path / "prenotazioni_wa.html")


def test_giorno_scelto_dal_menu_vince(tmp_path, fake_llm):
    fake_llm(RISPOSTA_OK)
    enriched, _ = L.main(str(_txt(tmp_path)), giorno_override="oggi")
    assert enriched[0]["messaggio"].startswith("Ciao Rossi, di questa sera a cena")


@pytest.mark.parametrize("risposta, frammento", [
    ("{non json", "non leggibile"),
    ("", "vuota"),
    ("   ", "vuota"),
    ("[1, 2]", "struttura inattesa"),
    ('{"prenotazioni": "nessuna"}', "formato inatteso"),
    ('{"prenotazioni": [1, 2]}', "formato inatteso"),
    (('{"prenotazioni": [{"nome": "Ro', "length"), "troncata"),
])
def test_risposte_llm_non_valide_sono_errori(tmp_path, fake_llm, risposta, frammento):
    """Regressione #4: prima JSON rotto → lista vuota, come se non ci fossero prenotazioni."""
    fake_llm(risposta)
    with pytest.raises(L.LLMError, match=frammento):
        L.main(str(_txt(tmp_path)))
    assert not (tmp_path / "prenotazioni_wa.html").exists()


def test_zero_prenotazioni_vere_restano_zero(tmp_path, fake_llm):
    fake_llm('{"data_servizio": null, "colonne": [], "prenotazioni": []}')
    enriched, _ = L.main(str(_txt(tmp_path)))
    assert enriched == []


def test_colonne_malformate_ripulite(tmp_path, fake_llm):
    fake_llm(json.dumps({"colonne": "nome", "prenotazioni": [{"nome": "A"}]}))
    enriched, _ = L.main(str(_txt(tmp_path)))
    assert enriched[0]["_colonne"] == []


def test_file_vuoto(tmp_path, fake_llm):
    fake = fake_llm()
    with pytest.raises(ValueError, match="vuoto"):
        L.main(str(_txt(tmp_path, "   \n")))
    assert fake.chiamate == []  # niente chiamata a pagamento per un file vuoto


def test_pdf_senza_testo(tmp_path, fake_llm):
    import pymupdf as fitz
    p = tmp_path / "scansione.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.save(str(p))
    doc.close()
    fake = fake_llm()
    with pytest.raises(ValueError, match="scansione"):
        L.main(str(p))
    assert fake.chiamate == []


def test_pdf_con_testo(tmp_path, fake_llm):
    import pymupdf as fitz
    p = tmp_path / "lista.pdf"
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "Rossi Mario 20:00 2")
    doc.save(str(p))
    doc.close()
    fake = fake_llm(RISPOSTA_OK)
    enriched, _ = L.main(str(p))
    assert len(enriched) == 2
    assert "Rossi Mario 20:00 2" in fake.chiamate[0]["messages"][1]["content"]


def test_csv(tmp_path, fake_llm):
    p = tmp_path / "lista.csv"
    p.write_text("Nome,Telefono,Ora\nRossi,3331234567,20:00\n", encoding="utf-8")
    fake = fake_llm(RISPOSTA_OK)
    L.main(str(p))
    assert "Rossi\t3331234567\t20:00" in fake.chiamate[0]["messages"][1]["content"]


def test_immagine_due_chiamate(tmp_path, fake_llm, monkeypatch):
    p = tmp_path / "foto.png"
    p.write_bytes(b"\x89PNG finto")
    fake = fake_llm("Rossi Mario 20:00 2", RISPOSTA_OK)
    enriched, _ = L.main(str(p))
    assert len(enriched) == 2
    assert fake.chiamate[0]["model"] == L.MODEL_VISION
    assert fake.chiamate[0]["messages"][0]["content"][0]["image_url"]["url"].startswith("data:image/png;base64,")


def test_immagine_illeggibile(tmp_path, fake_llm):
    p = tmp_path / "foto.jpg"
    p.write_bytes(b"jpg finto")
    fake_llm("")
    with pytest.raises(L.LLMError, match="nessun testo|alcun testo"):
        L.main(str(p))


def test_tiff_rifiutato_con_spiegazione(tmp_path, fake_llm):
    p = tmp_path / "foto.tiff"
    p.write_bytes(b"tiff")
    fake_llm()
    with pytest.raises(ValueError, match="PNG o JPG"):
        L.main(str(p))


def test_formato_non_supportato(tmp_path, fake_llm):
    p = tmp_path / "lista.docx"
    p.write_bytes(b"x")
    fake_llm()
    with pytest.raises(ValueError, match="non supportato"):
        L.main(str(p))


def test_chiave_api_mancante(tmp_path):
    with pytest.raises(RuntimeError, match="Nessuna API key"):
        L.main(str(_txt(tmp_path)))


def test_modelli_configurabili_da_ambiente(monkeypatch, tmp_path, fake_llm):
    """Impostazione MODEL: il modello usato è quello configurato."""
    monkeypatch.setattr(L, "MODEL", "modello-di-prova")
    fake = fake_llm(RISPOSTA_OK)
    L.main(str(_txt(tmp_path)))
    assert fake.chiamate[0]["model"] == "modello-di-prova"


def test_api_processa_file_inesistente(api, tmp_path):
    with pytest.raises(FileNotFoundError):
        api.processa_pdf(str(tmp_path / "manca.pdf"))
