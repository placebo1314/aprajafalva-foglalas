"""Vásárlói felület — Tkinter, két egyenrangú út egy ablakban
(blueprint 10. szakasz, "Koppintós út"):

- **koppintós**: bolt → nap → napszak → időpontválasztás a pontozott
  jelöltekből → megerősítés → kód. Végig gombokkal, nincs szükség az
  értelmezőre (`orchestrator.kereses_strukturaltan()`).
- **szöveges**: beviteli mező, az `assistant/orchestrator.py`-n át. A
  zárt kérdések gombként jelennek meg (pl. "Kedden vagy szerdán?" két
  gomb) — a felhasználónak nem kell begépelnie a választ.

Mindkét út UGYANAZOKAT az eszközöket hívja (`assistant/tools/`), a
választás/megerősítés utáni lépések közösek (`orchestrator.valaszt()`,
`.megerosit()`, `.elvet()`) — l. `tests/egyseg/test_orchestrator.py::
test_kereses_strukturaltan_koppintos_ut_ugyanoda_vezet`.

**A magyar mondatokat ez a modul sosem fogalmazza meg** — minden szöveg
az `assistant/valasz/` modulon át jön (M5: sablonok fájlban, nyelvkulcs
alatt). A felület csak megjeleníti, amit kap; a jövőbeli hangréteg
ugyanígy, ugyanezt a modult hívva, csak felolvasva.

**A vásárlóazonosító hash-elése is ideiglenes**: a végleges HMAC+pepper
megoldás (CLAUDE.md 2. invariáns) még nincs megírva — amíg nincs, a
`privacy/hash_ideiglenes.py` (sima SHA-256) helyettesíti. A nyers
azonosítót ez a modul (ui/vasarlo.py) sosem kapja meg szimbólumnévként
— rögtön a `privacy/` hívásának adja át, onnantól csak a hash kering.

**A felület a BEOSZTÁSHOZ igazodik, nem a rendszerórához.** A
`python feladat.py seed` demóadata egy fix, 2026-12-21-gyel kezdődő
hétre generál beosztást (`seed/betolt.py`) — ha a felület a mai naptól
keresne, MINDEN keresés üresen térne vissza, és a próbálgató ebből azt
látná, hogy "nem működik". Ezért:

- az `_idoszak` a ténylegesen meglévő slotokból derül ki
  (`core/repo/muszak_repo.py::slot_range`), nem konstansból;
- a koppintós "Nap" választó ennek az időszaknak a napjait kínálja,
  alapértelmezésben az elsőt (ha a mai nap az időszakon belül van, akkor
  a mait);
- a szöveges út `most`-ja is ide horgonyzódik (`_most_iso`): ha a mai
  nap kívül esik a beosztáson, a "ma"/"holnap"/"jövő héten" ehhez az
  időszakhoz képest oldódik fel, nem a valódi naptárhoz. Így a
  próbálgatónak NEM kell dátumot fejben tartania.
- az ablak tetején egy sor mindig kiírja, melyik időszakra van beosztás,
  és hogy a "ma" éppen mit jelent.

Ez **kizárólag a felület horgonya** — a `core/` és az eszközök továbbra
is a kapott ISO-időbélyeggel dolgoznak, semmilyen idő-eltolás nem kerül
beléjük (CLAUDE.md 4. invariáns: minden idő UTC-ben tárolódik).

**A beszélgetés-előzményt EZ A MODUL vezeti** (`szo_elozmenyek`,
ADR-019). Az értelmező a beszélgetést látja, nem a megőrzött
paramétereket adatként — és a ténylegesen kimondott magyar mondatokat
csak a felület ismeri (az orchestrator strukturált választ ad, amit az
`assistant/valasz/` fogalmaz mondattá). Ezért minden képernyőre kerülő
sor (a vásárlóé és a rendszeré egyaránt) bekerül az előzménybe, és a
`fordulo()` hívás átadja az utolsó néhányat. Az "Új beszélgetés" gomb
üríti.

**Az értelmezőt az `assistant/interpreter/__init__.py::
alapertelmezett_ertelmezo()` építi fel** (fordított kaszkád, ADR-018: a
normalizáló fut előbb, a modell értelmez kötött dekódolással, a dátumot
a parser oldja fel, a determinisztikus réteg a tartalék) — ez a modul
(CLAUDE.md, "Modulhatárok": "a ui/ nem hívhat LLM-et közvetlenül") a
modell-specifikus osztályokat sosem importálja, és nem is tudja, fut-e
éppen a háttérszolgáltatás — ha nincs konfigurálva vagy nem elérhető, a
felépítés CSENDBEN (hiba nélkül) a tisztán szabály-alapú viselkedésre
esik vissza.

**Próba-napló** (`naplo/probak.jsonl`, a `.gitignore` kizárja): a
szöveges úton minden fordulóról egy sor — bemenet, normalizált alak,
melyik réteg oldotta meg, felismert eszköz, paraméterek, bizonyosság, a
válasz típusa, időbélyeg. Ez a jövőbeli rejtett golden halmaz
nyersanyaga (golden-set skill: "valós beszélgetésben hiba → redaktált
trace → annotálás → golden set"), és tesztelés közben ez mutatja meg,
MI történt — a szöveges fülön a "Napló megnyitása" gomb olvashatóan
kiírja. **Vásárlóazonosító ide sosem jut el** — a megerősítéshez
használt azonosító-mező (`_megerosit`) egy KÜLÖN út a `privacy/`
hash-hívásba, nem érinti ezt a naplót. Ami viszont KÉRETLENÜL
elhangozhat a szabad szövegben (telefonszám, TAJ, e-mail), az
**redaktálva** kerül lemezre: a `bemenet`, a `normalizalt` és a
`parameterek` mind átmegy a `privacy/redakcio`-n a kiírás előtt
(CLAUDE.md 2. invariáns).

Indítás:
    python -m ui.vasarlo
"""

