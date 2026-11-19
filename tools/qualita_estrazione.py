"""
Qualità dell'estrazione: confronta campo per campo il risultato con quello atteso.

  python tools/qualita_estrazione.py                 # LLM FINTO (default): misura la normalizzazione
  python tools/qualita_estrazione.py --llm-vero --conferma   # LLM VERO: costa e invia i file FINTI a OpenAI.
                                                             # Da lanciare SOLO se il titolare lo chiede.

Va rieseguito a ogni modifica dei prompt (definizioni_llm.py) o della normalizzazione.
I file di prova sono generati in una cartella temporanea; la config è sempre una copia temporanea.
"""
import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
CASI = ROOT / "tests" / "fixtures" / "estrazione" / "casi.json"
CAMPI = ("nome", "telefono", "orario", "ospiti", "pasto")


def genera_file(caso: dict, cartella: Path) -> Path:
    fmt = caso["formato"]
    p = cartella / f"{caso['id']}.{fmt}"
    testo = "\n".join(caso["righe"])
    if fmt in ("txt", "csv"):
        p.write_text(testo + "\n", encoding="utf-8")
    elif fmt == "pdf":
        import pymupdf as fitz
        doc = fitz.open()
        page = doc.new_page()
        for i, riga in enumerate(caso["righe"]):
            page.insert_text((50, 60 + i * 18), riga, fontname="cour", fontsize=10)
        doc.save(str(p))
        doc.close()
    elif fmt == "png":
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (640, 40 + 28 * len(caso["righe"])), "white")
        d = ImageDraw.Draw(img)
        for i, riga in enumerate(caso["righe"]):
            d.text((20, 20 + i * 28), riga, fill="black")
        img.save(p)
    else:
        raise ValueError(fmt)
    return p


class _LLMFinto:
    def __init__(self, risposte):
        self._r = list(risposte)
        self.chat = SimpleNamespace(completions=self)

    def create(self, **_kw):
        msg = SimpleNamespace(content=self._r.pop(0))
        return SimpleNamespace(choices=[SimpleNamespace(message=msg, finish_reason="stop")])


def _isola_config(L, tmp: Path) -> None:
    cfg = tmp / "config"
    cfg.mkdir()
    for name in ("template.txt", "template_default.txt"):
        shutil.copy2(ROOT / "installer_files" / "config" / name, cfg / name)
    L.BASE_DIR = tmp
    L.CONFIG_DIR = cfg
    L.CONFIG_FILE = cfg / "config.json"
    L.TEMPLATE_FILE = cfg / "template.txt"
    L.DEFAULT_TEMPLATE_FILE = cfg / "template_default.txt"
    L.get_base_dir = lambda: tmp


def valuta(llm_vero: bool = False, chiave_api: str | None = None) -> dict:
    import logicaBE as L
    casi = json.loads(CASI.read_text(encoding="utf-8"))["casi"]
    tmp = Path(tempfile.mkdtemp(prefix="qualita_estrazione_"))
    _isola_config(L, tmp)
    if llm_vero:
        L.update_config({"api_key_encrypted": __import__("base64").b64encode(chiave_api.encode()).decode()})
        L.reset_client()

    giusti = {c: 0 for c in CAMPI + ("data_servizio", "numero_prenotazioni")}
    totali = {c: 0 for c in giusti}
    errori = []
    for caso in casi:
        f = genera_file(caso, tmp)
        if not llm_vero:
            risposte = ([caso["llm_testo_immagine"]] if caso["formato"] == "png" else []) + \
                       [json.dumps(caso["llm_simulato"])]
            L.client = _LLMFinto(risposte)
        try:
            out, _ = L.main(str(f))
        except Exception as e:  # un caso che fallisce conta come tutto sbagliato
            errori.append(f"{caso['id']}: ERRORE {type(e).__name__}: {e}")
            out = []
        att = caso["atteso"]["prenotazioni"]
        totali["numero_prenotazioni"] += 1
        if len(out) == len(att):
            giusti["numero_prenotazioni"] += 1
        else:
            errori.append(f"{caso['id']}: {len(out)} prenotazioni invece di {len(att)}")
        totali["data_servizio"] += 1
        ds = out[0].get("data_servizio") if out else None
        if ds == caso["atteso"]["data_servizio"]:
            giusti["data_servizio"] += 1
        else:
            errori.append(f"{caso['id']}: data_servizio {ds!r} invece di {caso['atteso']['data_servizio']!r}")
        for i, a in enumerate(att):
            r = out[i] if i < len(out) else {}
            for c in CAMPI:
                totali[c] += 1
                v = r.get(c)
                v = "" if v is None else str(v)
                if v == ("" if a[c] is None else str(a[c])):
                    giusti[c] += 1
                else:
                    errori.append(f"{caso['id']}[{i}].{c}: {v!r} invece di {a[c]!r}")
    shutil.rmtree(tmp, ignore_errors=True)
    perc = {c: round(100 * giusti[c] / totali[c], 1) if totali[c] else 100.0 for c in giusti}
    return {"percentuali": perc, "errori": errori, "casi": len(casi)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm-vero", action="store_true")
    ap.add_argument("--conferma", action="store_true", help="obbligatorio con --llm-vero")
    ap.add_argument("--chiave", help="chiave OpenAI da usare (solo con --llm-vero)")
    a = ap.parse_args()
    if a.llm_vero and not (a.conferma and a.chiave):
        sys.exit("Con --llm-vero servono --conferma e --chiave: costa e invia i file di prova a OpenAI.")
    res = valuta(a.llm_vero, a.chiave)
    print(f"Casi: {res['casi']}  ({'LLM VERO' if a.llm_vero else 'LLM finto'})")
    for campo, p in res["percentuali"].items():
        print(f"  {campo:<22} {p:6.1f}%")
    if res["errori"]:
        print("\nDifferenze:")
        for e in res["errori"]:
            print("  - " + e)
    sys.exit(0 if not res["errori"] else 1)


if __name__ == "__main__":
    main()
