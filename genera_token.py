# genera_token.py  — eseguilo con: python genera_token.py
import secrets
import hashlib
import json
from datetime import date, timedelta

def genera(giorni_validita: int = 30):
    raw = "-".join(secrets.token_hex(3).upper() for _ in range(4))
    h   = hashlib.sha256(raw.encode()).hexdigest()
    exp = (date.today() + timedelta(days=giorni_validita)).isoformat()
    return raw, h, exp

if __name__ == "__main__":
    n = int(input("Quanti token generare? ") or "1")
    giorni = int(input("Giorni di validità (default 30)? ") or "30")
    tokens = []
    for _ in range(n):
        raw, h, exp = genera(giorni)
        tokens.append({"token": raw, "hash": h, "expires": exp})
        print(f"  TOKEN: {raw}   →   hash: {h[:12]}...   scade: {exp}")

    with open("tokens_generati.json", "w") as f:
        json.dump(tokens, f, indent=2)
    print(f"\nSalvati in tokens_generati.json")