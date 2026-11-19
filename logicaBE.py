#logicaBE
import html
import os
import sys
import re
import json
import tempfile
from pathlib import Path
import base64
import csv
import io
import fitz
from urllib.parse import quote
from datetime import date
from openai import OpenAI
from definizioni_llm import SYSTEM_GLOBAL, USER_TMPL_GLOBAL

def reset_client() -> None:
    global client
    client = None

def get_base_dir() -> Path:
    # cartella dove sta l'exe
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    # In sviluppo: cartella del file .py
    return Path(__file__).resolve().parent

#Directories
BASE_DIR = get_base_dir()
CONFIG_DIR = BASE_DIR / "config"
CONFIG_FILE = CONFIG_DIR / "config.json"
TEMPLATE_FILE = CONFIG_DIR / "template.txt"
DEFAULT_TEMPLATE_FILE = CONFIG_DIR / "template_default.txt"
RUNTIME_TEMPLATE: str | None = None

# ───────────────────────────────────────────────
# SISTEMA LICENZE
# ───────────────────────────────────────────────
import hashlib
from datetime import date, datetime
import requests as _requests

LICENSE_SERVER_URL = ""

def _token_hash(token: str) -> str:
    return hashlib.sha256(token.strip().encode()).hexdigest()

def validate_license_online(token: str) -> dict:
    """
    Chiama il server e ritorna dict con:
      { "valid": bool, "expires": "YYYY-MM-DD" oppure None }
    In caso di errore di rete ritorna { "valid": False, "error": "..." }
    """
    try:
        r = _requests.post(
            LICENSE_SERVER_URL,
            json={"token_hash": _token_hash(token)},
            timeout=6
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"valid": False, "error": str(e)}

def check_license() -> tuple[bool, str]:
    """
    Controlla la licenza salvata in config.json.
    Ritorna (True, "") se valida, (False, messaggio_errore) se non valida.
    """
    cfg = load_config()
    token = cfg.get("license_token", "").strip()
    cached_expires = cfg.get("license_expires", "")
    last_check_str = cfg.get("license_last_check", "")

    if not token:
        return False, "Nessuna licenza inserita."

    # Controlla se l'ultima verifica online è di oggi → evita chiamata ogni avvio
    today_str = date.today().isoformat()
    if last_check_str == today_str and cached_expires:
        # Usa cache: verifica solo la scadenza
        try:
            exp = date.fromisoformat(cached_expires)
            if date.today() > exp:
                return False, f"Licenza scaduta il {cached_expires}."
            return True, ""
        except Exception:
            pass  # se la data è malformata, fa la chiamata online

    # Chiamata online
    result = validate_license_online(token)

    if not result.get("valid", False):
        err = result.get("error", "")
        if err:
            # Errore di rete: se abbiamo una cache ancora valida, lasciamo passare (grace period)
            if cached_expires:
                try:
                    exp = date.fromisoformat(cached_expires)
                    if date.today() <= exp:
                        return True, ""  # grace period: rete assente ma licenza non scaduta in cache
                except Exception:
                    pass
            return False, "Impossibile contattare il server licenze. Controlla la connessione."
        return False, "Licenza non valida."

    expires = result.get("expires", "")
    if not expires:
        return False, "Risposta server non valida (expires mancante)."

    try:
        exp = date.fromisoformat(expires)
        if date.today() > exp:
            return False, f"Licenza scaduta il {expires}."
    except Exception:
        return False, "Data scadenza non valida ricevuta dal server."

    # Salva in cache
    cfg["license_expires"] = expires
    cfg["license_last_check"] = today_str
    save_config(cfg)

    return True, ""

def save_license_token(token: str) -> tuple[bool, str]:
    """
    Salva il token e lo valida subito online.
    Ritorna (True, expires_str) oppure (False, messaggio_errore).
    """
    token = token.strip()
    if not token:
        return False, "Token vuoto."

    result = validate_license_online(token)
    if not result.get("valid", False):
        return False, "Token non valido o non riconosciuto dal server."

    expires = result.get("expires", "")
    if not expires:
        return False, "Risposta server non valida."

    try:
        date.fromisoformat(expires)
    except Exception:
        return False, "Data scadenza non valida."

    cfg = load_config()
    cfg["license_token"] = token
    cfg["license_expires"] = expires
    cfg["license_last_check"] = date.today().isoformat()
    save_config(cfg)

    return True, expires
