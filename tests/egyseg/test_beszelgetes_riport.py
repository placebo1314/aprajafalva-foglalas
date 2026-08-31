"""A beszélgetés-elemző (`tools/beszelgetes_riport.py`,
`python feladat.py riport`).

A `riport()` tiszta függvény (napló-sorok → HTML szöveg), tehát fájl és
böngésző nélkül tesztelhető. Amit itt mérünk:

1. **a lényeg BENNE van** — prompt, nyers válasz, dátumfeloldás, mindkét
   kimeneti mód;
2. **a HTML nem törik el** attól, amit a vásárló beírt (escape);
3. **a hiányzó nyomkövetés nem hibaág** — a régi naplósorok is
   megjeleníthetők.
"""

from __future__ import annotations

from tools.beszelgetes_riport import fordulo_blokk, modell_nelkul_futott, riport


def _sor(**mezok) -> dict:
    alap = {
        "idobelyeg": "2026-08-30T12:00:00Z",
        "bemenet": "Törpillához mennék holnap",
        "normalizalt": "Törpillához mennék holnap",
        "reteg": "llm",
        "eszkoz": "szabad_idopontok",
        "parameterek": {"bolt_id": "torpilla", "datum_tol": "2026-12-22T00:00:00Z"},
        "bizonyossag": {"eszkoz": 0.99, "bolt_id": 0.98},
        "valasz_tipus": "ajanlat",
        "uzenet_kulcs": None,
        "kapuor_ok": None,
        "egyetertes": None,
        "valaszido_masodperc": 4.2,
        "nyomkovetes": {
            "lepesek": [
                {"nev": "kapuőr", "masodperc": 0.001},
                {"nev": "modellhívás", "masodperc": 4.1},
            ],
            "mezo_forras": {"bolt_id": "modell", "datum": "dátumparser"},
            "datum": {
                "modell_kifejezes": "holnap",
                "modell_datum_tol": None,
                "parser_tol": "2026-12-22T00:00:00Z",
                "parser_ig": "2026-12-22T23:59:59Z",
                "nyertes": "parser (a modell idézetéből)",
            },
            "kapuor": {"kategoria": "foglalasi_szandek", "ok": None},
            "modell": "qwen3.5:9b",
            "modellhivas_db": 1,
            "prompt": {"rendszer": "RENDSZERPROMPT", "vasarlo": "Vásárló: Törpillához mennék"},
            "nyers_valasz": '{"eszkoz": "szabad_idopontok"}',
            "sema_ok": True,
            "llm_hiba": None,
            "valasz_szovegesen": "Ezeket az időpontokat találtam — melyik jó?",
            "valasz_beszelhetoen": "A legkorábbi nyolc órakor van. Jó lesz?",
        },
    }
    return {**alap, **mezok}


# --- ami benne van ---------------------------------------------------


def test_a_fordulo_blokk_a_teljes_nyomkovetest_megmutatja():
    blokk = fordulo_blokk(_sor(), 1)

    for elvart in (
        "Törpillához mennék holnap",  # bemenet
        "RENDSZERPROMPT",  # a teljes prompt
        "Vásárló: Törpillához mennék",  # a beszélgetés, ahogy a modell látta
        "{&quot;eszkoz&quot;: &quot;szabad_idopontok&quot;}",  # nyers válasz, escape-elve
        "parser (a modell idézetéből)",  # dátumfeloldás: melyik nyert
        "dátumparser",  # mezőnkénti forrás
        "modellhívás",  # lépésenkénti idő
        "A legkorábbi nyolc órakor van. Jó lesz?",  # beszélhető kimenet
        "Ezeket az időpontokat találtam",  # szöveges kimenet
        "qwen3.5:9b",
    ):
        assert elvart in blokk, elvart


def test_a_hosszu_reszek_osszecsukva_indulnak():
    """A prompt fordulónként több ezer karakter — nyitva a jelentés
    olvashatatlan lenne. A `<details>` natívan csukott, JavaScript
    nélkül."""
    blokk = fordulo_blokk(_sor(), 1)
    assert "<details class='reszlet'><summary>A teljes prompt" in blokk
    # A forduló-blokk maga is csukott (nincs `open` attribútum).
    assert '<details class="fordulo">' in blokk


def test_a_reteg_szinkodot_kap():
    llm = fordulo_blokk(_sor(reteg="llm"), 1)
    tartalek = fordulo_blokk(_sor(reteg="szabaly:tartalek"), 1)

    assert "background:#e8f0fe" in llm
    # A tartalék az egyetlen réteg, ami elromlott állapotot jelezhet —
    # riasztó színt kap.
    assert "background:#fdecea" in tartalek


def test_a_normalizalas_jelolve_van_ha_atirt():
    """A „hónap" → „holnap" típusú csere a leggyakoribb
    meglepetés-forrás — látszania kell, hogy a rendszer MÁST látott."""
    atirt = fordulo_blokk(_sor(bemenet="hónap mennék", normalizalt="holnap mennék"), 1)
    valtozatlan = fordulo_blokk(_sor(), 1)

    assert "átírva" in atirt
    assert "átírva" not in valtozatlan