from __future__ import annotations

import json
import sys
import tkinter as tk
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from tkinter import ttk

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from assistant import valasz as valasz_szoveg  # noqa: E402
from assistant.interpreter import (  # noqa: E402
    KI_RENDSZER,
    KI_VASARLO,
    aktiv_modell_neve,
    alapertelmezett_ertelmezo,
)
from assistant.orchestrator import Orchestrator  # noqa: E402
from assistant.tools import katalogus  # noqa: E402
from core.azonosito import new_uuid  # noqa: E402
from core.repo import migracio, muszak_repo, torzsadat_repo  # noqa: E402
from privacy.hash_ideiglenes import ideiglenes_hash  # noqa: E402
from privacy.redakcio import redaktal, redaktal_ertekek  # noqa: E402
from seed.betolt import ALAP_DB_PATH  # noqa: E402

_NAPSZAKOK = [
    ("delelott", "délelőtt"),
    ("delutan", "délután"),
    ("este", "este"),
    ("barmikor", "bármikor"),
]

_PROBA_NAPLO_UTVONAL = ROOT / "naplo" / "probak.jsonl"

# A szöveges napló "Te:" előtagja — ebből tudja a `_naplo_ir`, hogy a
# sor a vásárlóé-e vagy a rendszeré (a beszélgetés-előzményhez, ADR-019).
_TE_CIMKE = "Te"

# Hány NAPLÓSOR megy át előzményként az értelmezőnek. Négy forduló =
# négy vásárlói sor + a rájuk adott rendszer-sorok; a rendszer egy
# fordulóban több sort is írhat (nyugtázó + eredmény), ezért nem
# fordulót, hanem sort számolunk, bőven a négy forduló fölé kerekítve.
_ELOZMENY_SOROK = 12


def _most_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# Legfeljebb ennyi napot kínál fel a koppintós "Nap" választó a beosztás
# időszakából — hosszú beosztásnál a legördülő különben használhatatlanná
# nyúlna. A demóadat egy hét, ez bőven elég rá.
_NAP_VALASZTO_MAX = 21


def horgony_most(idoszak: dict | None, valodi_most: str) -> str:
    """A szöveges út `most` értéke: a valódi idő, HA a mai nap beleesik a
    beosztás időszakába — különben az időszak első napjának ELEJE.

    Miért: a demóadat egy fix, távoli hétre szól. Ha a "holnap" a valódi
    holnapot jelentené, minden keresés üresen térne vissza, és a
    próbálgató ebből azt látná, hogy a rendszer nem működik — a
    dokumentált, de észben tartandó dátum a legrosszabb fajta felületi
    teher (`docs/TESZTELES.md`, "Beszélgetés-próba").

    **A napszakot is elengedjük** (`T00:00:00Z`), nem csak a napot: ha a
    valódi órát tartanánk meg, egy este próbálgató felhasználónak a "ma"
    egy olyan ablakot jelentene, ami a bolt nyitvatartása UTÁN kezdődik —
    tehát üresen térne vissza, pontosan attól a hibától, amit ez a
    horgony megszüntetni hivatott. A horgonyzott nap amúgy is egy másik
    (jövőbeli) naptári nap, ott a "már elmúlt" fogalomnak nincs értelme.

    Ez a horgony **kizárólag a felületé**: az így kapott ISO-időbélyeg
    ugyanúgy UTC és ugyanúgy végigmegy az orchestratoron, mint bármelyik
    másik — sem a `core/`, sem az eszközök nem tudnak róla (CLAUDE.md 4.
    invariáns)."""
    if idoszak is None:
        return valodi_most
    ma = valodi_most[:10]
    if idoszak["elso_nap"] <= ma <= idoszak["utolso_nap"]:
        return valodi_most
    return f"{idoszak['elso_nap']}T00:00:00Z"