# ───────────────────────────────────────────────
# FINE SISTEMA LICENZE
# ───────────────────────────────────────────────

def set_runtime_template(text: str | None) -> None:

    global RUNTIME_TEMPLATE
    text = (text or "").strip()
    RUNTIME_TEMPLATE = text or None

def load_template() -> str:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        default_tpl = DEFAULT_TEMPLATE_FILE.read_text(encoding="utf-8")
    except Exception:
        default_tpl = ""

    # Se il file esiste → lo leggiamo
    if TEMPLATE_FILE.exists():
        try:
            return TEMPLATE_FILE.read_text(encoding="utf-8")
        except Exception:
            # in caso esplodano permessi/encoding → fallback su default
            return default_tpl

    # Se non esiste → lo creiamo con default
    try:
        TEMPLATE_FILE.write_text(default_tpl, encoding="utf-8")
    except Exception:
        # se non riusciamo a scrivere comunque ritorniamo default
        return default_tpl

    return default_tpl

def load_api_key() -> str:
    key_path = get_base_dir() / "gptkey.txt"
    if not key_path.exists():
        raise FileNotFoundError(
            f"File gptkey.txt non trovato nella cartella: {key_path.parent}"
        )
    return key_path.read_text(encoding="utf-8").strip()


MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-2024-08-06")


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}

def save_config(cfg: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False),
                           encoding="utf-8")


def load_api_key_new() -> str:
    cfg = load_config()
    enc = cfg.get("api_key_encrypted", "").strip()
    if not enc:
        return ""
    import base64
    try:
        return base64.b64decode(enc.encode()).decode()
    except Exception:
        return ""

def load_api_key_legacy() -> str:
    """
    Vecchio metodo: gptkey.txt nella cartella base.
    Lo teniamo solo come fallback nel caso non esista ancora config.json.
    """
    key_path = get_base_dir() / "gptkey.txt"
    if not key_path.exists():
        return ""
    return key_path.read_text(encoding="utf-8").strip()


# ---- inizializzazione client OpenAI ----
client = None  # verrà creato alla prima chiamata


def get_client() -> OpenAI:
    global client
    if client is not None:
        return client

    api_key = load_api_key_new()
    if not api_key:
        api_key = load_api_key_legacy()

    if not api_key:
        raise RuntimeError("Nessuna API key configurata. Definirla dalle Impostazioni.")

    client = OpenAI(api_key=api_key)
    return client

# -------------------------------------------------------------------
# Utils
# -------------------------------------------------------------------
def normalize_phone(s: str) -> str:
    if not s:
        return ""
    digits = re.sub(r"\D", "", s)
    if not digits:
        return ""
    return "+" + digits


def cap_name(n: str) -> str:
    if not n:
        return n
    parts = [p for p in n.strip().split() if p]
    out = []
    for p in parts:
        out.append(p.upper() if len(p) == 1 else (p[0].upper() + p[1:].lower()))
    return " ".join(out)


def clean_name(n: str) -> str:
    if not n:
        return n
    if n.upper() in {"N", "C", "A", "S", "PS"}:
        return ""
    if re.fullmatch(r"\d{1,2}/\d{1,2}", n):
        return ""
    n = re.sub(r"[|•·\-–—,:;]+$", "", n).strip()
    return cap_name(n)

def load_pdf_text(pdf_path: Path) -> str:
    doc = fitz.open(str(pdf_path))
    chunks: list[str] = []

    for i, page in enumerate(doc, start=1):
        txt = page.get_text("text") or ""
        header = f"\n\n===== PAGINA {i} =====\n\n"
        chunks.append(header + txt)

    doc.close()
    return "\n".join(chunks).strip()

