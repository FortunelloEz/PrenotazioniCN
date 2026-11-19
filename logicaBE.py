#logicaBE
import html
import os
import sys
import re
import json
import shutil
import string
import tempfile
from pathlib import Path
import base64
import csv
import io
import pymupdf as fitz  # "import fitz" è deprecato da PyMuPDF 2.x
from urllib.parse import quote
from datetime import date
from openai import OpenAI
from definizioni_llm import SYSTEM_GLOBAL, USER_TMPL_GLOBAL


class ConfigError(RuntimeError):
    """La configurazione non si può leggere o scrivere senza rischiare di perderla."""


class TemplateError(ValueError):
    """Il template del messaggio non è valido: nessun messaggio deve partire."""


class LLMError(RuntimeError):
    """L'AI non ha restituito un risultato utilizzabile (non va confuso con «0 prenotazioni»)."""


class SuperbError(RuntimeError):
    """Errore nello scarico da Superb, con messaggio già comprensibile per l'utente."""

def reset_client() -> None:
    global client
    client = None

def get_base_dir() -> Path:
    # cartella dove sta l'exe
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    # In sviluppo: cartella del file .py
    return Path(__file__).resolve().parent

# ───────────────────────────────────────────────
# CARTELLE
# BASE_DIR = cartella del programma (exe). Può non essere scrivibile.
# DATA_DIR = dati e configurazione dell'utente:
#   - app installata (frozen): %APPDATA%\PrenotazioniCN
#   - sviluppo: la cartella del progetto (comportamento di sempre)
#   - variabile d'ambiente PRENOTAZIONICN_DATA_DIR: vince su tutto
# All'avvio prepare_data_dir() migra la vecchia config (BASE_DIR\config) copiandola:
# l'originale non viene mai cancellato.
# ───────────────────────────────────────────────
BASE_DIR = get_base_dir()
APP_FOLDER_NAME = "PrenotazioniCN"
RUNTIME_TEMPLATE: str | None = None
_DATA_WARNING: str | None = None


def default_data_dir() -> Path:
    override = os.environ.get("PRENOTAZIONICN_DATA_DIR", "").strip()
    if override:
        return Path(override)
    if getattr(sys, "frozen", False) and os.environ.get("APPDATA"):
        return Path(os.environ["APPDATA"]) / APP_FOLDER_NAME
    return BASE_DIR


def use_data_dir(data_dir: Path) -> None:
    """Imposta tutti i percorsi dei dati a partire da data_dir (unico punto)."""
    global DATA_DIR, CONFIG_DIR, CONFIG_FILE, TEMPLATE_FILE, DEFAULT_TEMPLATE_FILE
    DATA_DIR = Path(data_dir)
    CONFIG_DIR = DATA_DIR / "config"
    CONFIG_FILE = CONFIG_DIR / "config.json"
    TEMPLATE_FILE = CONFIG_DIR / "template.txt"
    DEFAULT_TEMPLATE_FILE = CONFIG_DIR / "template_default.txt"


use_data_dir(default_data_dir())


def get_data_warning() -> str | None:
    return _DATA_WARNING


def _copy_dir_verified(src: Path, dest: Path) -> list[str]:
    """Copia src in dest (che non deve esistere) passando da una cartella temporanea; verifica byte per byte."""
    tmp = dest.with_name(dest.name + ".migrazione_in_corso")
    if tmp.exists():
        shutil.rmtree(tmp)
    shutil.copytree(src, tmp)
    copiati = []
    for f in src.rglob("*"):
        if f.is_file():
            rel = f.relative_to(src)
            if (tmp / rel).read_bytes() != f.read_bytes():
                shutil.rmtree(tmp, ignore_errors=True)
                raise OSError(f"copia non identica: {rel}")
            copiati.append(str(rel))
    os.replace(tmp, dest)
    return copiati