def _idopont_cimke(kezdet_iso: str, veg_iso: str) -> str:
    kezdet = datetime.fromisoformat(kezdet_iso.replace("Z", "+00:00"))
    veg = datetime.fromisoformat(veg_iso.replace("Z", "+00:00"))
    return f"{kezdet.strftime('%Y-%m-%d %H:%M')}–{veg.strftime('%H:%M')} (UTC)"


def _proba_naplo_ir(
    bemenet: str,
    ertelmezes: dict | None,
    reteg: str | None,
    *,
    normalizalt: str | None = None,
    valasz_tipus: str | None = None,
) -> None:
    """Egy fordulót ír a `naplo/probak.jsonl`-be — l. modul docstring,
    "Próba-napló". Nyolc mező, mert tesztelés közben mind a nyolc kérdés
    külön felmerül: mit írtam be, mit LÁTOTT belőle a rendszer
    (`normalizalt`), ki oldotta meg (`reteg`), minek értette (`eszkoz`,
    `parameterek`), mennyire volt biztos benne (`bizonyossag`), mi lett
    belőle (`valasz_tipus`), és mikor (`idobelyeg`).

    **REDAKTÁLÁS TÁROLÁS ELŐTT** (CLAUDE.md 2. invariáns, ADR-005): a
    vásárló mondata és az abból kinyert paraméterek egyaránt átmennek a
    `privacy/redakcio`-n, MIELŐTT lemezre kerülnének. Ez nem elméleti
    óvatosság: a robusztussági halmaz "személyes adat" kategóriája
    pontosan azt méri, mi történik, ha valaki KÉRETLENÜL bediktálja a
    telefonszámát — enélkül a szám nyersen kerülne a naplófájlba, és
    soha nem kértük."""
    _PROBA_NAPLO_UTVONAL.parent.mkdir(parents=True, exist_ok=True)
    sor = {
        "idobelyeg": _most_iso(),
        "bemenet": redaktal(bemenet),
        "normalizalt": redaktal(normalizalt),
        "reteg": reteg,
        "eszkoz": (ertelmezes or {}).get("eszkoz"),
        "parameterek": redaktal_ertekek((ertelmezes or {}).get("parameterek")),
        "bizonyossag": (ertelmezes or {}).get("bizonyossag"),
        "valasz_tipus": valasz_tipus,
    }
    with _PROBA_NAPLO_UTVONAL.open("a", encoding="utf-8") as fajl:
        fajl.write(json.dumps(sor, ensure_ascii=False) + "\n")


def proba_naplo_olvas(utolso: int | None = None) -> list[dict]:
    """A próba-napló sorai, legrégebbitől a legújabbig. `utolso`
    megadásakor csak az utolsó N sor. Hiányzó fájl esetén üres lista —
    ez nem hiba, csak azt jelenti, hogy még nem volt forduló.

    A sérült (nem JSON) sorokat átugorja: a napló megnyitása SOHA ne
    boruljon fel attól, hogy egy korábbi futás félbeszakadt."""
    if not _PROBA_NAPLO_UTVONAL.exists():
        return []
    sorok = []
    for nyers in _PROBA_NAPLO_UTVONAL.read_text(encoding="utf-8").splitlines():
        if not nyers.strip():
            continue
        try:
            sorok.append(json.loads(nyers))
        except json.JSONDecodeError:
            continue
    return sorok[-utolso:] if utolso else sorok


def proba_naplo_szoveg(sorok: list[dict]) -> str:
    """A napló olvasható alakja — ez kerül a "Napló megnyitása" ablakba.
    Külön függvény, hogy Tkinter nélkül is előállítható és tesztelhető
    legyen (`tests/egyseg/test_vasarlo.py`)."""
    if not sorok:
        return "Még nincs egyetlen próba sem. Írj be valamit a szöveges fülön."
    darabok = []
    for i, sor in enumerate(sorok, start=1):
        parameterek = sor.get("parameterek") or {}
        bizonyossag = sor.get("bizonyossag") or {}
        darabok.append(
            f"{i}. [{sor.get('idobelyeg', '?')}]\n"
            f"   bemenet:      {sor.get('bemenet')!r}\n"
            f"   normalizált:  {sor.get('normalizalt')!r}\n"
            f"   réteg:        {sor.get('reteg')}\n"
            f"   eszköz:       {sor.get('eszkoz')}\n"
            f"   paraméterek:  {parameterek}\n"
            f"   bizonyosság:  {bizonyossag}\n"
            f"   válasz:       {sor.get('valasz_tipus')}"
        )
    return "\n\n".join(darabok)


