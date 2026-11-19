# main.py
from pathlib import Path
from datetime import date, datetime
import webview
from tkinter.filedialog import askopenfilename
import json
import webbrowser
import logicaBE
from logicaBE import (load_template, load_config, save_config, CONFIG_DIR, TEMPLATE_FILE,
                      check_license, save_license_token)
import base64
import sys
import subprocess
import os
import winreg
from urllib.parse import quote
class Api:

    def __init__(self):
        self.last_html_path: Path | None = None
        self.last_loaded_file: Path | None = None

    def apri_file_caricato(self) -> dict:
        try:
            if not self.last_loaded_file or not self.last_loaded_file.exists():
                return {"ok": False, "error": "Nessun file caricato"}

            os.startfile(str(self.last_loaded_file))
            return {"ok": True}

        except Exception as e:
            return {"ok": False, "error": str(e)}

    def apri_whatsapp_app(self, phone: str, messaggio: str) -> dict:
        phone_clean = phone.replace("+", "").replace(" ", "")
        testo_encoded = quote(messaggio, safe="")
        uri = f"whatsapp://send?phone={phone_clean}&text={testo_encoded}"

        try:
            if sys.platform == "win32":
                # controlla se il protocollo whatsapp:// è registrato nel registro
                wa_installato = False
                try:
                    with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "whatsapp"):
                        wa_installato = True
                except FileNotFoundError:
                    wa_installato = False

                if wa_installato:
                    os.startfile(uri)
                    return {"ok": True}
                else:
                    return {"ok": False, "reason": "not_installed"}

            elif sys.platform == "darwin":
                subprocess.Popen(["open", uri])
                return {"ok": True}
            else:
                subprocess.Popen(["xdg-open", uri])
                return {"ok": True}

        except Exception as e:
            print(f"Errore apertura WhatsApp app: {e}")
            return {"ok": False, "error": str(e)}

    def ricalcola_messaggi(self, data_json: str):
        try:
            records = json.loads(data_json or "[]")
        except Exception as e:
            print("Errore parsing JSON in ricalcola_messaggi:", e)
            return []

        enriched = logicaBE.recompute_records(records)
        return enriched

    def set_api_key(self, key: str) -> str:
        key = (key or "").strip()
        cfg = load_config()
        cfg["api_key_encrypted"] = base64.b64encode(key.encode()).decode()
        save_config(cfg)
        logicaBE.reset_client()   # ← aggiunta
        return "Chiave salvata correttamente. Riavviare l'app"

    def get_template(self) -> str:
        return load_template()

    def set_runtime_template(self, text: str) -> str:
        logicaBE.set_runtime_template(text)
        return "Template di sessione aggiornato."

    def reset_template(self) -> str:
        if TEMPLATE_FILE.exists():
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup = TEMPLATE_FILE.with_name(f"template_backup_{ts}.txt")
            TEMPLATE_FILE.replace(backup)
        return "Template ripristinato al default."

    def set_superb_session(self, session: str, restaurant_id: str) -> dict:
        session       = (session or "").strip()
        restaurant_id = (restaurant_id or "").strip()
        if not session:
            return {"ok": False, "error": "Sessione vuota."}
        cfg = load_config()
        cfg["superb_session"]       = session
        if restaurant_id:
            cfg["superb_restaurant_id"] = restaurant_id
        save_config(cfg)
        return {"ok": True}

    def get_superb_config(self) -> dict:
        cfg = load_config()
        return {
            "has_session":   bool(cfg.get("superb_session", "").strip()),
            "restaurant_id": cfg.get("superb_restaurant_id", ""),
        }

    def processa_superb(self, date_str: str, giorno: str | None = None) -> list:
        enriched, html_path = logicaBE.main_superb(date_str, giorno or None)
        self.last_html_path = Path(html_path)
        return enriched

    def insert_license(self, token: str) -> dict:
        ok, result = save_license_token(token.strip())
        if ok:
            return {"ok": True, "expires": result}
        return {"ok": False, "error": result}

    def get_license_status(self) -> dict:
        cfg = load_config()
        token = cfg.get("license_token", "")
        expires = cfg.get("license_expires", "")
        if not token:
            return {"has_license": False, "expires": ""}
        return {"has_license": True, "expires": expires}

    def set_template(self, text: str) -> str:
        text = (text or "").strip()
        if not text:
            return "Template vuoto: nessuna modifica applicata."

        CONFIG_DIR.mkdir(parents=True, exist_ok=True)

        # backup se esiste template corrente
        if TEMPLATE_FILE.exists():
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup = TEMPLATE_FILE.with_name(f"template_{ts}.bak.txt")
            TEMPLATE_FILE.replace(backup)

        TEMPLATE_FILE.write_text(text, encoding="utf-8")
        return "Template aggiornato."
    def scegli_file(self) -> str:
        path = askopenfilename(
            title="Seleziona file",
            filetypes=[
                ("Tutti i formati supportati", "*.pdf *.jpg *.jpeg *.png *.csv *.txt"),
                ("PDF", "*.pdf"),
                ("Immagini", "*.jpg *.jpeg *.png"),
                ("CSV", "*.csv"),
                ("Testo", "*.txt"),
            ]
        )
        return path or ""

    def processa_pdf(self, pdf_path: str, giorno: str | None = None):
        pdf = Path(pdf_path)
        self.last_loaded_file = pdf
        if not pdf.exists():
            raise FileNotFoundError(f"PDF non trovato: {pdf}")

        if not giorno:
            giorno = None

        enriched, html_path = logicaBE.main(
            pdf_path=str(pdf),
            svc_date=None,
            giorno_override=giorno
        )
        self.last_html_path = Path(html_path)
        return enriched

    def esporta_html(self, data_json: str | None = None) -> str:
        if data_json:
            try:
                records = json.loads(data_json)
            except Exception as e:
                print("Errore nel parsing del JSON da frontend:", e)
                return "Errore: dati non validi dalla GUI (JSON malformato)."

            # Se non abbiamo ancora un path, creiamo un nome di default
            if self.last_html_path is None:
                self.last_html_path = Path("prenotazioni_wa.html")

            logicaBE.save_html(records, self.last_html_path)
            webbrowser.open(self.last_html_path.as_uri())
            return f"HTML aggiornato e aperto: {self.last_html_path}"

        # Fallback: nessun JSON passato → prova ad aprire l’ultimo HTML generato
        if not self.last_html_path or not self.last_html_path.exists():
            return "Nessun file HTML generato da esportare."

        webbrowser.open(self.last_html_path.as_uri())
        return f"HTML aperto: {self.last_html_path}"

def get_html_path() -> Path:
    if hasattr(sys, "_MEIPASS"):
        base = Path(sys._MEIPASS)  # cartella temporanea usata da PyInstaller --onefile
    else:
        base = Path(__file__).resolve().parent
    return base / "assets" / "index.html"

def start():
    api = Api()
    screen = webview.screens[0]
    width = int(screen.width * 0.7)
    height = int(screen.height * 0.7)
    x = int(screen.width * 0.15)
    y = int(screen.height * 0.15)

    html_path = get_html_path()

    # ── Controllo licenza all'avvio ──
    ok, msg = check_license()
    if not ok:
        # Mostra finestra di attivazione invece dell'app principale
        license_html = get_html_path().parent / "license.html"
        webview.create_window(
            title="Attivazione licenza",
            url=str(license_html),
            js_api=api,
            width=480,
            height=340,
            resizable=False
        )
        webview.start()
        return
    # ── Fine controllo licenza ──

    webview.create_window(
        title="Cascina Nascosta - Prenotazioni",
        url=str(html_path),
        js_api=api,
        width=width,
        height=height,
        x=x,
        y=y,
        resizable=True
    )

    webview.start()



if __name__ == "__main__":
    start()