def prepare_data_dir(data_dir: Path | None = None, legacy_dir: Path | None = None) -> Path:
    """
    Da chiamare all'avvio, prima di leggere la config.
    Se la cartella dati non ha ancora una config e la vecchia (accanto all'exe) esiste,
    la copia (verificata) e lascia l'originale dov'è. In caso di problemi usa la vecchia
    cartella, così l'app funziona come prima, e avvisa.
    """
    global _DATA_WARNING
    data_dir = Path(data_dir) if data_dir else default_data_dir()
    legacy_cfg = Path(legacy_dir) if legacy_dir else BASE_DIR / "config"
    target_cfg = data_dir / "config"
    if data_dir.resolve() == BASE_DIR.resolve() or target_cfg.exists():
        use_data_dir(data_dir)
        return data_dir
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        if legacy_cfg.is_dir():
            copiati = _copy_dir_verified(legacy_cfg, target_cfg)
            nota = (
                f"Migrazione del {datetime.now():%d/%m/%Y %H:%M}\n"
                f"Configurazione copiata da: {legacy_cfg}\n"
                f"File copiati e verificati: {len(copiati)}\n\n"
                "La vecchia cartella NON è stata cancellata: contiene ancora la vecchia configurazione\n"
                "(anche la chiave ChatGPT in base64). Quando la nuova versione funziona, si può eliminare.\n"
            )
            _atomic_write_text(data_dir / "MIGRAZIONE.txt", nota)
        else:
            target_cfg.mkdir(parents=True, exist_ok=True)
        use_data_dir(data_dir)
        return data_dir
    except OSError as e:
        _DATA_WARNING = (
            f"Non sono riuscito a preparare la cartella dati «{data_dir}» ({e}). "
            f"Uso ancora la configurazione in «{legacy_cfg}»: nessun dato è stato perso."
        )
        use_data_dir(legacy_cfg.parent)
        return legacy_cfg.parent

# ───────────────────────────────────────────────
# SISTEMA LICENZE
# ───────────────────────────────────────────────
import hashlib
from datetime import datetime
import requests as _requests

LICENSE_SERVER_URL = ""

def _token_hash(token: str) -> str:
    return hashlib.sha256(token.strip().encode()).hexdigest()

