"""BESZÉLGETÉS-ELEMZŐ — a próba-naplóból (`naplo/probak.jsonl`) egyetlen,
offline megnyitható HTML fájl.

    python feladat.py riport
    python feladat.py riport --utolso 20
    python feladat.py riport --ki naplo/riport.html --megnyit

## Miért HTML, és miért egyetlen fájl

A `python feladat.py naplo` ÖSSZESÍT (számok, eloszlások, hibaminták);
ez a jelentés a másik irányba megy: **egy fordulót mutat meg teljes
mélységben**. A kettő nem helyettesíti egymást — az összesítés
megmondja, hogy valami baj van, ez megmondja, hogy MI.

Egyetlen fájl, keretrendszer nélkül:

- **offline megnyitható** — nincs szerver, nincs CDN, nincs build;
  átmásolható, elküldhető, mellékelhető egy hibajegyhez;
- **nincs függősége** — a projektnek amúgy sincs webes függősége, és egy
  jelentésért nem érdemes elsőt bevezetni (`docs/KOMPONENSEK.md`,
  „Amit szándékosan magunk írunk");
- **a `<details>` elem natívan összecsukható**, JavaScript nélkül. A
  hosszú részek (prompt, nyers válasz) alapból csukva vannak, mert
  fordulónként több ezer karakterről van szó.

## Amit MUTAT, és miért pont azt

Fordulónként, egy blokkban:

| Rész | Mire felel |
|---|---|
| bemenet ↔ normalizált alak | mit LÁTOTT a rendszer abból, amit beírtak |
| réteg (színkóddal) | ki döntött: kapuőr, szabály, modell, orchestrator-rövidzár |
| modell, hívásszám, önkonzisztencia | hányszor kérdeztük meg, egyetértett-e magával |
| a teljes prompt | mit kapott ténylegesen — a leggyakoribb „miért ezt csinálta" válasza |
| nyers modellválasz + séma-ellenőrzés | a modell szava, mielőtt a kapuk hozzányúltak |
| eszköz és paraméterek, forrással | HONNAN jött az érték: modell, parser, zárt halmaz |
| dátumfeloldás | mit adott a modell, mit a parser, melyik nyert |
| lépésenkénti idő | hol telt el a válaszidő |
| a kimenő válasz MINDKÉT módban | ugyanaz a döntés, szövegesen és felolvasva |

**A napló már redaktált** (`privacy/redakcio`), tehát ez a jelentés is
az: nyers telefonszám, TAJ vagy e-mail nem kerülhet bele, mert oda sem
került, ahonnan olvassuk.
"""

from __future__ import annotations

import argparse
import html
import json
import sys
import webbrowser
from pathlib import Path

GYOKER = Path(__file__).resolve().parents[1]
if str(GYOKER) not in sys.path:
    sys.path.insert(0, str(GYOKER))

from tools.naplo_elemzo import elemez, tendencia_szoveg  # noqa: E402

ALAP_KIMENET = GYOKER / "naplo" / "riport.html"

# RÉTEG → szín. A színkód nem díszítés: a réteg az első kérdés, amit egy
# furcsa válasznál felteszünk, és három-négy fordulónyi görgetés után a
# szem gyorsabban találja meg a színt, mint a szót.
#
# A `szabaly:tartalek` szándékosan RIASZTÓ színt kap: az az egyetlen
# réteg, ami elromlott állapotot jelezhet (elhalt Ollama), a többi
# tervezett út.
_RETEG_SZIN = {
    "llm": ("#e8f0fe", "#1a4b8c"),
    "kapuor": ("#eef7ea", "#2f6b2f"),
    "szabaly:zart_valasz": ("#f3eefc", "#5b3c88"),
    "szabaly:tenyvalasz": ("#f3eefc", "#5b3c88"),
    "szabaly:tartalek": ("#fdecea", "#a3271b"),
    "orchestrator:sorszam": ("#fff6d9", "#7a5c00"),
}
_RETEG_ALAP = ("#eeeeee", "#444444")