# --- ami nem törhet el -----------------------------------------------


def test_a_vasarlo_szovege_nem_torheti_el_a_html_t():
    """A napló a vásárló mondatait tartalmazza. Egy `<script>` szó nem
    törheti el a jelentést — és nem is futhat le benne."""
    blokk = fordulo_blokk(_sor(bemenet="<script>alert('x')</script> időpontot kérek"), 1)

    assert "<script>" not in blokk
    assert "&lt;script&gt;" in blokk


def test_a_nyomkovetes_nelkuli_regi_naplosor_is_megjelenik():
    """A nyomkövetés később került a naplóba — a korábbi sorok nem
    tehetik használhatatlanná a jelentést."""
    regi = _sor()
    del regi["nyomkovetes"]

    blokk = fordulo_blokk(regi, 3)

    assert "Törpillához mennék holnap" in blokk
    assert "3." in blokk


def test_ures_naplo_utbaigazit():
    szoveg = riport([])

    assert "üres" in szoveg
    assert "vegigjatszas" in szoveg


# --- a fejléc-összesítés ---------------------------------------------


def test_a_fejlec_ugyanazokat_a_szamokat_hozza_mint_a_naplo_elemzo():
    """Két jelentés nem mondhat mást ugyanarról a naplóról — a fejléc
    ezért a `naplo_elemzo.elemez()`-ből dolgozik, nem saját
    számolásból."""
    sorok = [_sor(valaszido_masodperc=1.0), _sor(reteg="kapuor", valasz_tipus="elutasitas")]

    szoveg = riport(sorok)

    assert "fordulók" in szoveg
    assert "p50" in szoveg
    assert "réteg-megoszlás" in szoveg


def test_a_teljes_html_onallo_es_offline():
    """Egyetlen fájl: nincs külső stíluslap, nincs script, nincs CDN —
    átmásolható és elküldhető."""
    szoveg = riport([_sor()])

    assert szoveg.startswith("<!doctype html>")
    assert "<style>" in szoveg
    assert "http://" not in szoveg and "https://" not in szoveg
    assert "<script" not in szoveg


# -- MODELL NÉLKÜL FUTOTT beszélgetés (piros sáv a fejlécben) ----------
#
# Ez a jelentés legfontosabb egy bitje. A tartalék ág csendben átveszi a
# fordulót, a válaszok értelmesek maradnak, és a számok mégis mást
# mérnek, mint amit az olvasó hisz.


def test_modell_nelkuli_beszelgetesre_piros_figyelmeztetes():
    html = riport([_sor(reteg="szabaly:tartalek", nyomkovetes=None)])

    assert "MODELL NÉLKÜL futott" in html
    assert "modell-riaszt" in html


def test_modell_reteg_eseten_nincs_figyelmeztetes():
    html = riport([_sor(reteg="llm")])

    assert "MODELL NÉLKÜL futott" not in html


def test_egyetlen_modellhivas_is_elegendo():
    """A réteg nem az egyetlen forrás: van olyan út (kapuőr, sorszámos
    hivatkozás), ahol a `reteg` nem `llm`, de a fordulóban MÉGIS volt
    modellhívás. Az ilyen beszélgetés nem „modell nélküli"."""
    sorok = [
        _sor(reteg="kapuor", nyomkovetes={"modellhivas_db": 1}),
        _sor(reteg="szabaly:tartalek", nyomkovetes={"modellhivas_db": 0}),
    ]

    assert modell_nelkul_futott(sorok) is False


def test_ures_naplo_nem_riaszt():
    """Nulla forduló nem állítás a modellről — arra nincs mit mondani."""
    assert modell_nelkul_futott([]) is False
    assert "MODELL NÉLKÜL futott" not in riport([])


def test_a_riasztas_kiirja_a_konfiguralt_modellt():
    """A leggyanúsabb eset: VAN beállított modell, mégsem futott
    egyetlen hívás sem (nem indult el az Ollama). Ezt külön ki kell
    mondani, mert a próbálgató épp azt hiszi, hogy be van kapcsolva."""
    html = riport([_sor(reteg="szabaly:tartalek", modell="qwen3.5:9b", nyomkovetes=None)])

    assert "qwen3.5:9b" in html
    assert "egyetlen fordulóban sem futott modellhívás" in html


def test_a_riport_kiirja_a_forras_naplot():
    """Archivált naplóból készült riport (`--fajl`): két riport ugyanúgy
    néz ki, és ha nem írja ki, melyik próbasorozatot mutatja, a másikra
    hivatkozó következtetés némán rossz lesz."""
    html = riport([_sor()], "probak-20260831-195812.jsonl")

    assert "probak-20260831-195812.jsonl" in html
