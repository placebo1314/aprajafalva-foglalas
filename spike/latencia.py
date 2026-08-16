"""Válaszidő és tokenizer-hatékonyság mérése — M-1 spike. ELDOBHATÓ KÓD.

1 és 3 párhuzamos kéréssel méri a p50/p95 válaszidőt, és a kimeneti
tokenszámot magyar mondatonként (ez a tokenizer-hatékonyság mérőszáma —
kevesebb token/mondat = gyorsabb, olcsóbb inferencia ugyanahhoz a
tartalomhoz). A VRAM-ot `nvidia-smi`-vel figyeli a futás alatt.

Használat:
    python spike/latencia.py --modell qwen3.5:9b
"""

from __future__ import annotations

import argparse
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

GYOKER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GYOKER))

from spike.golden_futtato import betolt, modell_hivas  # noqa: E402

_SZALSZAMOK = (1, 3)


def _vram_mb() -> int | None:
    try:
        ki = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return int(ki.stdout.strip().splitlines()[0])
    except Exception:  # noqa: BLE001 - a VRAM-mérés opcionális, nem szabad elakasztania a mérést
        return None


def _p(idok: list[float], szazalek: float) -> float:
    if not idok:
        return 0.0
    rendezve = sorted(idok)
    idx = min(int(len(rendezve) * szazalek), len(rendezve) - 1)
    return rendezve[idx]


def _egy_kor(modell: str, mondatok: list[str], most: str, szalszam: int, gondolkodas: bool) -> dict:
    idok: list[float] = []
    tokenek: list[int] = []
    hibak: list[str] = []
    zar = threading.Lock()

    def _feladat(mondat: str) -> None:
        _kimenet, telt, tokenszam, hiba = modell_hivas(
            modell, mondat, most, gondolkodas=gondolkodas
        )
        with zar:
            idok.append(telt)
            if tokenszam:
                tokenek.append(tokenszam)
            if hiba:
                hibak.append(hiba)

    vram_elotte = _vram_mb()
    kezdet = time.monotonic()

    if szalszam == 1:
        for mondat in mondatok:
            _feladat(mondat)
    else:
        # szalszam-anyi "hullám": a mondatokat szalszam-as csoportokban
        # indítjuk egyszerre, hogy a GPU-n ténylegesen szalszam kérés fusson
        # párhuzamosan (nem csak szalszam szál, ami egyesével sorba áll).
        for i in range(0, len(mondatok), szalszam):
            csoport = mondatok[i : i + szalszam]
            szalak = [threading.Thread(target=_feladat, args=(m,)) for m in csoport]
            for szal in szalak:
                szal.start()
            for szal in szalak:
                szal.join(timeout=180)

    teljes_ido = time.monotonic() - kezdet
    vram_alatt = _vram_mb()

    tokenszam_mondatonkent = statistics.mean(tokenek) if tokenek else None

    return {
        "szalszam": szalszam,
        "n": len(idok),
        "p50_s": _p(idok, 0.5),
        "p95_s": _p(idok, 0.95),
        "atlag_s": statistics.mean(idok) if idok else 0.0,
        "teljes_ido_s": teljes_ido,
        "atlagos_token_per_mondat": tokenszam_mondatonkent,
        "vram_mb_elotte": vram_elotte,
        "vram_mb_alatt": vram_alatt,
        "hibaszam": len(hibak),
    }


def fut(modell: str, gondolkodas: bool = True) -> list[dict]:
    meta, esetek = betolt()
    mondatok = [e.bemenet for e in esetek]
    most = meta["most_alapertelmezett"]

    eredmenyek = []
    for szalszam in _SZALSZAMOK:
        print(f"\n--- {modell}, {szalszam} párhuzamos kérés ---")
        eredmeny = _egy_kor(modell, mondatok, most, szalszam, gondolkodas)
        eredmenyek.append(eredmeny)
        print(
            f"  n={eredmeny['n']}  p50={eredmeny['p50_s']:.2f}s  p95={eredmeny['p95_s']:.2f}s  "
            f"átlag token/mondat={eredmeny['atlagos_token_per_mondat']}"
        )
        print(
            f"  VRAM előtte={eredmeny['vram_mb_elotte']} MiB, "
            f"alatta={eredmeny['vram_mb_alatt']} MiB"
        )
        if eredmeny["hibaszam"]:
            print(f"  HIBÁK: {eredmeny['hibaszam']}")
    return eredmenyek


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--modell", required=True)
    parser.add_argument("--json", type=Path, default=None, help="Eredmény mentése JSON-ba")
    parser.add_argument(
        "--nincs-gondolkodas",
        action="store_true",
        help="Ollama think=false — lásd golden_futtato.py azonos kapcsolóját",
    )
    args = parser.parse_args()
    eredmenyek = fut(args.modell, gondolkodas=not args.nincs_gondolkodas)
    if args.json:
        import json

        args.json.write_text(
            json.dumps({"modell": args.modell, "korok": eredmenyek}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\nJSON mentve: {args.json}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