def load_file_text(file_path: Path) -> str:
    """Dispatcher multi-formato: PDF, immagini, CSV, TXT."""
    ext = file_path.suffix.lower()

    if ext == ".pdf":
        return load_pdf_text(file_path)

    elif ext in (".jpg", ".jpeg", ".png", ".tiff", ".webp"):
        return _load_image_via_llm(file_path)

    elif ext == ".csv":
        try:
            raw = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            raw = file_path.read_text(encoding="latin-1", errors="ignore")
        # converte CSV in testo tabellare leggibile dal LLM
        reader = csv.reader(io.StringIO(raw))
        lines = ["\t".join(row) for row in reader]
        return "\n".join(lines)

    elif ext in (".txt",):
        try:
            return file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return file_path.read_text(encoding="latin-1", errors="ignore")

    else:
        raise ValueError(f"Formato non supportato: {ext}")


def _load_image_via_llm(image_path: Path) -> str:
    ext = image_path.suffix.lower().replace(".", "")
    media_type = "jpeg" if ext in ("jpg", "jpeg") else ext
    b64 = base64.b64encode(image_path.read_bytes()).decode()

    c = get_client()
    resp = c.chat.completions.create(
        model="gpt-4o",
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/{media_type};base64,{b64}"}
                },
                {
                    "type": "text",
                    "text": (
                        "Questa immagine contiene una tabella di prenotazioni di un ristorante. "
                        "Estrai TUTTO il testo visibile mantenendo la struttura a colonne. "
                        "Includi intestazioni, nomi, telefoni, orari, stati e note. "
                        "Restituisci solo testo grezzo, nessun commento."
                    )
                }
            ]
        }],
        max_tokens=4000,
    )
    return resp.choices[0].message.content or ""



def call_llm_global(raw_text: str) -> dict:
    messages = [
        {"role": "system", "content": SYSTEM_GLOBAL},
        {"role": "user", "content": USER_TMPL_GLOBAL.format(body=raw_text)}
    ]

    c = get_client()
    resp = c.chat.completions.create(
        model=MODEL,
        messages=messages,
        response_format={"type": "json_object"},
        temperature=0,
        max_tokens=8000,
    )

    raw = resp.choices[0].message.content or "{}"

    try:
        return json.loads(raw)
    except Exception:
        return {
            "data_servizio": None,
            "colonne": [],
            "prenotazioni": []
        }

def nome_breve(nome: str) -> str:
    if not nome:
        return ""
    first = nome.strip().split()[0]
    return re.sub(r"[^\wÀ-ÖØ-öø-ÿ'-]", "", first)


def infer_pasto(orario, pasto):
    p = (pasto or "").strip().lower()
    if p in ("pranzo", "lunch"):    return "pranzo"
    if p in ("aperitivo", "aperitif"): return "aperitivo"
    if p in ("cena", "dinner"):     return "cena"

    # fallback sull'orario
    if orario:
        try:
            h = int(str(orario).split(":")[0])
            if 11 <= h <= 15: return "pranzo"
            if 16 <= h <= 18: return "aperitivo"
            if h >= 19:       return "cena"
        except Exception:
            pass
    return None

def format_data_label(svc: date | None) -> str | None:
    """
    Ritorna una stringa tipo 'Sabato 17 gennaio' per la data servizio.
    Se svc è None, ritorna None.
    """
    if not svc:
        return None

    giorni = [
        "Lunedì", "Martedì", "Mercoledì",
        "Giovedì", "Venerdì", "Sabato", "Domenica"
    ]
    mesi = [
        "gennaio", "febbraio", "marzo", "aprile",
        "maggio", "giugno", "luglio", "agosto",
        "settembre", "ottobre", "novembre", "dicembre"
    ]

    giorno_sett = giorni[svc.weekday()]
    mese = mesi[svc.month - 1]
    return f"{giorno_sett} {svc.day} {mese}"

def frase_giorno(svc: date | None) -> str:
    if not svc:
        return "oggi"
    giorni = {
        0: "lunedì",
        1: "martedì",
        2: "mercoledì",
        3: "giovedì",
        4: "venerdì",
        5: "sabato",
        6: "domenica",
    }
    return giorni[svc.weekday()]


