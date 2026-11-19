"""
Prova con la finestra pywebview VERA (WebView2) della conferma alla chiusura.
Tutto il mondo esterno è finto (stessi mock di server_verifica.py), config temporanea.
Simula il clic sulla X inviando WM_CLOSE alla finestra.

  .venv\\Scripts\\python tools\\prova_chiusura_reale.py

Apre una finestra sullo schermo per ~15 secondi. Esce con 0 se tutto è come atteso.
"""
import ctypes
import os
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import server_verifica as SV  # noqa: E402  (applica tutti i finti e la config temporanea)
import webview  # noqa: E402

TITOLO = "PROVA-CHIUSURA-PrenotazioniCN"
user32 = ctypes.windll.user32
user32.FindWindowW.restype = ctypes.c_void_p
WM_CLOSE = 0x0010

# pywebview espone solo i metodi della CLASSE: il finto va messo lì (mai la finestra file vera)
SV.M.Api.scegli_file = lambda self: str(SV.FILE_PRENOTAZIONI)
api = SV.M.Api()
win = webview.create_window(TITOLO, url=str(ROOT / "assets" / "index.html"), js_api=api, width=1100, height=700)
api._window = win
win.events.closing += api._on_closing
esiti = {}


def _hwnd():
    return user32.FindWindowW(None, TITOLO)


def _aperta(h):
    return bool(h) and bool(user32.IsWindow(ctypes.c_void_p(h)))


def _x(h):
    user32.PostMessageW(ctypes.c_void_p(h), WM_CLOSE, 0, 0)


def scenario():
    try:
        win.events.loaded.wait(20)
        time.sleep(2)
        win.evaluate_js("document.getElementById('btnLoad').click()")
        time.sleep(0.7)
        win.evaluate_js("document.getElementById('btnProcess').click()")
        time.sleep(2)
        esiti["righe caricate"] = win.evaluate_js("document.querySelectorAll('#output tbody tr').length")
        h = _hwnd()

        # 1) senza modifiche nessuna domanda: lo verifichiamo solo sul backend (non chiudiamo)
        esiti["sporca prima della modifica"] = api._dirty
        win.evaluate_js("(() => { const i = document.querySelector('#output tbody tr input');"
                        " i.value = 'Prova Modifica'; i.dispatchEvent(new Event('change')); return 1; })()")
        time.sleep(1)
        esiti["sporca dopo la modifica"] = api._dirty

        # 2) X → resta aperta e chiede conferma con il kit dell'app
        _x(h)
        time.sleep(1.5)
        esiti["aperta dopo la X"] = _aperta(h)
        esiti["titolo conferma"] = win.evaluate_js(
            "(document.querySelector('.confirm-backdrop h2') || {}).textContent || ''")
        esiti["fuoco su"] = win.evaluate_js("document.activeElement ? document.activeElement.textContent : ''")

        # 3) Annulla → resta aperta, dati intatti
        win.evaluate_js("document.querySelector('.confirm-backdrop .btn-modal-cancel').click()")
        time.sleep(0.8)
        esiti["aperta dopo Annulla"] = _aperta(h)
        esiti["modifica conservata"] = win.evaluate_js("currentData[0].nome")

        # 4) X di nuovo → Chiudi senza salvare → chiusa davvero
        _x(h)
        time.sleep(1.5)
        esiti["_hwnd"] = h
        # run_js non aspetta la risposta: la finestra si chiude proprio durante questo clic
        win.run_js("document.querySelector('.confirm-backdrop .btn-modal-danger').click()")
    except Exception as e:  # la prova non deve mai lasciare la finestra aperta
        esiti["errore"] = repr(e)
    finally:
        time.sleep(5)
        if _aperta(_hwnd()):   # la prova non lascia mai la finestra aperta
            esiti["chiusa dopo conferma"] = False
            api._close_ok = True
            win.destroy()


def guardiano():
    time.sleep(60)
    os._exit(3)   # mai una finestra appesa sullo schermo


threading.Thread(target=scenario, daemon=True).start()
threading.Thread(target=guardiano, daemon=True).start()
webview.start()
# webview.start() torna solo quando la finestra è chiusa
if "chiusa dopo conferma" not in esiti and "_hwnd" in esiti:
    esiti["chiusa dopo conferma"] = not _aperta(esiti["_hwnd"])

ATTESI = {
    "righe caricate": 5,
    "sporca prima della modifica": False,
    "sporca dopo la modifica": True,
    "aperta dopo la X": True,
    "titolo conferma": "Chiudere PrenotazioniCN?",
    "fuoco su": "Annulla",
    "aperta dopo Annulla": True,
    "modifica conservata": "Prova Modifica",
    "chiusa dopo conferma": True,
}
ok = True
for k, v in ATTESI.items():
    got = esiti.get(k)
    stato = "ok " if got == v else "NO "
    ok &= got == v
    print(f"{stato} {k}: {got!r}" + ("" if got == v else f"  (atteso {v!r})"))
if "errore" in esiti:
    ok = False
    print("ERRORE:", esiti["errore"])
sys.exit(0 if ok else 1)
