"""Qualità dell'estrazione con LLM finto: la normalizzazione deve dare il 100% su ogni campo."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import qualita_estrazione as Q  # noqa: E402


def test_qualita_estrazione_llm_finto():
    res = Q.valuta(llm_vero=False)
    assert res["errori"] == [], "\n".join(res["errori"])
    assert all(p == 100.0 for p in res["percentuali"].values()), res["percentuali"]