def clean_phone_to_wa(telefono: str) -> str:
    return re.sub(r"\D", "", telefono or "")


def format_giorno_for_sentence(giorno: str, pasto_text: str) -> str:
    if not giorno:
        return "di questa sera" if pasto_text == "cena" else "di oggi"

    g = giorno.strip()
    g_lower = g.lower()

    if g_lower == "oggi":
        return "di questa sera" if pasto_text == "cena" else "di oggi"

    giorni_maschili = {
        "lunedi", "lunedì",
        "martedi", "martedì",
        "mercoledi", "mercoledì",
        "giovedi", "giovedì",
        "venerdi", "venerdì",
        "sabato"
    }
    if g_lower in giorni_maschili:
        return f"di questo {g_lower}"

    if g_lower == "domenica":
        return "di questa domenica"

    return f"a {g}"


def build_message(nome: str, giorno: str, pasto: str, ospiti: int | None, orario: str | None) -> str:
    nome = nome_breve(nome) or ""
    ppl = str(ospiti) if ospiti is not None else "?"
    hhmm = orario or "?"
    pasto_text = pasto or "?"
    giorno = format_giorno_for_sentence(giorno, pasto_text)
    persone = "persona" if ppl == "1" else "persone"

    global RUNTIME_TEMPLATE
    if RUNTIME_TEMPLATE is not None:
        template = RUNTIME_TEMPLATE
    else:
        template = load_template()

    msg = template.format(
        nome=nome,
        giorno=giorno,
        pasto=pasto_text,
        ospiti=ppl,
        persone=persone,
        orario=hhmm
    )
    if pasto == "aperitivo" and "a aperitivo" in msg:
        msg = msg.replace("a aperitivo", "per l'aperitivo")
    return msg

def recompute_records(records: list) -> list:
    out = []
    for r in records:
        nome = r.get("nome", "")
        telefono = r.get("telefono", "")
        orario = r.get("orario", "")
        ospiti = r.get("ospiti", "")
        giorno = r.get("giorno", "")

        pasto = infer_pasto(orario, r.get("pasto", ""))

        msg = build_message(nome, giorno, pasto, ospiti, orario)
        wa_number = clean_phone_to_wa(telefono)
        wa_link = f"https://wa.me/{wa_number}?text={quote(msg, safe='')}" if wa_number else "#"

        r_out = dict(r)
        r_out["pasto"] = pasto
        r_out["messaggio"] = msg
        r_out["link_whatsapp"] = wa_link
        r_out["telefono_wa"] = wa_number
        out.append(r_out)
    return out

# ───────────────────────────────────────────────
# INTEGRAZIONE SUPERB
# ───────────────────────────────────────────────
from datetime import timedelta
from zoneinfo import ZoneInfo

_SUPERB_API = "https://api.superbexperience.com"
_ROME_TZ = ZoneInfo("Europe/Rome")

_SUPERB_HEADERS_BASE = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
    "client-identifier": "web-partner",
    "client-version": "1.24.0",
    "origin": "https://partner.superbexperience.com",
    "referer": "https://partner.superbexperience.com/",
    "utc": "true",
}

def fetch_superb(date_str: str) -> list[dict]:
    cfg = load_config()
    session = cfg.get("superb_session", "").strip()
    restaurant_id = cfg.get("superb_restaurant_id", "").strip()

    if not session:
        raise RuntimeError("Sessione Superb non configurata. Inserirla dalle Impostazioni.")
    if not restaurant_id:
        raise RuntimeError("ID ristorante Superb non configurato.")

    # Replica esatta del range usato dal browser: T02:00:00Z → T02:00:00Z giorno dopo
    d = date.fromisoformat(date_str)
    start = f"{d.isoformat()}T02:00:00.000Z"
    end   = f"{(d + timedelta(days=1)).isoformat()}T02:00:00.000Z"

    q = json.dumps({
        "takeAway": False,
        "restaurant": restaurant_id,
        "startDate": start,
        "endDate": end,
    }, separators=(",", ":"))

    headers = dict(_SUPERB_HEADERS_BASE)
    headers["restaurant"] = restaurant_id

    r = _requests.get(
        f"{_SUPERB_API}/booking/dashboard",
        params={"sort": "arrival", "q": q},
        headers=headers,
        cookies={"koa:sess": session},
        timeout=10,
    )

    if r.status_code == 401:
        raise RuntimeError("Sessione Superb scaduta. Rinnovarla dalle Impostazioni → Configura Superb.")
    r.raise_for_status()

    data = r.json()
    if not data.get("success"):
        raise RuntimeError(f"Superb ha risposto con errore: {data}")

    return data.get("data", [])


