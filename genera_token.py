# genera_token.py  — eseguilo con: python genera_token.py
# I token generati vengono AGGIUNTI a tokens_generati.json (quelli vecchi restano).
# tokens_generati.json contiene segreti: non va mai nel repository né nell'installer.
import secrets
import hashlib
import json
import os
import shutil
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

TOKENS_FILE = Path(__file__).resolve().parent / "tokens_generati.json"


def genera(giorni_validita: int = 30):
    raw = "-".join(secrets.token_hex(3).upper() for _ in range(4))
    h   = hashlib.sha256(raw.encode()).hexdigest()
    exp = (date.today() + timedelta(days=giorni_validita)).isoformat()
    return raw, h, exp


def carica_esistenti(path: Path = TOKENS_FILE) -> list:
    """Legge i token già generati. Se il file è illeggibile si ferma: meglio non scrivere che perderli."""
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{path.name} non contiene una lista: controllalo a mano prima di continuare.")
    return data


def salva_aggiungendo(nuovi: list, path: Path = TOKENS_FILE) -> int:
    """Aggiunge i nuovi token a quelli esistenti (copia di sicurezza + scrittura atomica). Ritorna il totale."""
    esistenti = carica_esistenti(path)
    if path.exists():
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.copy2(path, path.with_name(f"{path.stem}.backup_{ts}.json"))
    tutti = esistenti + nuovi
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(tutti, f, indent=2)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return len(tutti)


def _chiedi_intero(domanda: str, predefinito: int) -> int:
    while True:
        risposta = input(domanda).strip()
        if not risposta:
            return predefinito
        if risposta.isdigit() and int(risposta) > 0:
            return int(risposta)
        print("  Scrivi un numero intero maggiore di zero.")


if __name__ == "__main__":
    n = _chiedi_intero("Quanti token generare? ", 1)
    giorni = _chiedi_intero("Giorni di validità (default 30)? ", 30)
    tokens = []
    for _ in range(n):
        raw, h, exp = genera(giorni)
        tokens.append({"token": raw, "hash": h, "expires": exp, "creato": date.today().isoformat()})
        print(f"  TOKEN: {raw}   →   hash: {h[:12]}...   scade: {exp}")

    totale = salva_aggiungendo(tokens)
    print(f"\nAggiunti {len(tokens)} token a {TOKENS_FILE.name} (totale nel file: {totale}).")