class VasarloApp(tk.Tk):
    def __init__(self, db_path: str | None = None) -> None:
        super().__init__()
        self.title("Aprajafalva — időpontfoglalás")
        self.geometry("820x620")

        self.db_path = db_path or str(ALAP_DB_PATH)
        self.conn = migracio.conn_nyitas(self.db_path)
        migracio.migral(self.conn)

        orgs = torzsadat_repo.orgs_list(self.conn)
        self.org_id = orgs[0]["id"] if orgs else None
        self.session_id = new_uuid()
        # A beszélgetés eddigi sorai (ki, mit) — ezt kapja meg az
        # értelmező (ADR-019). A felület vezeti, mert csak ő ismeri a
        # ténylegesen kimondott magyar mondatokat.
        self.szo_elozmenyek: list[tuple[str, str]] = []
        self.orchestrator = Orchestrator(self.conn, alapertelmezett_ertelmezo(), org_id=self.org_id)

        # A beosztás időszaka — ehhez igazodik a nap-választó és a
        # szöveges út `most`-ja is (l. modul docstring).
        self.idoszak = (
            muszak_repo.slot_range(self.conn, org_id=self.org_id) if self.org_id else None
        )

        self.protocol("WM_DELETE_WINDOW", self._close)
        self._build()

    def _most_iso(self) -> str:
        """A szöveges út `most` értéke — a beosztáshoz horgonyozva
        (`horgony_most`), nem a nyers rendszeróra."""
        return horgony_most(self.idoszak, _most_iso())

    def _valaszthato_napok(self) -> list[str]:
        """A koppintós nap-választó értékei: a beosztás időszakának
        napjai. Beosztás nélkül a mai naptól számított hét nap — így a
        legördülő üres adatbázison sem marad üres."""
        if self.idoszak is None:
            return [(date.today() + timedelta(days=i)).isoformat() for i in range(7)]
        elso = date.fromisoformat(self.idoszak["elso_nap"])
        utolso = date.fromisoformat(self.idoszak["utolso_nap"])
        napok = (utolso - elso).days + 1
        return [
            (elso + timedelta(days=i)).isoformat() for i in range(min(napok, _NAP_VALASZTO_MAX))
        ]

    # ------------------------------------------------------------------
    # Felépítés
    # ------------------------------------------------------------------

    def _build(self) -> None:
        if self.org_id is None:
            ttk.Label(
                self,
                text="Nincs betöltött demóadat — futtasd: python feladat.py seed",
                padding=20,
                foreground="#a00",
            ).pack()
            return

        # Indító sor: melyik időszakra van beosztás, és mit jelent a
        # "ma" ezen a felületen. Ez az ELSŐ dolog, amit a próbálgató lát —
        # enélkül a demóadat távoli hete néma kudarcnak látszana.
        self.idoszak_cimke = ttk.Label(
            self,
            text=valasz_szoveg.rendszersor_szoveg(
                self.idoszak, self._most_iso(), _most_iso(), aktiv_modell_neve()
            ),
            padding=(12, 8),
            foreground="#046",
            wraplength=780,
        )
        self.idoszak_cimke.pack(anchor="w", fill="x")

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True)

        self.koppintos_tab = ttk.Frame(notebook, padding=12)
        self.szoveges_tab = ttk.Frame(notebook, padding=12)
        notebook.add(self.koppintos_tab, text="Koppintós út")
        notebook.add(self.szoveges_tab, text="Írjon nekünk")

        self._koppintos_build()
        self._szoveges_build()

    # ------------------------------------------------------------------
    # Koppintós út
    # ------------------------------------------------------------------

    def _koppintos_build(self) -> None:
        tab = self.koppintos_tab

        ttk.Label(tab, text="Bolt:").grid(row=0, column=0, sticky="w", pady=3)
        self._kop_bolt_nev_map = {
            katalogus.BOLT_NEVEK[slug]: slug for slug in katalogus.BOLT_SLUGOK
        }
        self.kop_bolt_valto = tk.StringVar()
        ttk.Combobox(
            tab,
            textvariable=self.kop_bolt_valto,
            values=sorted(self._kop_bolt_nev_map),
            state="readonly",
            width=20,
        ).grid(row=0, column=1, sticky="w", pady=3)

        ttk.Label(tab, text="Nap:").grid(row=1, column=0, sticky="w", pady=3)
        napok = self._valaszthato_napok()
        # Alapérték: a mai nap, HA a beosztásban van — különben a
        # beosztás első napja. Így a "Időpontok keresése" gomb az első
        # kattintásra is talál valamit (l. modul docstring).
        alap_nap = _most_iso()[:10] if _most_iso()[:10] in napok else (napok[0] if napok else "")
        self.kop_nap_valto = tk.StringVar(value=alap_nap)
        ttk.Combobox(
            tab, textvariable=self.kop_nap_valto, values=napok, state="readonly", width=20
        ).grid(row=1, column=1, sticky="w", pady=3)

        ttk.Label(tab, text="Napszak:").grid(row=2, column=0, sticky="w", pady=3)
        self.kop_napszak_valto = tk.StringVar(value="barmikor")
        napszak_keret = ttk.Frame(tab)
        napszak_keret.grid(row=2, column=1, sticky="w", pady=3)
        for ertek, cimke in _NAPSZAKOK:
            ttk.Radiobutton(
                napszak_keret, text=cimke, variable=self.kop_napszak_valto, value=ertek
            ).pack(side="left")

        ttk.Button(tab, text="Időpontok keresése", command=self._kop_kereses).grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(10, 0)
        )

        # A nyugtázó sor — a hangcsatorna töltelékmondatának szöveges
        # próbája (docs/blueprint.md 7. szakasz, "Kétlépcsős válasz").
        # Külön mező a hibaüzenettől (`kop_uzenet`), más színnel, hogy a
        # kettő ne keveredjen.
        self.kop_nyugtazo = ttk.Label(tab, text="", foreground="#555", wraplength=700)
        self.kop_nyugtazo.grid(row=4, column=0, columnspan=2, sticky="w", pady=(8, 0))

        self.kop_uzenet = ttk.Label(tab, text="", foreground="#a00", wraplength=700)
        self.kop_uzenet.grid(row=5, column=0, columnspan=2, sticky="w")

        self.kop_tartalom = ttk.Frame(tab, padding=(0, 10))
        self.kop_tartalom.grid(row=6, column=0, columnspan=2, sticky="w")

    def _kop_kereses(self) -> None:
        bolt_slug = self._kop_bolt_nev_map.get(self.kop_bolt_valto.get())
        nap = self.kop_nap_valto.get()
        if not bolt_slug or not nap:
            self.kop_uzenet.config(text=valasz_szoveg.hiba_szoveg("hianyzo_bolt_es_nap"))
            return
        self.kop_uzenet.config(text="")

        parameterek = {
            "bolt_id": bolt_slug,
            "datum_tol": f"{nap}T00:00:00Z",
            "datum_ig": f"{nap}T23:59:59Z",
            "napszak": self.kop_napszak_valto.get(),
        }
        # A koppintós úton a felismert ablak megegyezik a gombokkal
        # kiválasztott paraméterekkel — nincs szükség parszolásra, de a
        # nyugtázó sor elve ugyanaz, mint a szöveges úton.
        self.kop_nyugtazo.config(text=valasz_szoveg.nyugtazo_szoveg(parameterek))
        self.update_idletasks()

        valasz = self.orchestrator.kereses_strukturaltan(self.session_id, parameterek)
        self._eredmeny_render(self.kop_tartalom, valasz, self.kop_uzenet)

    # ------------------------------------------------------------------
    # Közös: jelölt-lista, választás, megerősítés (mindkét út innen ágazik)
    # ------------------------------------------------------------------

    def _eredmeny_render(self, keret: ttk.Frame, valasz: dict, uzenet_label: ttk.Label) -> None:
        for widget in keret.winfo_children():
            widget.destroy()

        if valasz.get("tipus") == "ajanlat":
            for jelolt in valasz["jeloltek"]:
                ttk.Button(
                    keret,
                    text=_idopont_cimke(jelolt["kezdet"], jelolt["veg"]),
                    command=lambda s=jelolt["slot_id"]: self._jelolt_valaszt(
                        keret, s, uzenet_label
                    ),
                ).pack(anchor="w", pady=2)
            return

        if not valasz.get("sikeres", True):
            kulcs = valasz.get("uzenet_kulcs", "")
            uzenet_label.config(text=valasz_szoveg.hiba_szoveg(kulcs))
            return

        # Egyéb sikeres eszközválasz (bolt_info, foglalas_lemondas, ...)
        ttk.Label(keret, text=valasz_szoveg.tenyvalasz_szoveg(valasz), wraplength=680).pack(
            anchor="w"
        )

    def _jelolt_valaszt(self, keret: ttk.Frame, slot_id: str, uzenet_label: ttk.Label) -> None:
        valasz = self.orchestrator.valaszt(self.session_id, slot_id)
        if valasz.get("tipus") != "megerositest_ker":
            uzenet_label.config(
                text=valasz_szoveg.hiba_szoveg(valasz.get("uzenet_kulcs", "ismeretlen_valasz"))
            )
            return

        for widget in keret.winfo_children():
            widget.destroy()

        ttk.Label(keret, text=valasz_szoveg.megerosites_ker_szoveg()).pack(anchor="w")
        ttk.Label(keret, text="Azonosító (számsor):").pack(anchor="w", pady=(6, 0))
        azonosito_valto = tk.StringVar()
        ttk.Entry(keret, textvariable=azonosito_valto, width=24).pack(anchor="w")

        gombsor = ttk.Frame(keret, padding=(0, 8))
        gombsor.pack(anchor="w")
        ttk.Button(
            gombsor,
            text="Igen, foglalom",
            command=lambda: self._megerosit(keret, uzenet_label, azonosito_valto.get()),
        ).pack(side="left", padx=(0, 6))
        ttk.Button(gombsor, text="Mégse", command=lambda: self._elvet(keret, uzenet_label)).pack(
            side="left"
        )

    def _megerosit(self, keret: ttk.Frame, uzenet_label: ttk.Label, azonosito_bevitel: str) -> None:
        if not azonosito_bevitel.strip():
            uzenet_label.config(text=valasz_szoveg.hiba_szoveg("hianyzo_azonosito_bevitel"))
            return
        kulcs_hash = ideiglenes_hash(azonosito_bevitel)
        valasz = self.orchestrator.megerosit(self.session_id, kulcs_hash)
        for widget in keret.winfo_children():
            widget.destroy()
        if valasz.get("tipus") == "visszaigazolas":
            ttk.Label(
                keret,
                text=valasz_szoveg.sikeres_foglalas_szoveg(valasz["foglalasi_kod"]),
                font=("TkDefaultFont", 11, "bold"),
            ).pack(anchor="w")
        else:
            kulcs = valasz.get("uzenet_kulcs", "")
            uzenet_label.config(text=valasz_szoveg.hiba_szoveg(kulcs))

    def _elvet(self, keret: ttk.Frame, uzenet_label: ttk.Label) -> None:
        self.orchestrator.elvet(self.session_id)
        for widget in keret.winfo_children():
            widget.destroy()
        uzenet_label.config(text=valasz_szoveg.elvetve_szoveg())

    # ------------------------------------------------------------------
    # Szöveges út
    # ------------------------------------------------------------------

    def _szoveges_build(self) -> None:
        tab = self.szoveges_tab

        self.szo_naplo = tk.Text(tab, height=18, wrap="word", state="disabled")
        self.szo_naplo.pack(fill="both", expand=True)

        also_sor = ttk.Frame(tab, padding=(0, 8))
        also_sor.pack(fill="x")
        self.szo_beviteli_valto = tk.StringVar()
        bevitel = ttk.Entry(also_sor, textvariable=self.szo_beviteli_valto)
        bevitel.pack(side="left", fill="x", expand=True)
        bevitel.bind("<Return>", lambda _e: self._szo_kuldes())
        ttk.Button(also_sor, text="Küldés", command=self._szo_kuldes).pack(side="left", padx=(6, 0))

        self.szo_gombsor = ttk.Frame(tab, padding=(0, 4))
        self.szo_gombsor.pack(fill="x")
        self.szo_jelolt_keret = ttk.Frame(tab, padding=(0, 4))
        self.szo_jelolt_keret.pack(fill="x")
        self.szo_uzenet = ttk.Label(tab, text="", foreground="#a00", wraplength=700)
        self.szo_uzenet.pack(anchor="w")

        # Várakozás-jelző: a modellhívás fordulónként több másodperc is
        # lehet (ADR-018 mérés: ~8 s), és addig a Tkinter ablak
        # mozdulatlan. Jelzés nélkül ez lefagyásnak látszik. A mondatot
        # itt sem a felület fogalmazza — a `nyugtazo` sablonok
        # "általános" változata megy, ugyanaz, amit a hangcsatorna is
        # használna töltelékmondatnak.
        self.szo_allapot = ttk.Label(tab, text="", foreground="#555")
        self.szo_allapot.pack(anchor="w")

        also_gombsor = ttk.Frame(tab, padding=(0, 6))
        also_gombsor.pack(anchor="w")
        # Tesztelés közben ez mutatja meg, MI történt: melyik réteg
        # oldotta meg, minek értette, mennyire volt biztos benne.
        ttk.Button(also_gombsor, text="Napló megnyitása", command=self._naplo_ablak).pack(
            side="left", padx=(0, 6)
        )
        # A szándék kemény része (bolt, szolgáltatás) fordulók között
        # ÉLETBEN MARAD (`orchestrator.kovetkezo_kontextus`) — ez a
        # helyes viselkedés alkudozásnál, de próbálgatás közben azt
        # jelenti, hogy az előző próba boltja beleszól a következőbe.
        # Enélkül minden próbához újra kellene indítani az ablakot.
        ttk.Button(also_gombsor, text="Új beszélgetés", command=self._uj_beszelgetes).pack(
            side="left"
        )

    def _uj_beszelgetes(self) -> None:
        """Friss session: a szándék kemény része sem öröklődik tovább.
        A szöveges naplót is üríti, hogy látszódjon, hol kezdődik az új
        próba."""
        self.session_id = new_uuid()
        self.szo_elozmenyek.clear()
        for keret in (self.szo_gombsor, self.szo_jelolt_keret):
            for widget in keret.winfo_children():
                widget.destroy()
        self.szo_uzenet.config(text="")
        self.szo_naplo.config(state="normal")
        self.szo_naplo.delete("1.0", "end")
        self.szo_naplo.config(state="disabled")

    def _naplo_ablak(self) -> None:
        """A `naplo/probak.jsonl` eddigi próbái egy külön ablakban. A
        tartalmat a `proba_naplo_szoveg()` állítja elő — ez a metódus
        csak megjeleníti (a formázás Tkinter nélkül is tesztelhető)."""
        ablak = tk.Toplevel(self)
        ablak.title("Próba-napló — naplo/probak.jsonl")
        ablak.geometry("760x520")
        szoveg = tk.Text(ablak, wrap="word")
        szoveg.pack(fill="both", expand=True)
        szoveg.insert("end", proba_naplo_szoveg(proba_naplo_olvas()))
        szoveg.config(state="disabled")

    # A kiút-gombok mögötti, előre megírt mondatok: a választás egy új
    # fordulóként megy vissza az orchestratorba, hogy onnantól a szokásos
    # út fusson (értelmező → állapotgép), ne külön ág.
    _KIUT_MONDAT = {
        "bolt": "másik boltban szeretnék",
        "het": "jövő héten szeretnék",
        "napszak": "bármikor jó, bármelyik napszakban",
    }

    def _kiut_valasztas(self, dimenzio: str) -> None:
        mondat = self._KIUT_MONDAT.get(dimenzio)
        if mondat:
            self._szo_kuldes(mondat)

    def _alternativa_felajanl(self, dimenzio: str | None) -> None:
        """Ha az eszköz talált alternatívát (`alternativ_dimenzio`),
        felajánljuk KOPPINTHATÓ gombként — a vásárlónak nem kell újra
        megfogalmaznia a kérést (blueprint 1. szakasz, 5. igény: "ha
        nincs hely, alternatíva jöjjön"). A mondatot és a gombfeliratot
        az `assistant/valasz/` adja, ez a modul nem fogalmaz."""
        szovegek = valasz_szoveg.alternativa_szoveg(dimenzio)
        if szovegek is None:
            return
        bevezetes, gomb_felirat = szovegek
        self._naplo_ir("Rendszer", bevezetes)
        ttk.Button(
            self.szo_gombsor,
            text=gomb_felirat,
            command=lambda d=dimenzio: self._alternativa_kereses(d),
        ).pack(side="left", padx=(0, 6))

    def _alternativa_kereses(self, dimenzio: str) -> None:
        for widget in self.szo_gombsor.winfo_children():
            widget.destroy()
        valasz = self.orchestrator.alternativa_kereses(self.session_id, dimenzio)
        self._szoveges_valasz_kezel(valasz)

    def _naplo_ir(self, ki_be: str, szoveg: str) -> None:
        self.szo_naplo.config(state="normal")
        self.szo_naplo.insert("end", f"{ki_be}: {szoveg}\n")
        self.szo_naplo.config(state="disabled")
        self.szo_naplo.see("end")
        # Ami a képernyőn megjelenik, az kerül a beszélgetés-előzménybe
        # is (ADR-019) — a rendszer mondatai ugyanúgy, mint a vásárlóé:
        # enélkül a modell nem tudná, MIÉRT kérdez a vásárló másik napot
        # ("nincs szabad időpont kedden").
        self._elozmenyhez_ad(KI_VASARLO if ki_be == _TE_CIMKE else KI_RENDSZER, szoveg)

    def _elozmenyhez_ad(self, ki: str, szoveg: str) -> None:
        """Egy sor a beszélgetés-előzményhez, a legutóbbi fordulókra
        vágva. A vágás azért kell, mert a prompt hossza latencia
        (`docs/PLATFORM_TANULSAGOK.md`), és mert négy fordulónál régebbi
        előzmény már ritkán befolyásolja az aktuális mondatot."""
        self.szo_elozmenyek.append((ki, szoveg))
        del self.szo_elozmenyek[:-_ELOZMENY_SOROK]

    def _szo_kuldes(self, elore_kitoltott: str | None = None) -> None:
        szoveg = elore_kitoltott if elore_kitoltott is not None else self.szo_beviteli_valto.get()
        if not szoveg.strip():
            return
        self.szo_beviteli_valto.set("")
        # Az értelmező az ELŐZŐ fordulókat kapja meg — az aktuális
        # mondat külön megy (`beszelgetes_szovege` teszi a végére), így
        # nem duplázódik.
        elozmenyek = list(self.szo_elozmenyek)
        self._naplo_ir(_TE_CIMKE, szoveg)

        # MINDKÉT gombkeretet ürítjük, nem csak a kiút-gombokat: a
        # korábbi forduló időpont-gombjai különben a képernyőn maradnának
        # egy olyan válasz mellett, aminek semmi köze hozzájuk (pl. egy
        # lemondás-kérdés alatt ott állna három foglalható időpont) — és
        # rájuk kattintva egy már lezárt ajánlatból választana a vásárló.
        for keret in (self.szo_gombsor, self.szo_jelolt_keret):
            for widget in keret.winfo_children():
                widget.destroy()
        self.szo_uzenet.config(text="")

        self.szo_allapot.config(text=valasz_szoveg.nyugtazo_szoveg({}))
        self.update_idletasks()

        valasz = self.orchestrator.fordulo(
            self.session_id, szoveg, self._most_iso(), elozmenyek=elozmenyek
        )
        self.szo_allapot.config(text="")
        _proba_naplo_ir(
            szoveg,
            self.orchestrator.utolso_ertelmezes,
            getattr(self.orchestrator.ertelmezo, "utolso_reteg", None),
            normalizalt=getattr(self.orchestrator.ertelmezo, "utolso_normalizalt", None),
            valasz_tipus=valasz.get("tipus") or ("sikeres" if valasz.get("sikeres") else "hiba"),
        )
        self._szoveges_valasz_kezel(valasz)

    def _szoveges_valasz_kezel(self, valasz: dict) -> None:
        tipus = valasz.get("tipus")

        if tipus == "elutasitas":
            self._naplo_ir("Rendszer", valasz_szoveg.hiba_szoveg(valasz["uzenet_kulcs"]))
            return

        if tipus == "kiut":
            # Ugyanaz a válasz harmadszor nem megy ki — más mondat, zárt
            # választással (blueprint 7. szakasz, "Négy technika" 2.).
            # A frusztráció-figyelő MÁSODIK kiútja embert ajánl, nem
            # újabb szűkítést — ott nincs gomb, csak a mondat.
            if valasz.get("emberhez"):
                self._naplo_ir("Rendszer", valasz_szoveg.hiba_szoveg(valasz["uzenet_kulcs"]))
                return
            bevezetes, gombok = valasz_szoveg.kiut_szoveg(valasz.get("valaszthato_dimenziok", []))
            self._naplo_ir("Rendszer", bevezetes)
            for dimenzio, felirat in gombok:
                ttk.Button(
                    self.szo_gombsor,
                    text=felirat,
                    command=lambda d=dimenzio: self._kiut_valasztas(d),
                ).pack(side="left", padx=(0, 6))
            return

        if tipus == "visszakerdezes":
            hianyzo = valasz.get("hianyzo_mezo")
            self._naplo_ir("Rendszer", valasz_szoveg.visszakerdezes_szoveg(hianyzo))
            valasztek = valasz.get("valaszthato_ertekek") or []
            if valasz.get("kerdes_tipusa") == "zart" and valasztek:
                for ertek in valasztek:
                    cimke = katalogus.BOLT_NEVEK.get(ertek, ertek)
                    ttk.Button(
                        self.szo_gombsor,
                        text=cimke,
                        command=lambda e=ertek: self._szo_kuldes(e),
                    ).pack(side="left", padx=(0, 6))
            return

        if tipus == "ajanlat":
            # A nyugtázó sor — a hangcsatorna töltelékmondatának szöveges
            # próbája (docs/blueprint.md 7. szakasz) — külön naplósorban,
            # MIELŐTT a tényleges (tartalmi) eredmény megjelenik.
            self._naplo_ir(
                "Rendszer", valasz_szoveg.nyugtazo_szoveg(valasz.get("felismert_ablak", {}))
            )
            self._naplo_ir(
                "Rendszer",
                valasz_szoveg.ajanlat_bevezetes_legkozelebbi_szoveg()
                if valasz.get("legkozelebbi")
                else valasz_szoveg.ajanlat_bevezetes_szoveg(),
            )
            self._eredmeny_render(self.szo_jelolt_keret, valasz, self.szo_uzenet)
            return

        if tipus == "eszkoz_hiba" or not valasz.get("sikeres", True):
            if valasz.get("felismert_ablak"):
                self._naplo_ir("Rendszer", valasz_szoveg.nyugtazo_szoveg(valasz["felismert_ablak"]))
            kulcs = valasz.get("uzenet_kulcs", "")
            self._naplo_ir("Rendszer", valasz_szoveg.hiba_szoveg(kulcs))
            self._alternativa_felajanl(valasz.get("alternativ_dimenzio"))
            return

        if valasz.get("sikeres"):
            self._naplo_ir("Rendszer", valasz_szoveg.tenyvalasz_szoveg(valasz))
            return

        self._naplo_ir("Rendszer", valasz_szoveg.hiba_szoveg("ismeretlen_valasz"))

    # ------------------------------------------------------------------

    def _close(self) -> None:
        self.conn.close()
        self.destroy()


def main() -> int:
    app = VasarloApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
