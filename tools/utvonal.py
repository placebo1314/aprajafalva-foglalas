"""ÚTVONAL-NÉZŐ — egy beszélgetés lépésről lépésre, előre-hátra
(`python feladat.py utvonal`).

```
python feladat.py utvonal                      # ablak, session-választóval
python feladat.py utvonal --szoveg             # ugyanaz a konzolra, ablak nélkül
python feladat.py utvonal --fajl naplo/probak-20260831-181115.jsonl
python feladat.py utvonal --session 3f2a       # egy konkrét session (elég a eleje)
```

**Miért kellett, amikor van már napló-elemző és riport.** Mert azok
FORDULÓKAT mutatnak: az elemző összesít (hány forduló, milyen rétegek,
mennyi idő), a riport pedig egyetlen fordulót bont ki teljes
mélységben. Egyik sem válaszol arra a kérdésre, ami egy próba után
először merül fel: **hogyan jutott EL a beszélgetés oda, ahova?**

Ez a nézet a BESZÉLGETÉST teszi az elemzés egységévé, és fordulónként
három dolgot mutat meg egymás mellett:

1. **Mi történt** — mit írt be a vásárló, mit látott belőle a rendszer,
   mi lett belőle (eszköz, paraméterek), és mit kapott vissza.
2. **Miért oda ment tovább** — melyik réteg döntött és milyen alapon:
   elkapta-e a kapuőr, mit adott a modell és mit a dátumparser, melyik
   nyert, mely mezők jöttek honnan, melyik kapu szólt közbe.
3. **Hol tartott, és hova jutott** — az állapotgép állapota és átmenete
   (ADR-028), meg hogy miért NEM mozdult, ha nem mozdult.

**A magyarázatot nem találjuk ki**: minden mondata a naplóban álló
mezőkre mutat vissza (`nyomkovetes.mezo_forras`, `.datum.nyertes`,
`.kapuor`, `bizonyossag`, `allapot`, `atmenet`). Ahol a napló hallgat,
ott a nézet is azt írja, hogy nem tudjuk — nem pótolja sejtéssel.

**A session-azonosító 2026-09-21 óta kerül a naplóba.** A régebbi
sorokat időköz alapján csoportosítjuk (`_IDOKOZ_PERC`), és ezt a nézet
KI IS ÍRJA: egy becsült határ nem ugyanaz a bizonyíték, mint egy
rögzített azonosító.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

GYOKER = Path(__file__).resolve().parents[1]
if str(GYOKER) not in sys.path:
    sys.path.insert(0, str(GYOKER))

# Ennyi szünet után KÜLÖN beszélgetésnek vesszük a fordulókat — csak a
# `session_id` NÉLKÜLI, régi naplósoroknál. Tapasztalati érték: egy
# beszélgetésen belül a leghosszabb szünet is percekben mérhető (a
# modell 3-4 másodperc, a gépelés is), két próba között viszont
# jellemzően negyedóra telik el.
_IDOKOZ_PERC = 10

# A dátumfeloldás kimenete, ha a mondatban egyáltalán nem volt időpont
# (`assistant/interpreter/`). Külön mondat jár neki: ez nem kudarc,
# hanem a dokumentált tartalék ablak.
_NINCS_DATUM = "nincs feloldható dátum"


@dataclass
class Lepes:
    """Egy forduló a beszélgetés útvonalán — a naplósor és a belőle
    OLVASHATÓ magyarázat."""

    sorszam: int
    sor: dict

    @property
    def nyom(self) -> dict:
        return self.sor.get("nyomkovetes") or {}

    @property
    def bemenet(self) -> str:
        return self.sor.get("bemenet") or ""

    @property
    def idopont(self) -> str:
        return (self.sor.get("idobelyeg") or "")[11:19]


@dataclass
class Beszelgetes:
    """Egy session útvonala. A `becsult` azt jelenti, hogy a határait
    időköz alapján húztuk meg, nem `session_id` alapján."""

    azonosito: str
    lepesek: list[Lepes] = field(default_factory=list)
    becsult: bool = False

    @property
    def kezdet(self) -> str:
        return (self.lepesek[0].sor.get("idobelyeg") or "") if self.lepesek else ""

    @property
    def elso_mondat(self) -> str:
        return self.lepesek[0].bemenet if self.lepesek else ""

    @property
    def vegkimenetel(self) -> str:
        """Mire jutott a beszélgetés — a session-lista második sora.

        Nem a legutolsó forduló típusa, hanem a LEGTÖBBET mondó: egy
        létrejött foglalás akkor is a végkimenetel, ha utána még
        elhangzott egy köszönöm."""
        tipusok = [lepes.sor.get("valasz_tipus") for lepes in self.lepesek]
        for tipus, szoveg in (
            ("visszaigazolas", "foglalás létrejött"),
            ("megerositest_ker", "megerősítésig jutott"),
            ("ajanlat", "kapott ajánlatot"),
            ("kiut", "kiútig jutott"),
            ("kinalat", "katalógusig jutott"),
        ):
            if tipus in tipusok:
                return szoveg
        return "nem jutott ajánlatig"


def sessionokra_bont(sorok: list[dict]) -> list[Beszelgetes]:
    """A naplósorok BESZÉLGETÉSEKRE bontva, időrendben.

    Elsődlegesen a `session_id` szerint — az a rögzített igazság. Ahol
    az hiányzik (2026-09-21 előtti sorok), ott az időköz dönt, és a
    beszélgetés `becsult` jelet kap: a nézet ezt kiírja, mert egy
    sejtett határ nem ugyanaz a bizonyíték, mint egy azonosító."""
    beszelgetesek: list[Beszelgetes] = []
    utolso_ido: datetime | None = None
    for sor in sorok:
        azonosito = sor.get("session_id")
        ido = _ido(sor.get("idobelyeg"))
        if azonosito:
            if not beszelgetesek or beszelgetesek[-1].azonosito != azonosito:
                beszelgetesek.append(Beszelgetes(azonosito=azonosito))
        else:
            uj_kell = (
                not beszelgetesek
                or not beszelgetesek[-1].becsult
                or (
                    ido is not None
                    and utolso_ido is not None
                    and ido - utolso_ido > timedelta(minutes=_IDOKOZ_PERC)
                )
            )
            if uj_kell:
                beszelgetesek.append(
                    Beszelgetes(azonosito=f"(becsült #{len(beszelgetesek) + 1})", becsult=True)
                )
        utolso_ido = ido or utolso_ido
        aktualis = beszelgetesek[-1]
        aktualis.lepesek.append(Lepes(sorszam=len(aktualis.lepesek) + 1, sor=sor))
    return beszelgetesek


def _ido(idobelyeg: str | None) -> datetime | None:
    if not idobelyeg:
        return None
    try:
        return datetime.fromisoformat(idobelyeg.replace("Z", "+00:00"))
    except ValueError:
        return None


# ---------------------------------------------------------------------
# A MAGYARÁZAT — „miért oda ment tovább"
#
# Ez a modul lelke, és szándékosan TISZTA FÜGGVÉNY: egy naplósorból
# mondatokat csinál, felület nélkül. Így tesztelhető
# (`tests/egyseg/test_utvonal.py`), és így használható a `--szoveg`
# alakban is.
# ---------------------------------------------------------------------

# Melyik réteg mit jelent. A `reteg` mező egy szó; a próbálgatónak
# viszont az a kérdése, hogy KI döntött és MIÉRT ő.
_RETEG_MAGYARAZAT = {
    "kapuor": (
        "A KAPUŐR döntött, a modell meg sem szólalt — a mondat a zárt kategóriák egyikébe esett."
    ),
    "llm": "A MODELL értelmezte a mondatot, utána determinisztikus kapuk ellenőrizték (ADR-018).",
    "szabaly": "A DETERMINISZTIKUS réteg oldotta meg — modellhívás nélkül.",
    "tartalek": "TARTALÉKÁG: nem volt használható modellválasz, a szabályalapú réteg vette át.",
    "orchestrator:sorszam": (
        "Az ORCHESTRATOR ismerte fel, hogy a mondat a felajánlott jelöltek egyikére "
        "mutat — ehhez nem kell modell, csak a lista."
    ),
}

# Válasz-típus → mit LÁTOTT ebből a vásárló, és mi következhet belőle.
# A „hova tovább" kérdésre ez felel: a rendszer minden fordulóban
# felkínál egy folytatást, és a következő mondat arra válasz.
_KOVETKEZMENY = {
    "ajanlat": "Időpontokat kapott — a következő lépés a választás (koppintás vagy mondat).",
    "visszakerdezes": "Visszakérdeztünk — a következő mondat erre a kérdésre felel.",
    "megerositest_ker": "Megerősítést kértünk — innen igen vagy nem visz tovább.",
    "visszaigazolas": "A foglalás LÉTREJÖTT, a beszélgetésnek itt vége is lehet.",
    "elvetve": "Elvetettük a választott időpontot, de a többi jelölt még áll.",
    "kiut": "KIÚT: a rendszer felismerte, hogy nem haladunk, és mást ajánlott.",
    "kinalat": "Felsoroltuk, mi van a boltokban — a következő lépés a bolt választása.",
    "koszones": "Bemutatkoztunk — a vásárló még nem mondott foglalási kérést.",
    "meta_valasz": "A rendszerről szóló kérdésre feleltünk; a beszélgetés állapota NEM változott.",
    "elutasitas": "Hatókörön kívüli kérés — nem indult keresés.",
    "eszkoz_hiba": "A keresés lefutott, de nem talált — a válasz megmondja, min lehet lazítani.",
}


def mi_tortent(lepes: Lepes) -> list[tuple[str, str]]:
    """`[(címke, érték)]` — a forduló TÉNYEI, magyarázat nélkül."""
    sor = lepes.sor
    sorok = [("Beírta", lepes.bemenet or "(gombnyomás)")]
    if sor.get("normalizalt") and sor["normalizalt"] != lepes.bemenet:
        sorok.append(("Normalizálva", sor["normalizalt"]))
    sorok.append(("Eszköz", sor.get("eszkoz") or "—"))
    parameterek = sor.get("parameterek") or {}
    if parameterek:
        sorok.append(
            ("Paraméterek", "\n".join(f"{kulcs} = {ertek}" for kulcs, ertek in parameterek.items()))
        )
    sorok.append(("Válasz típusa", sor.get("valasz_tipus") or "—"))
    if sor.get("uzenet_kulcs"):
        sorok.append(("Üzenet", sor["uzenet_kulcs"]))
    kimenet = (lepes.nyom.get("valasz_szovegesen") or "").strip()
    if kimenet:
        sorok.append(("Amit a vásárló látott", kimenet))
    if sor.get("valaszido_masodperc") is not None:
        sorok.append(("Válaszidő", f"{sor['valaszido_masodperc']:.2f} s"))
    return sorok


def miert(lepes: Lepes) -> list[str]:
    """MIÉRT oda ment tovább — mondatok, a naplóban álló mezőkből.

    Minden mondat mögött konkrét mező van. Ahol a napló hallgat, ott
    ez a lista rövidebb — nem egészítjük ki sejtéssel."""
    sor, nyom = lepes.sor, lepes.nyom
    mondatok: list[str] = []

    kapuor = nyom.get("kapuor") or {}
    kategoria = kapuor.get("kategoria")
    if kategoria and kategoria != "foglalasi_szandek":
        reszletek = ", ".join(resz for resz in (kapuor.get("ok"), kapuor.get("minta")) if resz)
        mondatok.append(
            f"A KAPUŐR elkapta a mondatot: {kategoria}"
            + (f" ({reszletek})" if reszletek else "")
            + " — ide a modell már nem szólt bele."
        )
    elif kategoria:
        mondatok.append("A kapuőr ÁTENGEDTE: foglalási szándéknak látta.")

    reteg = sor.get("reteg") or ""
    if reteg.startswith("felulet:"):
        mondatok.append(
            f"KOPPINTÁS ({reteg.split(':', 1)[1]}) — itt nem volt mit értelmezni, "
            "a szándék a gombból egyértelmű."
        )
    elif reteg in _RETEG_MAGYARAZAT:
        mondatok.append(_RETEG_MAGYARAZAT[reteg])
    elif reteg:
        mondatok.append(f"A(z) {reteg} réteg oldotta meg a fordulót.")

    if nyom.get("rovidzar"):
        mondatok.append(f"RÖVIDZÁR: {nyom['rovidzar']} — a szokásos út egy részét kihagytuk.")

    mondatok.extend(_mezo_forras_mondatok(nyom))
    mondatok.extend(_datum_mondatok(nyom))
    mondatok.extend(_bizonyossag_mondatok(sor, nyom.get("modellhivas_db", 1)))

    if nyom.get("sema_ok") is False:
        mondatok.append("A modellválasz NEM ment át a séma-ellenőrzésen — ezért nem az döntött.")
    if nyom.get("llm_hiba"):
        mondatok.append(f"Modellhiba: {nyom['llm_hiba']} — innen a tartalékág vitte tovább.")
    return mondatok


def _mezo_forras_mondatok(nyom: dict) -> list[str]:
    """Melyik mező HONNAN jött. Ez a leggyakoribb kérdés egy furcsa
    keresés után: a boltot a vásárló mondta, vagy mi találtuk ki?"""
    forras = nyom.get("mezo_forras") or {}
    if not forras:
        return []
    return [
        "A mezők forrása: " + ", ".join(f"{mezo} ← {honnan}" for mezo, honnan in forras.items())
    ]


def _datum_mondatok(nyom: dict) -> list[str]:
    """A dátumfeloldás — a modell és a parser versenye (ADR-011).

    Ez az a pont, ahol a legtöbbet lehet tévedni, és ahol a napló a
    legtöbbet mondja: mit adott a modell, mit a parser, és MELYIK
    nyert."""
    datum = nyom.get("datum") or {}
    if not datum:
        return []
    mondatok = []
    kifejezes = datum.get("modell_kifejezes")
    if kifejezes:
        mondatok.append(f"A modell ezt a dátumkifejezést adta: {kifejezes!r}.")
    nyertes = datum.get("nyertes")
    if not nyertes:
        return mondatok
    if nyertes == _NINCS_DATUM:
        # NEM hiba, hanem bevallott hiánypótlás: a mondatban nem volt
        # időpont, tehát a keresés a dokumentált tartalék ablakot
        # kapta. A golden mérés is így különbözteti meg a kitalált
        # dátumtól (`tests/golden/futtato.py::_tartalek_ablak_e`).
        mondatok.append(
            "A mondatban NEM volt feloldható dátum — a keresés a tartalék ablakot kapta "
            "(egy hét mostantól). Ez bevallott hiánypótlás, nem kitalált időpont."
        )
        return mondatok
    mondatok.append(
        f"A dátumot a {nyertes} oldotta fel: "
        f"{datum.get('parser_tol') or datum.get('modell_datum_tol') or '—'} "
        f"→ {datum.get('parser_ig') or '—'}."
    )
    return mondatok


def _bizonyossag_mondatok(sor: dict, modellhivas: int = 1) -> list[str]:
    """A bizonyosság-kapu (ADR-021): mely mezőkben volt bizonytalan a
    modell, és mit tettünk vele.

    A `None` érték itt NEM alacsony bizonyosság — azt jelenti, hogy a
    mezőt nem a modell adta (pl. a dátumot a parser oldotta fel). Ezt
    fontos külön mondani: különben a nézet minden fordulónál
    bizonytalanságot jelentene ott, ahol szó sincs róla."""
    bizonyossag = sor.get("bizonyossag") or {}
    ertekek = {
        mezo: ertek for mezo, ertek in bizonyossag.items() if isinstance(ertek, (int, float))
    }
    if not ertekek:
        return []
    if not modellhivas:
        # NEM MODELL-BIZONYOSSÁG. A rövidzárak (sorszám, megerősítés) és
        # a kapuőr 1.0-t írnak be, mert determinisztikusan biztosak —
        # ezt „a modell magabiztos volt" mondattal visszaadni hazugság
        # lenne: modell nem is futott.
        return [
            "A bizonyosság itt determinisztikus (1.00), nem modell-pontszám: nem futott modell."
        ]
    alacsony = [f"{mezo} {ertek:.2f}" for mezo, ertek in ertekek.items() if ertek < 0.8]
    if alacsony:
        return ["ALACSONY bizonyosság: " + ", ".join(alacsony) + " — itt szólhat közbe a kapu."]
    legkisebb = min(ertekek.items(), key=lambda parosr: parosr[1])
    return [f"A modell magabiztos volt (a leggyengébb mező: {legkisebb[0]} {legkisebb[1]:.2f})."]


def hova_tovabb(lepes: Lepes, kovetkezo: Lepes | None) -> list[str]:
    """Hol tartott a beszélgetés, hova jutott — és mi következett."""
    sor = lepes.sor
    mondatok = []
    allapot = sor.get("allapot")
    atmenet = sor.get("atmenet")
    if atmenet:
        mondatok.append(f"Állapotátmenet: {atmenet}.")
    elif allapot:
        mondatok.append(
            f"Az állapot MARADT: {allapot} — ez a forduló nem vitte tovább a beszélgetést."
        )
    kovetkezmeny = _KOVETKEZMENY.get(sor.get("valasz_tipus") or "")
    if kovetkezmeny:
        mondatok.append(kovetkezmeny)
    if kovetkezo is not None:
        mondatok.append(f"A vásárló erre ezt mondta: {kovetkezo.bemenet!r}")
    else:
        mondatok.append("Ez volt a beszélgetés utolsó fordulója.")
    return mondatok


def lepes_szovege(lepes: Lepes, kovetkezo: Lepes | None, osszesen: int) -> str:
    """Egy lépés teljes szövege — ugyanaz a tartalom megy az ablakba és
    a `--szoveg` kimenetbe. Egy forrás, két megjelenés."""
    reszek = [f"{lepes.sorszam}/{osszesen}. forduló  ({lepes.idopont})", ""]
    for cimke, ertek in mi_tortent(lepes):
        if "\n" in str(ertek):
            reszek.append(f"  {cimke}:")
            reszek.extend(f"      {alsor}" for alsor in str(ertek).split("\n"))
        else:
            reszek.append(f"  {cimke}: {ertek}")
    reszek += ["", "  MIÉRT ÍGY DÖNTÖTT:"]
    reszek += [f"    - {mondat}" for mondat in miert(lepes)] or [
        "    (a napló nem mond róla semmit)"
    ]
    reszek += ["", "  HOVA TOVÁBB:"]
    reszek += [f"    - {mondat}" for mondat in hova_tovabb(lepes, kovetkezo)]
    return "\n".join(reszek)


def beszelgetes_szovege(beszelgetes: Beszelgetes) -> str:
    fejlec = [
        "=" * 72,
        f"Beszélgetés: {beszelgetes.azonosito}"
        + ("   [a határai BECSÜLTEK — nincs session-azonosító]" if beszelgetes.becsult else ""),
        f"Kezdet: {beszelgetes.kezdet}   fordulók: {len(beszelgetes.lepesek)}"
        f"   végkimenetel: {beszelgetes.vegkimenetel}",
        "=" * 72,
        "",
    ]
    osszesen = len(beszelgetes.lepesek)
    torzs = []
    for index, lepes in enumerate(beszelgetes.lepesek):
        kovetkezo = beszelgetes.lepesek[index + 1] if index + 1 < osszesen else None
        torzs.append(lepes_szovege(lepes, kovetkezo, osszesen))
    return "\n".join(fejlec) + "\n\n".join(torzs)


def szures(beszelgetesek: list[Beszelgetes], eleje: str | None) -> list[Beszelgetes]:
    """Session-szűrés az azonosító ELEJE alapján — egy 32 karakteres
    UUID-t nem gépel be senki."""
    if not eleje:
        return beszelgetesek
    return [b for b in beszelgetesek if b.azonosito.startswith(eleje)]


# ---------------------------------------------------------------------
# AZ ABLAK
#
# Tkinter, mint a vásárlói felület — nincs új függőség, és Windowson,
# macOS-en, Linuxon egyaránt elindul. A nézet SZÁNDÉKOSAN nem szerkeszt
# semmit: naplót olvas, és soha nem ír.
# ---------------------------------------------------------------------


class UtvonalAblak:
    """A session-választó és a lépegető. Az `Előző`/`Következő` mellett
    a balra-jobbra nyíl is lép — aki egy beszélgetést átnéz, nem az
    egérhez akar nyúlni minden fordulónál."""

    def __init__(self, beszelgetesek: list[Beszelgetes], forras: str) -> None:
        import tkinter as tk
        from tkinter import ttk

        self._tk = tk
        self.beszelgetesek = beszelgetesek
        self.aktualis: Beszelgetes | None = None
        self.index = 0

        self.ablak = tk.Tk()
        self.ablak.title(f"Útvonal — {forras}")
        self.ablak.geometry("1180x760")

        keret = ttk.Frame(self.ablak, padding=10)
        keret.pack(fill="both", expand=True)

        bal = ttk.Frame(keret)
        bal.pack(side="left", fill="y", padx=(0, 12))
        ttk.Label(bal, text="Beszélgetések", font=("TkDefaultFont", 10, "bold")).pack(anchor="w")
        ttk.Label(
            bal,
            text=f"{len(beszelgetesek)} db — a legújabb legfelül",
            foreground="#555",
        ).pack(anchor="w", pady=(0, 6))
        self.lista = tk.Listbox(bal, width=46, height=34, exportselection=False)
        self.lista.pack(fill="y", expand=True)
        self.lista.bind("<<ListboxSelect>>", self._valasztas)
        for beszelgetes in reversed(beszelgetesek):
            jel = "~" if beszelgetes.becsult else " "
            self.lista.insert(
                "end",
                f"{jel}{beszelgetes.kezdet[5:16]}  {len(beszelgetes.lepesek):2}×  "
                f"{beszelgetes.elso_mondat[:24]}",
            )

        jobb = ttk.Frame(keret)
        jobb.pack(side="left", fill="both", expand=True)

        self.fejlec = ttk.Label(jobb, text="", font=("TkDefaultFont", 11, "bold"), wraplength=760)
        self.fejlec.pack(anchor="w")
        self.alfejlec = ttk.Label(jobb, text="", foreground="#555", wraplength=760)
        self.alfejlec.pack(anchor="w", pady=(0, 8))

        self.szoveg = tk.Text(jobb, wrap="word", state="disabled", font=("TkFixedFont", 10))
        self.szoveg.pack(fill="both", expand=True)

        gombsor = ttk.Frame(jobb, padding=(0, 10))
        gombsor.pack(fill="x")
        self.elozo_gomb = ttk.Button(gombsor, text="◀ Előző", command=self.elozo)
        self.elozo_gomb.pack(side="left")
        self.kovetkezo_gomb = ttk.Button(gombsor, text="Következő ▶", command=self.kovetkezo)
        self.kovetkezo_gomb.pack(side="left", padx=(6, 0))
        self.szamlalo = ttk.Label(gombsor, text="")
        self.szamlalo.pack(side="left", padx=(14, 0))
        ttk.Label(gombsor, text="(a balra-jobbra nyíl is lép)", foreground="#777").pack(
            side="right"
        )

        self.ablak.bind("<Left>", lambda _esemeny: self.elozo())
        self.ablak.bind("<Right>", lambda _esemeny: self.kovetkezo())

        if beszelgetesek:
            self.lista.selection_set(0)
            self._betolt(beszelgetesek[-1])

    def _valasztas(self, _esemeny) -> None:
        kijelolt = self.lista.curselection()
        if kijelolt:
            self._betolt(list(reversed(self.beszelgetesek))[kijelolt[0]])

    def _betolt(self, beszelgetes: Beszelgetes) -> None:
        self.aktualis = beszelgetes
        self.index = 0
        becsult = (
            "   [a határai BECSÜLTEK — nincs session-azonosító]" if beszelgetes.becsult else ""
        )
        self.fejlec.config(text=f"{beszelgetes.azonosito}{becsult}")
        self.alfejlec.config(
            text=f"{beszelgetes.kezdet}  ·  {len(beszelgetes.lepesek)} forduló  ·  "
            f"{beszelgetes.vegkimenetel}"
        )
        self._rajzol()

    def elozo(self) -> None:
        if self.aktualis and self.index > 0:
            self.index -= 1
            self._rajzol()

    def kovetkezo(self) -> None:
        if self.aktualis and self.index + 1 < len(self.aktualis.lepesek):
            self.index += 1
            self._rajzol()

    def _rajzol(self) -> None:
        if not self.aktualis or not self.aktualis.lepesek:
            return
        lepesek = self.aktualis.lepesek
        kovetkezo = lepesek[self.index + 1] if self.index + 1 < len(lepesek) else None
        self.szoveg.config(state="normal")
        self.szoveg.delete("1.0", "end")
        self.szoveg.insert("1.0", lepes_szovege(lepesek[self.index], kovetkezo, len(lepesek)))
        self.szoveg.config(state="disabled")
        self.szamlalo.config(text=f"{self.index + 1} / {len(lepesek)}")
        self.elozo_gomb.state(["!disabled"] if self.index > 0 else ["disabled"])
        self.kovetkezo_gomb.state(["!disabled"] if self.index + 1 < len(lepesek) else ["disabled"])

    def fut(self) -> None:
        self.ablak.mainloop()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Egy beszélgetés útvonala lépésről lépésre, a próba-naplóból."
    )
    parser.add_argument(
        "--fajl", type=Path, default=None, help="archív napló (naplo/probak-<dátum>.jsonl)"
    )
    parser.add_argument("--session", default=None, help="csak ez a session (elég az eleje)")
    parser.add_argument(
        "--szoveg", action="store_true", help="konzolra írja, ablak nélkül (SSH, CI)"
    )
    parser.add_argument("--utolso", type=int, default=None, help="csak az utolsó N beszélgetés")
    args = parser.parse_args(argv)

    from ui.vasarlo import PROBA_NAPLO_UTVONAL, proba_naplo_olvas

    sorok = proba_naplo_olvas(utvonal=args.fajl)
    if not sorok:
        print(
            "A próba-napló üres vagy nem létezik. Írj be pár mondatot a felületen "
            "(python -m ui.vasarlo), vagy futtasd: python feladat.py vegigjatszas"
        )
        return 1

    beszelgetesek = szures(sessionokra_bont(sorok), args.session)
    if not beszelgetesek:
        print(f"Nincs ilyen session: {args.session!r}")
        return 1
    if args.utolso:
        beszelgetesek = beszelgetesek[-args.utolso :]

    forras = (args.fajl or PROBA_NAPLO_UTVONAL).name
    if args.szoveg:
        for beszelgetes in beszelgetesek:
            print(beszelgetes_szovege(beszelgetes))
            print()
        return 0

    try:
        UtvonalAblak(beszelgetesek, forras).fut()
    except Exception as kivetel:  # noqa: BLE001 — l. lent
        # NINCS KÉPERNYŐ (SSH, CI, hiányzó Tk). Nem tracebackkel
        # állunk meg: a szöveges alak ugyanazt a tartalmat adja, és
        # ilyenkor az a helyes válasz, nem a hibaüzenet.
        print(f"Az ablak nem nyílt meg ({kivetel}) — a szöveges alak következik.\n")
        for beszelgetes in beszelgetesek:
            print(beszelgetes_szovege(beszelgetes))
            print()
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
