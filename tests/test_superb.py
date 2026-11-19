"""Superb: orari (ora legale/solare), errori comprensibili, nessuna rete vera."""
import json

import pytest

import logicaBE as L
from conftest import FakeResponse


@pytest.fixture(autouse=True)
def _setup(cfg_dir, monkeypatch):
    monkeypatch.setattr(L, "RUNTIME_TEMPLATE", "Ciao {nome}, {giorno} a {pasto} per {ospiti} {persone} alle {orario}.")
    (cfg_dir / "config.json").write_text(
        json.dumps({"superb_session": "SESSIONE-FINTA", "superb_restaurant_id": "RIST-FINTO"}), encoding="utf-8")


@pytest.mark.parametrize("arrival, atteso", [
    ("2026-07-18T18:30:00.000Z", "20:30"),   # ora legale: UTC+2
    ("2026-01-17T19:30:00.000Z", "20:30"),   # ora solare: UTC+1
    ("2026-03-29T00:30:00.000Z", "01:30"),   # giorno del cambio, prima delle 02:00 UTC+1
    ("2026-03-29T01:30:00.000Z", "03:30"),   # dopo il cambio: UTC+2
    ("2026-10-25T00:30:00.000Z", "02:30"),   # ritorno all'ora solare
    ("2026-01-17T23:30:00.000Z", "00:30"),   # a cavallo della mezzanotte
    ("", ""),
])
def test_arrival_to_orario(arrival, atteso):
    assert L._arrival_to_orario(arrival) == atteso


def _booking(nome="Mario Rossi", mobile="+393331234567", arrival="2026-07-18T18:30:00.000Z", guests=2, sub=("C",)):
    return {"_id": "id1", "arrival": arrival, "guests": guests, "subStatuses": list(sub),
            "user": {"name": {"full": nome}, "mobile": mobile}, "notes": "Allergia noci"}


def test_scarico_ok(fake_http):
    dati = [_booking(), _booking(nome="Anna Bianchi", guests=1, mobile="3477654321")]
    chiamate = fake_http(get=FakeResponse(200, {"success": True, "data": dati}))
    out, html_path = L.main_superb("2026-07-18")
    assert len(out) == 2
    a, b = out
    assert a["orario"] == "20:30" and a["pasto"] == "cena" and a["stato"] == "C" and a["note"] == "Allergia noci"
    assert a["giorno"] == "sabato" and a["data_servizio_label"] == "Sabato 18 luglio"
    assert a["messaggio"] == "Ciao Mario, di questo sabato a cena per 2 persone alle 20:30."
    assert b["telefono_wa"] == "393477654321" and "1 persona" in b["messaggio"]
    # finestra richiesta (comportamento attuale documentato: 02:00 UTC → 02:00 UTC del giorno dopo)
    q = json.loads(chiamate[0][2]["params"]["q"])
    assert q["startDate"] == "2026-07-18T02:00:00.000Z" and q["endDate"] == "2026-07-19T02:00:00.000Z"
    assert chiamate[0][2]["cookies"] == {"koa:sess": "SESSIONE-FINTA"}


@pytest.mark.parametrize("status", [401, 403])
def test_sessione_scaduta(fake_http, status):
    fake_http(get=FakeResponse(status))
    with pytest.raises(L.SuperbError, match="scaduta"):
        L.main_superb("2026-07-18")


def test_errore_server(fake_http):
    fake_http(get=FakeResponse(500))
    with pytest.raises(L.SuperbError, match="codice 500"):
        L.main_superb("2026-07-18")


def test_rete_assente(fake_http):
    def _giu(*_a, **_k):
        raise L._requests.ConnectionError("dns")
    fake_http(get=_giu)
    with pytest.raises(L.SuperbError, match="connessione"):
        L.main_superb("2026-07-18")


def test_risposta_non_json(fake_http):
    fake_http(get=FakeResponse(200, json_error=True))
    with pytest.raises(L.SuperbError, match="non leggibile"):
        L.main_superb("2026-07-18")


def test_errore_applicativo_non_mostra_dati(fake_http):
    fake_http(get=FakeResponse(200, {"success": False, "data": [_booking()]}))
    with pytest.raises(L.SuperbError) as e:
        L.main_superb("2026-07-18")
    assert "Mario" not in str(e.value) and "333" not in str(e.value)


def test_sessione_mancante(cfg_dir, fake_http):
    (cfg_dir / "config.json").write_text("{}", encoding="utf-8")
    fake_http()
    with pytest.raises(RuntimeError, match="non configurata"):
        L.main_superb("2026-07-18")


def test_ospiti_mancanti_e_nome_spezzato(fake_http):
    b = _booking(guests=None)
    b["user"]["name"] = {"first": "luca", "last": "verdi"}
    fake_http(get=FakeResponse(200, {"success": True, "data": [b]}))
    out, _ = L.main_superb("2026-07-18")
    assert out[0]["nome"] == "Luca Verdi" and "per ? persone" in out[0]["messaggio"]