def _arrival_to_orario(arrival: str) -> str:
    if not arrival:
        return ""
    try:
        dt_utc = datetime.fromisoformat(arrival.replace("Z", "+00:00"))
        dt_local = dt_utc.astimezone(_ROME_TZ)
        return dt_local.strftime("%H:%M")
    except Exception:
        return arrival[11:16] if len(arrival) >= 16 else ""


def normalize_superb_record(raw: dict, svc_date: date | None = None) -> dict:
    user     = raw.get("user") or {}
    name_obj = user.get("name") or {}
    arrival  = raw.get("arrival", "")

    nome_raw = (
        name_obj.get("full")
        or f"{name_obj.get('first', '')} {name_obj.get('last', '')}".strip()
    )

    sub = raw.get("subStatuses")
    stato = ""
    if isinstance(sub, list) and sub:
        stato = sub[0]
    elif isinstance(sub, str):
        stato = sub

    note_parts = []
    for campo in ("notes", "note", "internalNote", "guestNote", "comment"):
        v = raw.get(campo) or user.get(campo)
        if v and str(v).strip():
            note_parts.append(str(v).strip())
    note = " | ".join(note_parts)

    data_iso = svc_date.isoformat() if svc_date else arrival[:10]

    return {
        "nome":             clean_name(nome_raw),
        "telefono":         normalize_phone(user.get("mobile") or user.get("phone") or ""),
        "orario":           _arrival_to_orario(arrival),
        "ospiti":           raw.get("guests"),
        "stato":            stato,
        "note":             note,
        "data_servizio":    data_iso,
        "_superb_id":       raw.get("_id", ""),
    }


def main_superb(date_str: str, giorno_override: str | None = None) -> tuple[list[dict], str]:
    raw_records = fetch_superb(date_str)

    try:
        svc_date = date.fromisoformat(date_str)
    except Exception:
        svc_date = None

    colonne = ["nome", "telefono", "orario", "ospiti", "stato", "note"]

    giorno = giorno_override.strip() if giorno_override else frase_giorno(svc_date)

    enriched = []
    for raw in raw_records:
        rec   = normalize_superb_record(raw, svc_date)
        pasto = infer_pasto(rec.get("orario"), rec.get("pasto"))
        msg   = build_message(rec["nome"], giorno, pasto, rec.get("ospiti"), rec.get("orario"))
        wa_number = clean_phone_to_wa(rec["telefono"])
        wa_link   = f"https://wa.me/{wa_number}?text={quote(msg, safe='')}" if wa_number else "#"

        rec["pasto"]               = pasto
        rec["messaggio"]           = msg
        rec["link_whatsapp"]       = wa_link
        rec["telefono_wa"]         = wa_number
        rec["giorno"]              = giorno
        rec["data_servizio_label"] = format_data_label(svc_date) or ""
        rec["_colonne"]            = colonne
        enriched.append(rec)

    print(f"Superb: {len(enriched)} prenotazioni per {date_str}")
    html_path = BASE_DIR / "prenotazioni_wa.html"
    save_html(enriched, html_path)
    return enriched, str(html_path)

# ───────────────────────────────────────────────
# FINE INTEGRAZIONE SUPERB
# ───────────────────────────────────────────────

