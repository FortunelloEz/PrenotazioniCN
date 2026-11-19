"""Template del messaggio: validazione, salvataggio sicuro, backup."""
import pytest

import logicaBE as L


@pytest.mark.parametrize("tpl", [
    "Ciao {nome}",
    "Ciao {nome}, {giorno} a {pasto} per {ospiti} {persone} alle {orario}",
    "Usa {{graffe}} vere e {nome}",
])
def test_template_validi(tpl):
    assert L.validate_template(tpl) == []


@pytest.mark.parametrize("tpl, frammento", [
    ("", "vuoto"),
    ("   ", "vuoto"),
    ("Ciao {tavolo}", "{tavolo}"),
    ("Ciao {Nome}", "{Nome}"),
    ("Ciao {nome", "bilanciate"),
    ("Ciao nome} :-}", "bilanciate"),
    ("Ciao {}", "vuota"),
    ("Ore {orario:>5}", "formati"),
    ("Ciao {nome.upper}", "sconosciuta"),
])
def test_template_non_validi(tpl, frammento):
    errori = L.validate_template(tpl)
    assert errori and frammento in " ".join(errori)


def test_build_message_con_template_rotto_da_errore_chiaro(monkeypatch):
    """Regressione #3: prima KeyError/ValueError criptici e nessun messaggio generato."""
    monkeypatch.setattr(L, "RUNTIME_TEMPLATE", "Ciao {nome} {tavolo}")
    with pytest.raises(L.TemplateError, match="Variabile sconosciuta"):
        L.build_message("Mario Rossi", "oggi", "cena", 2, "20:00")


def test_set_template_non_valido_non_tocca_il_file(api, cfg_dir):
    prima = (cfg_dir / "template.txt").read_text(encoding="utf-8")
    res = api.set_template("Ciao {tavolo}")
    assert res["ok"] is False and "{tavolo}" in res["error"]
    assert (cfg_dir / "template.txt").read_text(encoding="utf-8") == prima
    assert not list(cfg_dir.glob("template_*.bak.txt"))


def test_set_template_fa_backup_e_scrive(api, cfg_dir):
    prima = (cfg_dir / "template.txt").read_text(encoding="utf-8")
    res = api.set_template("  Nuovo {nome}  ")
    assert res["ok"] is True
    assert (cfg_dir / "template.txt").read_text(encoding="utf-8") == "Nuovo {nome}"
    backups = list(cfg_dir.glob("template_*.bak.txt"))
    assert len(backups) == 1 and backups[0].read_text(encoding="utf-8") == prima


def test_salvare_il_predefinito_disattiva_il_template_di_sessione(api):
    """Regressione: prima il template di sessione restava attivo e copriva quello appena salvato."""
    assert api.set_runtime_template("Sessione {nome}")["ok"]
    assert L.build_message("Mario", "oggi", "cena", 2, "20:00") == "Sessione Mario"
    assert api.set_template("Predefinito {nome}")["ok"]
    assert L.build_message("Mario", "oggi", "cena", 2, "20:00") == "Predefinito Mario"


def test_set_runtime_template_valida(api):
    res = api.set_runtime_template("Ciao {nome")
    assert res["ok"] is False
    assert L.RUNTIME_TEMPLATE is None


def test_reset_template(api, cfg_dir):
    api.set_template("Personale {nome}")
    api.set_runtime_template("Sessione {nome}")
    res = api.reset_template()
    assert res["ok"] is True
    default = (cfg_dir / "template_default.txt").read_text(encoding="utf-8")
    assert (cfg_dir / "template.txt").read_text(encoding="utf-8") == default
    assert L.RUNTIME_TEMPLATE is None
    assert any(p.read_text(encoding="utf-8") == "Personale {nome}"
               for p in cfg_dir.glob("template_backup_*.txt"))


def test_reset_con_default_rotto_non_cancella_il_template(api, cfg_dir):
    (cfg_dir / "template_default.txt").write_text("Rotto {tavolo}", encoding="utf-8")
    api.set_template("Mio {nome}")
    res = api.reset_template()
    assert res["ok"] is False
    assert (cfg_dir / "template.txt").read_text(encoding="utf-8") == "Mio {nome}"


def test_backup_limitati(api, cfg_dir, monkeypatch):
    """Impostazione MAX_TEMPLATE_BACKUPS: col valore cambiato cambia il numero di backup conservati."""
    monkeypatch.setattr(L, "MAX_TEMPLATE_BACKUPS", 3)
    for i in range(6):
        api.set_template(f"Versione {i} {{nome}}")
    assert len(list(cfg_dir.glob("template_*.bak.txt"))) == 3


def test_backup_predefinito_20(api, cfg_dir):
    for i in range(23):
        api.set_template(f"Versione {i} {{nome}}")
    assert len(list(cfg_dir.glob("template_*.bak.txt"))) == L.MAX_TEMPLATE_BACKUPS == 20
