"""VRAM- ÉS KISZERVEZÉS-MÉRÉS — belefér-e a modell a kártyába, vagy
csendben a CPU dolgozik helyette.

```
python -m tools.vram_meres --modell qwen3.5:9b
python -m tools.vram_meres --modell qwen3.5:9b --num-ctx 65536
python -m tools.vram_meres --modell gemma3:12b --num-ctx 8192
```

**Miért kell külön eszköz.** A kiszervezés (offload) a legalattomosabb
üzemzavar: a rendszer MŰKÖDIK, a válaszok értelmesek, csak lassabbak — és
a szakirodalom szerint a részlegesen CPU-n futó modell a STRUKTURÁLT
kimenetet is rosszabbul adja, nem csak lassabban. A golden set
pontszáma ilyenkor romlik, és a mérés a modellre fogja, ami valójában a
memóriakezelésé.

Amit mér, három forrásból, mert egyik sem elég önmagában:

1. **`/api/ps`** — a betöltött modell mérete és abból mennyi van a
   VRAM-ban (`size` vs `size_vram`), plusz a TÉNYLEGESEN használt
   kontextusméret (`context_length`). Ez mondja meg, hogy a
   kért `num_ctx` egyáltalán érvényre jutott-e.
2. **`nvidia-smi`** — a kártya foglaltsága kívülről nézve, futás
   KÖZBEN. Az Ollama saját száma nem tartalmazza a többi folyamatot (és
   a képernyőt sem), a VRAM-verseny viszont attól még valódi.
3. **Válaszidő** — a kiszervezés legdrágább tünete. Egy azonos, rövid
   kérést futtatunk többször, és a p50-et nézzük.

**A `size == size_vram` a jó eset**: minden a GPU-n van. Ha a
`size_vram` kisebb, a különbség a CPU-n fut (az `ollama ps` ezt
`PROCESSOR` oszlopban `xx%/yy% CPU/GPU` alakban mutatja).
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

GYOKER = Path(__file__).resolve().parents[1]
if str(GYOKER) not in sys.path:
    sys.path.insert(0, str(GYOKER))

_ALAP_URL = "http://localhost:11434"

# Rövid, de VALÓDI kérés: séma-kényszerítéssel, mert a strukturált
# kimenet a kérdés tárgya. Egy csupasz "szia" gyorsabb lenne, és mást
# mérne.
_PROBA_MONDAT = "Szeretnék időpontot foglalni szerdára az Ügyifogyiba."


def _api(ut: str, adat: dict | None = None, url: str = _ALAP_URL, timeout: float = 180.0):
    keres = urllib.request.Request(
        f"{url}{ut}",
        data=None if adat is None else json.dumps(adat).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="GET" if adat is None else "POST",
    )
    try:
        with urllib.request.urlopen(keres, timeout=timeout) as valasz:
            return json.loads(valasz.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        print(f"  (az Ollama nem válaszolt: {exc})")
        return None


def nvidia_smi() -> dict | None:
    """A kártya neve és memóriája MB-ban, vagy `None`, ha nincs
    `nvidia-smi` (más gyártó, integrált GPU, CPU-s gép)."""
    if shutil.which("nvidia-smi") is None:
        return None
    parancs = [
        "nvidia-smi",
        "--query-gpu=name,memory.total,memory.used",
        "--format=csv,noheader,nounits",
    ]
    try:
        kimenet = subprocess.run(parancs, capture_output=True, text=True, timeout=15).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    sor = kimenet.strip().splitlines()[0].split(", ")
    if len(sor) < 3:
        return None
    return {"nev": sor[0], "osszes_mb": int(sor[1]), "hasznalt_mb": int(sor[2])}


def betoltott_modell(modell: str, url: str = _ALAP_URL) -> dict | None:
    valasz = _api("/api/ps", url=url)
    for adat in (valasz or {}).get("models") or []:
        if adat.get("name", "").startswith(modell.removesuffix(":latest")):
            return adat
    return None


def kiszervezes(adat: dict | None) -> tuple[float, str]:
    """`(GPU-arány, olvasható címke)`. A `size` a teljes betöltött
    méret, a `size_vram` az, ami ebből a kártyán van — a különbség fut a
    CPU-n."""
    if not adat or not adat.get("size"):
        return (0.0, "nincs betöltve")
    arany = (adat.get("size_vram") or 0) / adat["size"]
    if arany >= 0.999:
        return (arany, "100% GPU")
    return (arany, f"{arany:.0%} GPU / {1 - arany:.0%} CPU — KISZERVEZÉS")


def egy_hivas(modell: str, num_ctx: int, url: str = _ALAP_URL) -> tuple[float, int, int] | None:
    """`(másodperc, prompt_token, valasz_token)` egy valódi,
    séma-kényszerített hívásból."""
    payload = {
        "model": modell,
        "messages": [{"role": "user", "content": _PROBA_MONDAT}],
        "format": {
            "type": "object",
            "properties": {"bolt": {"type": "string"}, "nap": {"type": "string"}},
            "required": ["bolt", "nap"],
        },
        "stream": False,
        "think": False,
        "options": {"temperature": 0, "num_ctx": num_ctx},
    }
    kezdet = time.monotonic()
    valasz = _api("/api/chat", payload, url=url)
    if valasz is None:
        return None
    return (
        time.monotonic() - kezdet,
        int(valasz.get("prompt_eval_count") or 0),
        int(valasz.get("eval_count") or 0),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="VRAM- és kiszervezés-mérés egy modellre.")
    parser.add_argument("--modell", required=True, help="Ollama modellnév")
    parser.add_argument("--num-ctx", type=int, default=8192, help="kért kontextusméret")
    parser.add_argument("--ismetles", type=int, default=3, help="hány hívás")
    parser.add_argument("--url", default=_ALAP_URL)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args(argv)

    gpu = nvidia_smi()
    print(
        f"GPU: {gpu['nev']} — {gpu['hasznalt_mb']}/{gpu['osszes_mb']} MB foglalt (mérés előtt)"
        if gpu
        else "GPU: nincs nvidia-smi (más gyártó vagy CPU-s gép)"
    )
    print(f"Modell: {args.modell}, kért num_ctx: {args.num_ctx}\n")

    idok: list[float] = []
    for i in range(args.ismetles):
        eredmeny = egy_hivas(args.modell, args.num_ctx, args.url)
        if eredmeny is None:
            return 1
        masodperc, prompt_token, valasz_token = eredmeny
        idok.append(masodperc)
        # A MÁSODIK hívástól mérünk „melegen": az elsőbe beleszámít a
        # modell betöltése, ami nem a kontextusméretről szól.
        cimke = " (hideg — betöltéssel)" if i == 0 else ""
        print(
            f"  {i + 1}. hívás: {masodperc:5.2f} s   prompt {prompt_token} token, "
            f"válasz {valasz_token} token{cimke}"
        )

    adat = betoltott_modell(args.modell, args.url)
    arany, cimke = kiszervezes(adat)
    gpu_utana = nvidia_smi()
    meleg = idok[1:] or idok

    print()
    if adat:
        meret_mb = adat["size"] / 2**20
        vram_mb = adat.get("size_vram", 0) / 2**20
        print(f"Betöltve:      {meret_mb:.0f} MB, ebből VRAM {vram_mb:.0f} MB")
        print(f"Kiszervezés:   {cimke}")
        print(f"Tényleges kontextus: {adat.get('context_length')} (kért: {args.num_ctx})")
    if gpu_utana:
        print(
            f"GPU foglaltság: {gpu_utana['hasznalt_mb']}/{gpu_utana['osszes_mb']} MB (mérés után)"
        )
    atlag = sum(meleg) / len(meleg)
    print(f"Válaszidő (meleg): {atlag:.2f} s átlag, {min(meleg):.2f}–{max(meleg):.2f} s")

    if adat and adat.get("context_length") not in (None, args.num_ctx):
        print(
            "\nFIGYELEM: a tényleges kontextus NEM egyezik a kérttel — a szolgáltató "
            "felülbírálta (l. OLLAMA_CONTEXT_LENGTH vagy a modell Modelfile-ja)."
        )
    if arany < 0.999 and adat:
        print(
            "\nFIGYELEM: a modell egy része a CPU-n fut. A válaszidő ettől nő, és a "
            "strukturált kimenet megbízhatósága is romolhat — ilyen állapotban mért "
            "pontosság nem a modellről szól."
        )

    if args.json:
        args.json.write_text(
            json.dumps(
                {
                    "modell": args.modell,
                    "kert_num_ctx": args.num_ctx,
                    "tenyleges_kontextus": (adat or {}).get("context_length"),
                    "meret_byte": (adat or {}).get("size"),
                    "vram_byte": (adat or {}).get("size_vram"),
                    "gpu_arany": arany,
                    "idok": idok,
                    "gpu": gpu_utana,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"\nJSON mentve: {args.json}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