def estrai(pdf_path: Path):
    raw_text = load_file_text(Path(pdf_path))

    obj = call_llm_global(raw_text)

    colonne = obj.get("colonne", [])
    prenotazioni = obj.get("prenotazioni", []) or []

    svc_date_llm: date | None = None
    iso = obj.get("data_servizio")
    if iso:
        try:
            svc_date_llm = date.fromisoformat(str(iso).strip()[:10])
        except Exception:
            svc_date_llm = None

    out = []
    for r in prenotazioni:
        nome = clean_name(r.get("nome") or "")
        tel_raw = r.get("telefono") or ""
        tel_norm = normalize_phone(tel_raw)

        rec = dict(r)
        rec["nome"] = nome
        rec["telefono"] = tel_norm
        rec["data_servizio"] = svc_date_llm.isoformat() if svc_date_llm else None
        out.append(rec)

    print(f"Estratte {len(out)} prenotazioni")
    print(f"Colonne trovate: {colonne}")
    return out, colonne, svc_date_llm


def save_html(enriched: list[dict], path_html: Path, title="WhatsApp — Cascina Nascosta"):
    head = f"""<!DOCTYPE html>
<html lang="it"><head><meta charset="utf-8">
<title>{html.escape(title)}</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{{font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;margin:24px}}
table{{border-collapse:collapse;width:100%}}
th,td{{border:1px solid #ddd;padding:8px}}
th{{background:#f5f5f5;text-align:left}}
tr:nth-child(even){{background:#fafafa}}
a{{text-decoration:none}}
</style></head><body>
<h1>{html.escape(title)}</h1>
<table><thead><tr>
<th>Nome</th><th>Telefono</th><th>Orario</th><th>Ospiti</th><th>Pasto</th><th>Stato</th><th>Giorno</th><th>Note</th><th>WhatsApp</th>
</tr></thead><tbody>"""
    rows = []
    for r in enriched:
        nome = html.escape(str(r.get("nome", "")))
        tel = html.escape(str(r.get("telefono_wa", "")))
        orario = html.escape(str(r.get("orario", "")))
        ospiti = html.escape(str(r.get("ospiti", "")))
        pasto = html.escape(str(r.get("pasto", "")))
        giorno = html.escape(str(r.get("giorno", "")))
        stato = html.escape(str(r.get("stato", "")))
        note = html.escape(str(r.get("note", "")))
        link = html.escape(str(r.get("link_whatsapp", "")))
        rows.append(
            f"<tr><td>{nome}</td><td>{tel}</td><td>{orario}</td><td>{ospiti}</td>"
            f"<td>{pasto}</td><td>{stato}</td><td>{giorno}</td><td>{note}</td><td><a target='_blank' href='{link}'>Apri chat</a></td></tr>"        )
    tail = "</tbody></table></body></html>"
    path_html.write_text(head + "\n".join(rows) + tail, encoding="utf-8")


def main(pdf_path: str, svc_date: date | None = None, giorno_override: str | None = None):
    records, colonne, svc_date_found = estrai(Path(pdf_path))

    if svc_date is None:
        svc_date = svc_date_found
    enriched = []

    for r in records:
        nome = r.get("nome", "")
        telefono = r.get("telefono", "")
        orario = r.get("orario", "")
        ospiti = r.get("ospiti", "")

        if giorno_override:
            giorno = giorno_override
        elif svc_date:
            giorno = frase_giorno(svc_date)
        else:
            giorno = ""

        pasto = infer_pasto(orario, r.get("pasto", ""))

        msg = build_message(nome, giorno, pasto, ospiti, orario)
        wa_number = clean_phone_to_wa(telefono)
        wa_link = f"https://wa.me/{wa_number}?text={quote(msg, safe='')}" if wa_number else "#"

        r_out = dict(r)
        r_out["pasto"] = pasto
        r_out["messaggio"] = msg
        r_out["link_whatsapp"] = wa_link
        r_out["telefono_wa"] = wa_number
        r_out["giorno"] = giorno
        r_out["data_servizio_label"] = f"{svc_date.day} {svc_date.strftime('%B %Y')}" if svc_date else ""
        r_out["_colonne"] = colonne
        enriched.append(r_out)

    print("Creati messaggi/link WhatsApp")

    html_path = BASE_DIR / "prenotazioni_wa.html"
    save_html(enriched, html_path)
    print(f"Creato HTML")

    return enriched, str(html_path)