def validate_license_online(token: str) -> dict:
    """
    Chiama il server e ritorna dict con:
      { "valid": bool, "expires": "YYYY-MM-DD" oppure None }
    In caso di errore di rete o risposta malformata ritorna { "valid": False, "error": "..." }
    """
    try:
        r = _requests.post(
            LICENSE_SERVER_URL,
            json={"token_hash": _token_hash(token)},
            timeout=6
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        return {"valid": False, "error": str(e)}
    if not isinstance(data, dict):
        return {"valid": False, "error": "Risposta del server licenze non valida."}
    # Solo un vero booleano true conta come valido (una stringa "false" non deve sbloccare).
    data["valid"] = data.get("valid") is True
    return data

def check_license() -> tuple[bool, str]:
    """
    Controlla la licenza salvata in config.json.
    Ritorna (True, "") se valida, (False, messaggio_errore) se non valida.
    """
    cfg = load_config()
    token = str(cfg.get("license_token") or "").strip()
    cached_expires = str(cfg.get("license_expires") or "")
    last_check_str = str(cfg.get("license_last_check") or "")

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

    # Salva in cache (se non si riesce a scrivere, la licenza resta comunque valida per oggi)
    try:
        update_config({"license_expires": expires, "license_last_check": today_str})
    except ConfigError as e:
        print(f"Avviso: cache licenza non salvata: {e}")

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

    try:
        update_config({
            "license_token": token,
            "license_expires": expires,
            "license_last_check": date.today().isoformat(),
        })
    except ConfigError as e:
        return False, str(e)

    return True, expires
# ───────────────────────────────────────────────
# FINE SISTEMA LICENZE
# ───────────────────────────────────────────────

# Variabili ammesse nel template del messaggio (unico elenco: UI, validazione e build_message).
TEMPLATE_FIELDS = ("nome", "giorno", "pasto", "ospiti", "persone", "orario")

# Quanti backup del template conservare (i più vecchi vengono eliminati).
MAX_TEMPLATE_BACKUPS = 20


def validate_template(text: str | None) -> list[str]:
    """Ritorna l'elenco degli errori del template (vuoto = valido)."""
    if not (text or "").strip():
        return ["Il template è vuoto."]
    disponibili = ", ".join("{" + f + "}" for f in TEMPLATE_FIELDS)
    try:
        parsed = list(string.Formatter().parse(text))
    except ValueError:
        return ["Parentesi graffe non bilanciate. Le variabili si scrivono così: {nome}. "
                "Per scrivere una graffa nel testo usa {{ oppure }}."]
    errors: list[str] = []
    for _literal, field, spec, conv in parsed:
        if field is None:
            continue
        if field == "":
            errors.append("C'è una coppia di graffe vuota {}. Variabili disponibili: " + disponibili + ".")
        elif field not in TEMPLATE_FIELDS:
            errors.append(f"Variabile sconosciuta {{{field}}}. Variabili disponibili: {disponibili}.")
        elif spec or conv:
            errors.append(f"La variabile {{{field}}} non accetta formati: scrivi solo {{{field}}}.")
    # niente doppioni nello stesso messaggio di errore
    return list(dict.fromkeys(errors))


def set_runtime_template(text: str | None) -> None:
    """Template solo di sessione. Va validato prima (validate_template)."""
    global RUNTIME_TEMPLATE
    text = (text or "").strip()
    RUNTIME_TEMPLATE = text or None


def _prune_template_backups(keep: int | None = None) -> None:
    keep = MAX_TEMPLATE_BACKUPS if keep is None else keep
    backups = sorted(
        list(CONFIG_DIR.glob("template_*.bak.txt")) + list(CONFIG_DIR.glob("template_backup_*.txt")),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for old in backups[keep:]:
        try:
            old.unlink()
        except OSError:
            pass


def backup_template(kind: str = "bak") -> Path | None:
    """Copia template.txt in un backup datato (il file originale resta al suo posto)."""
    if not TEMPLATE_FILE.exists():
        return None
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    name = f"template_backup_{ts}.txt" if kind == "reset" else f"template_{ts}.bak.txt"
    dest = TEMPLATE_FILE.with_name(name)
    shutil.copy2(TEMPLATE_FILE, dest)
    _prune_template_backups()
    return dest


def save_template(text: str) -> None:
    """Salva il template predefinito: valida, fa il backup, scrive in modo atomico."""
    errors = validate_template(text)
    if errors:
        raise TemplateError(" ".join(errors))
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    backup_template("bak")
    _atomic_write_text(TEMPLATE_FILE, text.strip())
    # Il template di sessione non deve "coprire" quello appena salvato.
    set_runtime_template(None)


def default_template_path() -> Path:
    """template_default.txt: nella cartella dati; se manca, quello installato accanto al programma."""
    if DEFAULT_TEMPLATE_FILE.exists():
        return DEFAULT_TEMPLATE_FILE
    return BASE_DIR / "config" / "template_default.txt"


def reset_template_to_default() -> None:
    """Riporta il template a quello di fabbrica (con backup del precedente)."""
    path = default_template_path()
    default_tpl = path.read_text(encoding="utf-8") if path.exists() else ""
    errors = validate_template(default_tpl)
    if errors:
        raise TemplateError("Il template di fabbrica (template_default.txt) non è valido: " + " ".join(errors))
    backup_template("reset")
    _atomic_write_text(TEMPLATE_FILE, default_tpl)
    set_runtime_template(None)


def load_template() -> str:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        default_tpl = default_template_path().read_text(encoding="utf-8")
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
        _atomic_write_text(TEMPLATE_FILE, default_tpl)
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
# Modello per leggere le immagini (prima scritto fisso dentro _load_image_via_llm).
MODEL_VISION = os.getenv("OPENAI_VISION_MODEL", "gpt-4o")


# ───────────────────────────────────────────────
# CONFIGURAZIONE (chiave API, licenza, sessione Superb)
# Regole: scrittura atomica (file temporaneo + rinomina); un file illeggibile
# non viene mai sovrascritto senza averne prima conservato una copia, e
# l'utente viene avvisato (get_config_warning).
# ───────────────────────────────────────────────
_CONFIG_WARNING: str | None = None


class _ConfigCorrupt(Exception):
    pass


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _read_config_strict() -> dict:
    """Legge config.json. Solleva OSError se non leggibile, _ConfigCorrupt se danneggiato."""
    if not CONFIG_FILE.exists():
        return {}
    raw = CONFIG_FILE.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except ValueError as e:
        raise _ConfigCorrupt(str(e)) from e
    if not isinstance(data, dict):
        raise _ConfigCorrupt("il contenuto non è un oggetto JSON")
    return data


def _preserve_corrupt_config() -> Path:
    """Conserva una copia del config danneggiato (una sola copia per contenuto uguale)."""
    global _CONFIG_WARNING
    content = CONFIG_FILE.read_bytes()
    for existing in CONFIG_DIR.glob("config.danneggiato_*.json"):
        try:
            if existing.read_bytes() == content:
                dest = existing
                break
        except OSError:
            continue
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        dest = CONFIG_DIR / f"config.danneggiato_{ts}.json"
        shutil.copy2(CONFIG_FILE, dest)
    _CONFIG_WARNING = (
        "Il file di configurazione era danneggiato. Ne ho conservato una copia in "
        f"«{dest}». Chiave ChatGPT, licenza o sessione Superb potrebbero andare reinserite."
    )
    return dest


def get_config_warning() -> str | None:
    return _CONFIG_WARNING


def load_config() -> dict:
    """Lettura tollerante (per mostrare/usare i valori): mai un'eccezione, ma avvisa."""
    global _CONFIG_WARNING
    try:
        return _read_config_strict()
    except _ConfigCorrupt:
        try:
            _preserve_corrupt_config()
        except OSError as e:
            _CONFIG_WARNING = f"Il file di configurazione è danneggiato e non riesco a copiarlo: {e}"
        return {}
    except OSError as e:
        _CONFIG_WARNING = f"Impossibile leggere il file di configurazione: {e}"
        return {}


def update_config(changes: dict, remove: list[str] | tuple = ()) -> dict:
    """
    Aggiorna solo le chiavi indicate, rileggendo il file appena prima di scrivere.
    - file illeggibile (es. bloccato) → ConfigError, nessuna scrittura;
    - file danneggiato → prima se ne conserva una copia, poi si riparte da {}.
    """
    try:
        cfg = _read_config_strict()
    except _ConfigCorrupt:
        try:
            _preserve_corrupt_config()
        except OSError as e:
            raise ConfigError(
                f"Il file di configurazione è danneggiato e non riesco a farne una copia: {e}. "
                "Salvataggio annullato per non perdere dati."
            ) from e
        cfg = {}
    except OSError as e:
        raise ConfigError(f"Impossibile leggere il file di configurazione ({e}). Salvataggio annullato.") from e
    cfg.update(changes)
    for k in remove or ():
        cfg.pop(k, None)
    save_config(cfg)
    return cfg


def save_config(cfg: dict) -> None:
    try:
        _atomic_write_text(CONFIG_FILE, json.dumps(cfg, indent=2, ensure_ascii=False))
    except OSError as e:
        raise ConfigError(f"Impossibile salvare la configurazione: {e}") from e


# ───────────────────────────────────────────────
# CHIAVE API — cifrata con Windows DPAPI (legata all'utente Windows)
# Campo nuovo: "api_key_dpapi" (base64 del blob cifrato).
# Campo vecchio: "api_key_encrypted" (solo base64, NON cifrato): si legge ancora e
# viene convertito, rimuovendolo solo dopo aver verificato la decifratura.
# ───────────────────────────────────────────────
_DPAPI_ENTROPY = b"PrenotazioniCN/api_key/v1"


def dpapi_available() -> bool:
    return sys.platform == "win32"


def _dpapi(data: bytes, protect: bool) -> bytes:
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    def _blob(b: bytes):
        buf = ctypes.create_string_buffer(b, len(b))
        return DATA_BLOB(len(b), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf

    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    fn.argtypes = [ctypes.POINTER(DATA_BLOB), ctypes.c_void_p if not protect else wintypes.LPCWSTR,
                   ctypes.POINTER(DATA_BLOB), ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
                   ctypes.POINTER(DATA_BLOB)]
    fn.restype = wintypes.BOOL

    blob_in, _keep1 = _blob(data)
    entropy, _keep2 = _blob(_DPAPI_ENTROPY)
    blob_out = DATA_BLOB()
    CRYPTPROTECT_UI_FORBIDDEN = 0x1
    descr = "PrenotazioniCN" if protect else None
    ok = fn(ctypes.byref(blob_in), descr, ctypes.byref(entropy), None, None,
            CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(blob_out))
    if not ok:
        raise OSError(ctypes.get_last_error(), "DPAPI non riuscita")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(blob_out.pbData, ctypes.c_void_p))


def protect_api_key(key: str) -> str:
    return base64.b64encode(_dpapi(key.encode("utf-8"), True)).decode("ascii")


def unprotect_api_key(value: str) -> str:
    return _dpapi(base64.b64decode(value.encode("ascii")), False).decode("utf-8")


def api_key_config_changes(key: str) -> tuple[dict, list[str]]:
    """Cosa scrivere in config per salvare la chiave: (da aggiornare, da rimuovere)."""
    if dpapi_available():
        cifrata = protect_api_key(key)
        if unprotect_api_key(cifrata) != key:   # verifica prima di affidarsi
            raise OSError("verifica della cifratura non riuscita")
        return {"api_key_dpapi": cifrata}, ["api_key_encrypted"]
    return {"api_key_encrypted": base64.b64encode(key.encode()).decode()}, ["api_key_dpapi"]


def migrate_api_key() -> bool:
    """Converte la vecchia chiave base64 in DPAPI. True se ha convertito. Mai perdere la chiave."""
    if not dpapi_available():
        return False
    cfg = load_config()
    vecchia_b64 = str(cfg.get("api_key_encrypted") or "").strip()
    if not vecchia_b64 or str(cfg.get("api_key_dpapi") or "").strip():
        return False
    try:
        vecchia = base64.b64decode(vecchia_b64.encode()).decode()
    except Exception:
        return False   # valore illeggibile: lo si lascia com'è
    if not vecchia.strip():
        return False
    try:
        changes, remove = api_key_config_changes(vecchia)
        update_config(changes, remove=remove)
    except (OSError, ConfigError) as e:
        print(f"Avviso: chiave non convertita in DPAPI, resta il formato vecchio: {e}")
        return False
    return True


def load_api_key_new() -> str:
    global _CONFIG_WARNING
    cfg = load_config()
    cifrata = str(cfg.get("api_key_dpapi") or "").strip()
    if cifrata:
        try:
            return unprotect_api_key(cifrata)
        except Exception:
            _CONFIG_WARNING = ("La chiave ChatGPT salvata non è leggibile con questo utente Windows "
                               "(è stata salvata su un altro PC o da un altro utente). Reinseriscila dalle Impostazioni.")
            return ""
    enc = str(cfg.get("api_key_encrypted") or "").strip()
    if not enc:
        return ""
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
# Prefisso usato per i numeri italiani scritti senza prefisso internazionale.
DEFAULT_COUNTRY_CODE = "39"


def normalize_phone(s) -> str:
    """
    Ritorna il numero in formato +<prefisso><numero>, oppure "".
    - "+…" o "00…"            → già internazionale, si tiene il prefisso scritto;
    - 10 cifre che iniziano con 3 → cellulare italiano senza prefisso → +39;
    - inizia con un solo 0     → fisso italiano (nessun prefisso estero inizia per 0) → +39;
    - altrimenti               → "+" + cifre (caso ambiguo, invariato rispetto a prima).
    """
    if s is None:
        return ""
    s = str(s).strip()
    if not s:
        return ""
    digits = re.sub(r"\D", "", s)
    if not digits:
        return ""
    if s.lstrip("( ").startswith("+"):
        return "+" + digits
    if digits.startswith("00"):
        return "+" + digits[2:]
    if len(digits) == 10 and digits.startswith("3"):
        return "+" + DEFAULT_COUNTRY_CODE + digits
    if digits.startswith("0"):
        return "+" + DEFAULT_COUNTRY_CODE + digits
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
        text = load_pdf_text(file_path)
        # load_pdf_text aggiunge le intestazioni "===== PAGINA n =====": se resta solo quello, il PDF è una scansione
        if not re.sub(r"=+ PAGINA \d+ =+", "", text).strip():
            raise ValueError(
                "Il PDF non contiene testo selezionabile (probabilmente è una scansione). "
                "Salva la pagina come immagine PNG o JPG e carica l'immagine."
            )
        return text

    elif ext in (".tif", ".tiff"):
        raise ValueError("Le immagini TIFF non sono lette dall'AI: salvala come PNG o JPG e riprova.")

    elif ext in (".jpg", ".jpeg", ".png", ".webp"):
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
        model=MODEL_VISION,
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
    choice = resp.choices[0]
    if getattr(choice, "finish_reason", None) == "length":
        raise LLMError(
            "L'immagine contiene più testo di quanto l'AI riesca a leggere in una volta: "
            "ritagliala in due parti e caricale separatamente."
        )
    text = choice.message.content or ""
    if not text.strip():
        raise LLMError("L'AI non ha letto alcun testo nell'immagine. Controlla che sia nitida e riprova.")
    return text



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

    choice = resp.choices[0]
    if getattr(choice, "finish_reason", None) == "length":
        raise LLMError(
            "La risposta dell'AI è stata troncata: il file contiene troppe prenotazioni per una sola "
            "elaborazione. Dividilo in due parti e caricale separatamente. Nessuna prenotazione è stata caricata."
        )
    raw = choice.message.content or ""
    if not raw.strip():
        raise LLMError("L'AI ha restituito una risposta vuota. Riprova; se succede ancora, controlla il file.")

    try:
        obj = json.loads(raw)
    except ValueError as e:
        raise LLMError(
            "L'AI ha restituito una risposta non leggibile (JSON non valido). Riprova l'elaborazione."
        ) from e

    if not isinstance(obj, dict):
        raise LLMError("L'AI ha restituito una risposta con una struttura inattesa. Riprova l'elaborazione.")
    pren = obj.get("prenotazioni")
    if pren is None:
        obj["prenotazioni"] = []
    elif not isinstance(pren, list) or not all(isinstance(p, dict) for p in pren):
        raise LLMError("L'AI ha restituito le prenotazioni in un formato inatteso. Riprova l'elaborazione.")
    colonne = obj.get("colonne")
    if not isinstance(colonne, list):
        obj["colonne"] = []
    else:
        obj["colonne"] = [str(c) for c in colonne if isinstance(c, (str, int, float)) and str(c).strip()]
    return obj

def nome_breve(nome: str) -> str:
    if not nome:
        return ""
    first = nome.strip().split()[0]
    return re.sub(r"[^\wÀ-ÖØ-öø-ÿ'-]", "", first)


# Fasce orarie per riconoscere il pasto quando il file non lo dice (ore intere, estremi inclusi).
# Unico punto in cui sono definite. Fuori fascia (es. 10:xx o 00–10) → pasto non riconosciuto.
MEAL_HOUR_RANGES = (
    ("pranzo", 11, 15),
    ("aperitivo", 16, 18),
    ("cena", 19, 23),
)


def parse_hour(orario) -> int | None:
    """Ricava l'ora (0–23) da '19:30', '19.30', '19h30', '19', '7:30 PM'. None se non si capisce."""
    if orario is None:
        return None
    s = str(orario).strip().lower()
    m = re.match(r"^(\d{1,2})(?:\s*[:.h]\s*(\d{2}))?\s*(am|pm)?\b", s)
    if not m:
        return None
    h = int(m.group(1))
    ampm = m.group(3)
    if ampm == "pm" and h < 12:
        h += 12
    elif ampm == "am" and h == 12:
        h = 0
    return h if 0 <= h <= 23 else None


def infer_pasto(orario, pasto):
    p = (pasto or "").strip().lower()
    if p in ("pranzo", "lunch"):    return "pranzo"
    if p in ("aperitivo", "aperitif"): return "aperitivo"
    if p in ("cena", "dinner"):     return "cena"

    # fallback sull'orario
    h = parse_hour(orario)
    if h is not None:
        for nome, start, end in MEAL_HOUR_RANGES:
            if start <= h <= end:
                return nome
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

    # Il menu «Giorno» invia i nomi senza accento: nel messaggio al cliente vanno scritti giusti.
    giorni_maschili = {
        "lunedi": "lunedì", "lunedì": "lunedì",
        "martedi": "martedì", "martedì": "martedì",
        "mercoledi": "mercoledì", "mercoledì": "mercoledì",
        "giovedi": "giovedì", "giovedì": "giovedì",
        "venerdi": "venerdì", "venerdì": "venerdì",
        "sabato": "sabato",
    }
    if g_lower in giorni_maschili:
        return f"di questo {giorni_maschili[g_lower]}"

    if g_lower == "domenica":
        return "di questa domenica"

    return f"a {g}"


def get_active_template() -> str:
    """Template in uso: quello di sessione se impostato, altrimenti template.txt."""
    if RUNTIME_TEMPLATE is not None:
        return RUNTIME_TEMPLATE
    return load_template()


def campi_mancanti(pasto, ospiti, orario) -> list[str]:
    """
    Dati che mancano TRA QUELLI USATI dal template attivo: sono quelli che nel
    messaggio al cliente diventerebbero «?». Il frontend li usa per escludere la
    riga dall'invio in blocco e chiedere conferma sulla chat singola.
    """
    try:
        usati = {f for _l, f, _s, _c in string.Formatter().parse(get_active_template()) if f}
    except ValueError:
        return []
    out = []
    if "pasto" in usati and not pasto:
        out.append("pasto")
    if "ospiti" in usati and (ospiti is None or str(ospiti).strip() == ""):
        out.append("ospiti")
    if "orario" in usati and not orario:
        out.append("orario")
    return out


def build_message(nome: str, giorno: str, pasto: str, ospiti: int | None, orario: str | None) -> str:
    nome = nome_breve(nome) or ""
    # 0 è un valore vero (non "mancante"); None o stringa vuota → "?"
    ppl = "?" if ospiti is None or str(ospiti).strip() == "" else str(ospiti).strip()
    hhmm = orario or "?"
    pasto_text = pasto or "?"
    giorno = format_giorno_for_sentence(giorno, pasto_text)
    persone = "persona" if ppl == "1" else "persone"

    template = get_active_template()
    errors = validate_template(template)
    if errors:
        raise TemplateError(
            "Il template del messaggio non è valido, nessun messaggio è stato preparato. "
            + " ".join(errors) + " Correggilo da Impostazioni → Cambia template predefinito."
        )

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
        ospiti = r.get("ospiti")
        giorno = r.get("giorno", "")

        # «Esperienza personalizzata» (scelta dall'utente) vince sul riconoscimento automatico.
        personalizzato = str(r.get("pasto_personalizzato") or "").strip()
        pasto = personalizzato or infer_pasto(orario, r.get("pasto", ""))

        msg = build_message(nome, giorno, pasto, ospiti, orario)
        wa_number = clean_phone_to_wa(normalize_phone(telefono))
        wa_link = f"https://wa.me/{wa_number}?text={quote(msg, safe='')}" if wa_number else "#"

        r_out = dict(r)
        r_out["pasto"] = pasto
        r_out["telefono"] = normalize_phone(telefono)
        r_out["messaggio"] = msg
        r_out["link_whatsapp"] = wa_link
        r_out["telefono_wa"] = wa_number
        r_out["_mancanti"] = campi_mancanti(pasto, ospiti, orario)
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
    session = str(cfg.get("superb_session") or "").strip()
    restaurant_id = str(cfg.get("superb_restaurant_id") or "").strip()

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

    try:
        r = _requests.get(
            f"{_SUPERB_API}/booking/dashboard",
            params={"sort": "arrival", "q": q},
            headers=headers,
            cookies={"koa:sess": session},
            timeout=10,
        )
    except _requests.Timeout as e:
        raise SuperbError("Superb non ha risposto in tempo. Controlla la connessione e riprova.") from e
    except _requests.RequestException as e:
        raise SuperbError("Impossibile contattare Superb. Controlla la connessione a internet e riprova.") from e

    if r.status_code in (401, 403):
        raise SuperbError("Sessione Superb scaduta. Rinnovarla dalle Impostazioni → Configura Superb.")
    if r.status_code >= 400:
        raise SuperbError(f"Superb ha risposto con un errore (codice {r.status_code}). Riprova più tardi.")

    try:
        data = r.json()
    except ValueError as e:
        raise SuperbError("Superb ha restituito una risposta non leggibile. Riprova più tardi.") from e
    if not isinstance(data, dict) or not data.get("success"):
        # Non si mostra il contenuto della risposta: può contenere dati dei clienti.
        dettaglio = data.get("message") if isinstance(data, dict) else None
        raise SuperbError("Superb ha risposto con errore" + (f": {dettaglio}" if dettaglio else "."))

    items = data.get("data", [])
    if not isinstance(items, list):
        raise SuperbError("Superb ha restituito le prenotazioni in un formato inatteso.")
    return [x for x in items if isinstance(x, dict)]


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
        rec["_mancanti"]           = campi_mancanti(pasto, rec.get("ospiti"), rec.get("orario"))
        rec["giorno"]              = giorno
        rec["data_servizio_label"] = format_data_label(svc_date) or ""
        rec["_colonne"]            = colonne
        enriched.append(rec)

    print(f"Superb: {len(enriched)} prenotazioni per {date_str}")
    html_path = DATA_DIR / "prenotazioni_wa.html"
    save_html(enriched, html_path)
    return enriched, str(html_path)

# ───────────────────────────────────────────────
# FINE INTEGRAZIONE SUPERB
# ───────────────────────────────────────────────

def estrai(pdf_path: Path):
    raw_text = load_file_text(Path(pdf_path))
    if not (raw_text or "").strip():
        raise ValueError("Il file è vuoto: non ci sono prenotazioni da leggere.")

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
            f"<td>{pasto}</td><td>{stato}</td><td>{giorno}</td><td>{note}</td>"
            f"<td><a target='_blank' href='{link}'>Apri chat</a></td></tr>"
        )
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
        r_out["_mancanti"] = campi_mancanti(pasto, ospiti, orario)
        r_out["giorno"] = giorno
        # Stessa etichetta italiana usata per Superb (strftime('%B') dipende dalla lingua di Windows).
        r_out["data_servizio_label"] = format_data_label(svc_date) or ""
        r_out["_colonne"] = colonne
        enriched.append(r_out)

    print("Creati messaggi/link WhatsApp")

    html_path = DATA_DIR / "prenotazioni_wa.html"
    save_html(enriched, html_path)
    print("Creato HTML")

    return enriched, str(html_path)