_STILUS = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body { font-family: system-ui, "Segoe UI", sans-serif; margin: 0; padding: 24px;
       background: #fafafa; color: #1a1a1a; line-height: 1.5; }
h1 { font-size: 22px; margin: 0 0 4px; }
.alcim { color: #666; margin-bottom: 20px; font-size: 14px; }
.osszegzes { display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 24px; }
.modell-riaszt { background: #fdecea; border: 2px solid #c0392b; color: #7b241c;
                 border-radius: 8px; padding: 12px 16px; margin-bottom: 20px;
                 font-weight: 600; }
.modell-riaszt .halk { font-weight: 400; font-size: 13px; }
.kartya { background: #fff; border: 1px solid #e0e0e0; border-radius: 8px;
          padding: 10px 14px; min-width: 150px; }
.kartya .cimke { font-size: 12px; color: #666; text-transform: uppercase;
                 letter-spacing: .04em; }
.kartya .ertek { font-size: 20px; font-weight: 600; }
.kartya .megjegyzes { font-size: 12px; color: #666; }
details.fordulo { background: #fff; border: 1px solid #e0e0e0; border-radius: 8px;
                  margin-bottom: 10px; }
details.fordulo > summary { padding: 10px 14px; cursor: pointer; display: flex;
                            align-items: center; gap: 10px; flex-wrap: wrap; }
details.fordulo[open] > summary { border-bottom: 1px solid #eee; }
.sorszam { color: #999; font-variant-numeric: tabular-nums; min-width: 34px; }
.bemenet { font-weight: 600; flex: 1 1 320px; }
.cimkezo { font-size: 12px; padding: 2px 8px; border-radius: 10px; white-space: nowrap; }
.ido { color: #666; font-variant-numeric: tabular-nums; font-size: 13px; }
.torzs { padding: 12px 14px; }
.parban { display: flex; gap: 14px; flex-wrap: wrap; }
.parban > div { flex: 1 1 320px; min-width: 0; }
.mezo { margin-bottom: 12px; }
.mezo > .fejlec { font-size: 12px; color: #666; text-transform: uppercase;
                  letter-spacing: .04em; margin-bottom: 3px; }
pre { background: #f4f4f6; border: 1px solid #e6e6e9; border-radius: 6px;
      padding: 8px 10px; overflow-x: auto; font-size: 12.5px; margin: 0;
      white-space: pre-wrap; word-break: break-word; }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
th, td { text-align: left; padding: 4px 8px; border-bottom: 1px solid #eee;
         vertical-align: top; }
th { color: #666; font-weight: 600; width: 34%; }
.elteres { background: #fff3cd; }
.jo { color: #2f6b2f; } .rossz { color: #a3271b; }
details.reszlet { margin-top: 6px; }
details.reszlet > summary { font-size: 13px; color: #1a4b8c; cursor: pointer; }
.lepesek { display: flex; gap: 6px; flex-wrap: wrap; font-size: 12px; }
.lepes { background: #f0f0f3; border-radius: 4px; padding: 2px 7px; }
footer { margin-top: 28px; color: #777; font-size: 12px; }
@media (prefers-color-scheme: dark) {
  body { background: #16181c; color: #e6e6e6; }
  .kartya, details.fordulo { background: #1e2126; border-color: #303540; }
  pre { background: #14161a; border-color: #303540; color: #dcdcdc; }
  th, td { border-color: #2a2e36; }
  .alcim, .kartya .cimke, .kartya .megjegyzes, .ido, th { color: #9aa0aa; }
  .elteres { background: #4a3c12; }
  .lepes { background: #262a31; }
}
"""


def _e(ertek) -> str:
    """HTML-escape. Minden beírt szöveg ezen megy át — a napló a
    vásárló mondatait tartalmazza, és egy `<script>` szó nem törheti
    el a jelentést."""
    if ertek is None:
        return ""
    return html.escape(str(ertek), quote=True)


def _json_blokk(adat) -> str:
    if adat in (None, {}, []):
        return "<pre>—</pre>"
    return f"<pre>{_e(json.dumps(adat, ensure_ascii=False, indent=2))}</pre>"


def _reteg_cimke(reteg: str | None) -> str:
    hatter, szoveg = _RETEG_SZIN.get(reteg or "", _RETEG_ALAP)
    return (
        f'<span class="cimkezo" style="background:{hatter};color:{szoveg}">'
        f"{_e(reteg or 'ismeretlen')}</span>"
    )


def _kartya(cimke: str, ertek: str, megjegyzes: str = "") -> str:
    return (
        f'<div class="kartya"><div class="cimke">{_e(cimke)}</div>'
        f'<div class="ertek">{ertek}</div>'
        f'<div class="megjegyzes">{_e(megjegyzes)}</div></div>'
    )


# A modell-rétegek neve a naplóban. A `szabaly:*` és az
# `orchestrator:*` réteg NEM modell — ha egy beszélgetésben egyetlen
# ilyen sem szerepel, akkor a jelentés nem a modellről szól.
_MODELL_RETEGEK = ("llm", "kaszkad", "forditott")


def modell_nelkul_futott(sorok: list[dict]) -> bool:
    """Volt-e EGYETLEN modell-réteg is a beszélgetésben.

    Ez a jelentés legfontosabb egy bitje: a tartalék ág csendben átveszi
    a fordulót, a válaszok értelmesek maradnak, és a számok mégis mást
    mérnek, mint amit az olvasó hisz. Háromszor fordult elő, hogy egy
    kézi próba végig tartalékágon futott, és csak utólag derült ki."""
    if not sorok:
        return False
    return not any(
        (sor.get("reteg") or "").startswith(_MODELL_RETEGEK)
        or (sor.get("nyomkovetes") or {}).get("modellhivas_db")
        for sor in sorok
    )


def modell_riasztas(sorok: list[dict]) -> str:
    """A PIROS sáv a fejlécben, ha a beszélgetés modell nélkül futott."""
    if not modell_nelkul_futott(sorok):
        return ""
    modellek = {sor.get("modell") for sor in sorok if sor.get("modell")}
    reszlet = (
        f"Konfigurált modell a naplóban: {_e(', '.join(sorted(modellek)))} — "
        "de egyetlen fordulóban sem futott modellhívás."
        if modellek
        else "A naplóban egyetlen fordulóhoz sem tartozik konfigurált modell."
    )
    return (
        '<div class="modell-riaszt">Ez a beszélgetés MODELL NÉLKÜL futott — '
        "az eredmények nem a modellt mérik, hanem a determinisztikus tartalék ágat."
        f'<div class="halk">{reszlet}</div></div>'
    )


def fejlec_osszegzes(sorok: list[dict]) -> str:
    """A jelentés fejléce — ugyanazokból a számokból, amiket a
    `python feladat.py naplo` ír ki, hogy a kettő ne mondhasson mást."""
    osszes = elemez(sorok)
    ido = osszes["valaszido"]
    tipusok = osszes["valasz_tipusok"]
    mintak = osszes["hibamintak"]

    kartyak = [
        _kartya("fordulók", str(osszes["fordulok"]), f"{osszes['elso']} – {osszes['utolso']}"),
        _kartya(
            "réteg-megoszlás",
            "<br>".join(
                f'<span style="font-size:14px">{_reteg_cimke(r)} {n}</span>'
                for r, n in sorted(osszes["retegek"].items(), key=lambda p: -p[1])
            )
            or "—",
            "",
        ),
    ]
    if ido["n"]:
        kartyak.append(
            _kartya(
                "válaszidő",
                f"p50 {ido['p50']:.2f} s / p95 {ido['p95']:.2f} s",
                tendencia_szoveg(ido["tendencia"]),
            )
        )
    kartyak.append(
        _kartya(
            "visszakérdezés",
            str(tipusok.get("visszakerdezes", 0)),
            f"ajánlat: {tipusok.get('ajanlat', 0)} · elhárítás: {tipusok.get('elutasitas', 0)}",
        )
    )
    kiut = tipusok.get("kiut", 0)
    ismetles = len(mintak.get("ismetelt_visszakerdezes", []))
    kartyak.append(
        _kartya(
            "kiút / ismétlés",
            f"{kiut} / {ismetles}",
            "0 / 0 a jó eredmény" if (kiut or ismetles) else "egyik sem szólalt meg",
        )
    )
    return f'<div class="osszegzes">{"".join(kartyak)}</div>'


def _tabla(parok: list[tuple[str, str]]) -> str:
    sorok = "".join(f"<tr><th>{_e(k)}</th><td>{v}</td></tr>" for k, v in parok if v)
    return f"<table>{sorok}</table>" if sorok else ""


def _datum_resz(nyom: dict) -> str:
    """A dátumfeloldás három adata egymás mellett — a rendszer
    legkevésbé átlátható lépése (a modell idéz, a parser old fel, és
    eltérésnél a parser nyer)."""
    datum = nyom.get("datum") or {}
    if not datum:
        return ""
    modell = datum.get("modell_datum_tol")
    parser = datum.get("parser_tol")
    elter = bool(modell and parser and modell[:10] != parser[:10])
    sorok = [
        ("a modell idézete", _e(datum.get("modell_kifejezes") or "—")),
        (
            "a modell ISO-dátuma",
            f'<span class="{"elteres" if elter else ""}">{_e(modell or "—")}</span>',
        ),
        ("a parser eredménye", _e(f"{parser or '—'} … {datum.get('parser_ig') or '—'}")),
        ("melyik nyert", f"<b>{_e(datum.get('nyertes') or '—')}</b>"),
    ]
    return f'<div class="mezo"><div class="fejlec">Dátumfeloldás</div>{_tabla(sorok)}</div>'


def _mezo_forras_resz(sor: dict, nyom: dict) -> str:
    """Paraméterek mezőnkénti forrással és bizonyossággal.

    A `title` attribútum (tooltip) mondja meg, HONNAN jött az érték —
    a modelltől, a parsertől, a zárt halmazból vagy a megőrzött
    kontextusból. Ez az a kérdés, amire a nyers napló nem felelt."""
    parameterek = sor.get("parameterek") or {}
    if not parameterek:
        return ""
    forras = nyom.get("mezo_forras") or {}
    bizonyossag = sor.get("bizonyossag") or {}
    sorok = []
    for kulcs, ertek in parameterek.items():
        honnan = forras.get(kulcs) or forras.get("datum" if kulcs.startswith("datum") else "")
        biz = bizonyossag.get(kulcs)
        cim = f"forrás: {honnan}" if honnan else "forrás: nincs jelölve"
        biz_szoveg = f" · bizonyosság {biz:.2f}" if isinstance(biz, int | float) else ""
        sorok.append(
            (
                kulcs,
                f'<span title="{_e(cim)}">{_e(ertek)}</span>'
                f'<span class="ido">{_e(biz_szoveg)}</span>'
                + (f'<div class="ido">{_e(honnan)}</div>' if honnan else ""),
            )
        )
    return f'<div class="mezo"><div class="fejlec">Paraméterek</div>{_tabla(sorok)}</div>'


def _lepesek_resz(nyom: dict) -> str:
    lepesek = nyom.get("lepesek") or []
    if not lepesek:
        return ""
    darabok = "".join(
        f'<span class="lepes">{_e(lepes["nev"])} <b>{lepes["masodperc"]:.3f} s</b></span>'
        for lepes in lepesek
    )
    return (
        '<div class="mezo"><div class="fejlec">Lépések</div>'
        f'<div class="lepesek">{darabok}</div></div>'
    )


def _modell_resz(nyom: dict) -> str:
    prompt = nyom.get("prompt") or {}
    if not prompt and not nyom.get("nyers_valasz"):
        return ""
    sema = nyom.get("sema_ok")
    sema_szoveg = (
        '<span class="jo">átment</span>'
        if sema
        else ('<span class="rossz">ELBUKOTT</span>' if sema is False else "—")
    )
    reszek = [
        _tabla(
            [
                ("modell", _e(nyom.get("modell"))),
                ("hívások száma", _e(nyom.get("modellhivas_db"))),
                ("séma-ellenőrzés", sema_szoveg),
                ("hiba", f'<span class="rossz">{_e(nyom.get("llm_hiba"))}</span>'),
                ("önkonzisztencia", _e(nyom.get("egyetertes"))),
            ]
        )
    ]
    if nyom.get("nyers_valasz"):
        reszek.append(
            '<div class="mezo"><div class="fejlec">Nyers modellválasz</div>'
            f"<pre>{_e(nyom['nyers_valasz'])}</pre></div>"
        )
    if prompt:
        reszek.append(
            "<details class='reszlet'><summary>A teljes prompt, ami a modellhez ment</summary>"
            f"<pre>{_e(prompt.get('rendszer'))}</pre>"
            "<div class='fejlec'>A beszélgetés, ahogy a modell látta</div>"
            f"<pre>{_e(prompt.get('vasarlo'))}</pre></details>"
        )
    return "".join(reszek)


def fordulo_blokk(sor: dict, sorszam: int) -> str:
    nyom = sor.get("nyomkovetes") or {}
    ido = sor.get("valaszido_masodperc")
    ido_szoveg = f"{ido:.2f} s" if isinstance(ido, int | float) else "—"
    reteg = sor.get("reteg")

    valasz_parok = [
        ("szövegesen", f"<pre>{_e(nyom.get('valasz_szovegesen') or '—')}</pre>"),
        ("beszélhetően", f"<pre>{_e(nyom.get('valasz_beszelhetoen') or '—')}</pre>"),
    ]
    valasz_resz = (
        '<div class="mezo"><div class="fejlec">A kimenő válasz — mindkét módban</div>'
        '<div class="parban">'
        + "".join(f'<div><div class="fejlec">{_e(c)}</div>{v}</div>' for c, v in valasz_parok)
        + "</div></div>"
    )

    bemenet_resz = (
        '<div class="mezo"><div class="parban">'
        f'<div><div class="fejlec">Bemenet</div><pre>{_e(sor.get("bemenet"))}</pre></div>'
        f'<div><div class="fejlec">Normalizált alak{_normalizalas_jelzo(sor)}</div>'
        f"<pre>{_e(sor.get('normalizalt') or '—')}</pre></div>"
        "</div></div>"
    )

    fejlec_parok = [
        ("eszköz", _e(sor.get("eszkoz"))),
        ("válasz típusa", _e(sor.get("valasz_tipus"))),
        ("üzenetkulcs", _e(sor.get("uzenet_kulcs"))),
        ("kapuőr", _e((nyom.get("kapuor") or {}).get("ok") or sor.get("kapuor_ok"))),
        ("rövidzár", _e(nyom.get("rovidzar"))),
        # ÁLLAPOT ÉS ÁTMENET (ADR-028) — a beszélgetés hol tartott a
        # forduló után, és hogyan jutott oda. Ez a két adat mondja meg,
        # hogy egy furcsa válasz rossz értelmezés volt-e, vagy egy jó
        # értelmezés rossz állapotban.
        ("állapot", _e(sor.get("allapot"))),
        ("átmenet", _e(sor.get("atmenet"))),
        ("prompt-verzió", _e(sor.get("prompt_verzio"))),
    ]

    return (
        '<details class="fordulo">'
        f'<summary><span class="sorszam">{sorszam}.</span>'
        f'<span class="bemenet">{_e(sor.get("bemenet"))}</span>'
        f"{_reteg_cimke(reteg)}"
        f'<span class="ido">{_e(ido_szoveg)}</span></summary>'
        f'<div class="torzs">'
        f"{bemenet_resz}"
        f"{_tabla(fejlec_parok)}"
        f"{_mezo_forras_resz(sor, nyom)}"
        f"{_datum_resz(nyom)}"
        f"{_modell_resz(nyom)}"
        f"{_lepesek_resz(nyom)}"
        f"{valasz_resz}"
        "</div></details>"
    )


def _normalizalas_jelzo(sor: dict) -> str:
    """Jelzi, ha a normalizáló ténylegesen ÁTÍRT valamit — ez az egyik
    leggyakoribb meglepetés-forrás („hónap" → „holnap")."""
    if sor.get("normalizalt") and sor.get("normalizalt") != sor.get("bemenet"):
        return ' <span class="cimkezo" style="background:#fff3cd;color:#7a5c00">átírva</span>'
    return ""


def riport(sorok: list[dict], forras: str | None = None) -> str:
    """A teljes HTML — ez a függvény tiszta (napló-sorok listája →
    szöveg), tehát fájl nélkül tesztelhető.

    `forras`: melyik naplófájlból készült. Archivált naplónál
    (`--fajl`) ez a különbség nem díszítés: két riport ugyanúgy néz ki,
    és ha nem írja ki, melyik próbasorozatot mutatja, a másikra hivatkozó
    következtetés némán rossz lesz."""
    if not sorok:
        torzs = (
            "<p>A próba-napló üres. Futtasd: <code>python feladat.py vegigjatszas</code>, "
            "vagy nyisd meg a vásárlói felületet.</p>"
        )
    else:
        torzs = (modell_riasztas(sorok) + fejlec_osszegzes(sorok)) + "".join(
            fordulo_blokk(sor, i) for i, sor in enumerate(sorok, start=1)
        )
    return (
        "<!doctype html><html lang='hu'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<title>Beszélgetés-elemző — Aprajafalva</title>"
        f"<style>{_STILUS}</style></head><body>"
        "<h1>Beszélgetés-elemző</h1>"
        "<div class='alcim'>A próba-napló fordulói, kinyitható részletekkel. "
        "A napló redaktált — nyers személyes adat nincs benne."
        + (f" Forrás: <code>{_e(forras)}</code>." if forras else "")
        + "</div>"
        f"{torzs}"
        "<footer>Készítette: <code>python feladat.py riport</code> "
        "(<code>tools/beszelgetes_riport.py</code>). "
        "Az összesítés ugyanazokból a számokból dolgozik, mint a "
        "<code>python feladat.py naplo</code>.</footer>"
        "</body></html>"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Beszélgetés-elemző HTML a próba-naplóból.")
    parser.add_argument("--utolso", type=int, default=None, help="csak az utolsó N forduló")
    parser.add_argument("--ki", type=Path, default=ALAP_KIMENET, help="a HTML fájl útvonala")
    parser.add_argument(
        "--megnyit", action="store_true", help="megnyitja az alapértelmezett böngészőben"
    )
    parser.add_argument(
        "--fajl",
        type=Path,
        default=None,
        metavar="UTVONAL",
        help=(
            "egy ARCHIVÁLT naplóból dolgozik (naplo/probak-20260831-195812.jsonl) "
            "a jelenlegi napló helyett — az archiválás (python feladat.py naplo "
            "--archival) különben elvágná a hozzáférést a régi fordulókhoz"
        ),
    )
    args = parser.parse_args(argv)

    from ui.vasarlo import PROBA_NAPLO_UTVONAL, proba_naplo_archivumok, proba_naplo_olvas

    if args.fajl is not None and not args.fajl.exists():
        print(f"Nincs ilyen naplófájl: {args.fajl}")
        for utvonal in proba_naplo_archivumok():
            print(f"  archívum: {utvonal.relative_to(GYOKER).as_posix()}")
        return 1

    sorok = proba_naplo_olvas(args.utolso, utvonal=args.fajl)
    forras = (args.fajl or PROBA_NAPLO_UTVONAL).name
    args.ki.parent.mkdir(parents=True, exist_ok=True)
    args.ki.write_text(riport(sorok, forras), encoding="utf-8")
    print(f"Riport kész: {args.ki}  ({len(sorok)} forduló)")
    if args.megnyit:
        webbrowser.open(args.ki.resolve().as_uri())
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
