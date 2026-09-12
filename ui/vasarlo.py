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

**KIMENETI MÓD-kapcsoló a szöveges fülön** (M6, hang-előkészítés): a
`szoveges` a mai viselkedés, a `beszelheto` az, amit egy felolvasó
kapna — egész mondatok, kimondott számokkal, fordulónként legfeljebb két
mondattal és egy kérdéssel (`assistant/valasz/beszelheto.py`). A
kapcsoló azért van itt, mert **hang nélkül is meg kell tudni nézni, mit
fog hallani a vásárló**: a beszélhető mód szövegben kipróbálható, és
ettől tesztelhető is. Két következménye van a felületre:

- a rendszer mondatai fordulónként ÖSSZEGYŰJTVE mennek ki (egy
  megszólalás, nem három sor) — `_rendszer_mondat` / `_rendszer_flush`;
- a nyugtázó sor KIMARAD az összegyűjtésből, mert az a kétlépcsős
  válasz ELSŐ lépcsője (blueprint 7.), külön megszólalás — nem foghatja
  el a tartalmi válasz kétmondatos keretét.

A koppintós út mód-kapcsoló nélkül marad: ott a képernyő maga a válasz
(gombok, listák), hangon pedig nincs koppintás.

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
import os
import sys
import threading
import time
import tkinter as tk
import webbrowser
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from tkinter import ttk

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from assistant import hang  # noqa: E402
from assistant import valasz as valasz_szoveg  # noqa: E402
from assistant.interpreter import (  # noqa: E402
    KI_RENDSZER,
    KI_VASARLO,
    aktiv_modell_neve,
    alapertelmezett_ertelmezo,
    elomelegites,
    indito_ellenorzes,
)
from assistant.orchestrator import Orchestrator  # noqa: E402
from assistant.tools import katalogus  # noqa: E402
from assistant.valasz import helyi_ido  # noqa: E402
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

PROBA_NAPLO_UTVONAL = ROOT / "naplo" / "probak.jsonl"
# Az ARCHIVÁLT naplók ugyanabban a könyvtárban, dátumozott néven élnek
# (`probak-20260831-195812.jsonl`) — a minta az, ami alapján a
# `proba_naplo_archivumok()` megtalálja őket. Nem külön könyvtár: a napló
# egy fájl, az archívuma ugyanaz a fájl máskor, és egy `naplo/` listázás
# így magától időrendben mutatja őket.
_ARCHIVUM_MINTA = "probak-*.jsonl"
_ARCHIVUM_IDOBELYEG = "%Y%m%d-%H%M%S"

# A szöveges napló "Te:" előtagja — ebből tudja a `_naplo_ir`, hogy a
# sor a vásárlóé-e vagy a rendszeré (a beszélgetés-előzményhez, ADR-019).
_TE_CIMKE = "Te"

# Hány NAPLÓSOR megy át előzményként az értelmezőnek.
#
# **Ez már nem az ablak** (ADR-025): a vágást az értelmező oldalán a
# csúszó előzmény-ablak végzi (`assistant/interpreter/ablak.py`) — az
# utolsó néhány forduló szó szerint, a régebbiek egy összefoglaló
# sorban. Ez a szám csak azt mondja meg, meddig ér vissza az a
# nyersanyag, amiből az összefoglaló készülhet.
#
# Korábban 12 volt, és EGYBEN az ablak is: ami kicsúszott, az
# nyomtalanul elveszett — a legelső mondatban kimondott bolttal együtt.
# Most a régebbi fordulók összefoglalva élnek tovább, ezért érdemes
# többet átadni, mint amennyi szó szerint elmegy.
_ELOZMENY_SOROK = 60


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


def _idopont_cimke(kezdet_iso: str, veg_iso: str, zona: str | None) -> str:
    """Egy jelölt gombfelirata — HELYI idővel, időzóna-jelölés nélkül.

    2026-09-20-ig ez állt a gombon: `2026-12-21 07:00–07:10 (UTC)`. A
    demóadat boltjai 8 órakor nyitnak, tehát a vásárló minden időpontot
    egy órával korábbinak látott a valóságosnál (nyáron kettővel), és a
    felolvasó is így mondta. Nem formázási hiba volt: **rossz időpontot
    mondtunk** (`assistant/valasz/helyi_ido.py`).

    A dátum marad ISO-alakban: a gombok egymás alatt állnak, ott az
    azonos szélesség segít. A ZÓNA nem jelenik meg — a vásárlónak nincs
    dolga az időzónákkal, az ő ideje a falióra."""
    kezdet = helyi_ido.helyi_iso(kezdet_iso, zona)
    veg = helyi_ido.helyi_iso(veg_iso, zona)
    return f"{kezdet[:10]} {kezdet[11:16]}–{veg[11:16]}"


def _proba_naplo_ir(
    bemenet: str,
    ertelmezes: dict | None,
    reteg: str | None,
    *,
    normalizalt: str | None = None,
    valasz_tipus: str | None = None,
    valaszido_masodperc: float | None = None,
    uzenet_kulcs: str | None = None,
    kapuor_ok: str | None = None,
    egyetertes: int | None = None,
    modell: str | None = None,
    prompt_verzio: str | None = None,
    allapot: dict | None = None,
    nyomkovetes: dict | None = None,
    session_id: str | None = None,
) -> None:
    """Egy fordulót ír a `naplo/probak.jsonl`-be — l. modul docstring,
    "Próba-napló". A mezők azért ennyien vannak, mert tesztelés közben
    mindegyik kérdés külön felmerül: mit írtam be, mit LÁTOTT belőle a
    rendszer (`normalizalt`), ki oldotta meg (`reteg`), minek értette
    (`eszkoz`, `parameterek`), mennyire volt biztos benne
    (`bizonyossag`), mi lett belőle (`valasz_tipus`, `uzenet_kulcs`),
    mennyi ideig tartott (`valaszido_masodperc`), és mikor
    (`idobelyeg`).

    **Az utolsó négy mező a napló-elemzőért került be**
    (`tools/naplo_elemzo.py`, `python feladat.py naplo`): válaszidő
    nélkül nem lehet átlagot és p95-öt számolni, `uzenet_kulcs` és
    `kapuor_ok` nélkül a hibaminták csak típus-szinten látszanának
    ("elutasítás" — de miért?), `egyetertes` nélkül pedig az
    önkonzisztencia hatása mérhetetlen lenne éles használat közben.
    Mind a négy opcionális: a régi naplósorok is olvashatók maradnak.

    **A `nyomkovetes` a beszélgetés-elemzőé** (`tools/
    beszelgetes_riport.py`, `python feladat.py riport`): a modellhez
    ténylegesen elküldött prompt, a nyers modellválasz, a
    séma-ellenőrzés eredménye, a dátumfeloldás három adata (mit adott a
    modell, mit a parser, melyik nyert), a lépésenkénti idő, a
    mezőnkénti forrás, és a kimenő válasz MINDKÉT módban. Ezek egyike
    sem fér el egy naplósor olvasható alakjában — az elemző viszont
    összecsukható blokkokban meg tudja mutatni őket.

    **REDAKTÁLÁS TÁROLÁS ELŐTT** (CLAUDE.md 2. invariáns, ADR-005): a
    vásárló mondata és az abból kinyert paraméterek egyaránt átmennek a
    `privacy/redakcio`-n, MIELŐTT lemezre kerülnének. **A
    nyomkövetés is** — és ott ez még fontosabb: a prompt SZÓ SZERINT
    tartalmazza a beszélgetés utolsó fordulóit, tehát mindent, amit a
    vásárló bediktált. Ez nem elméleti
    óvatosság: a robusztussági halmaz "személyes adat" kategóriája
    pontosan azt méri, mi történik, ha valaki KÉRETLENÜL bediktálja a
    telefonszámát — enélkül a szám nyersen kerülne a naplófájlba, és
    soha nem kértük."""
    PROBA_NAPLO_UTVONAL.parent.mkdir(parents=True, exist_ok=True)
    sor = {
        "idobelyeg": _most_iso(),
        # MELYIK BESZÉLGETÉS. Enélkül a napló FORDULÓK listája volt, nem
        # beszélgetéseké: az „új beszélgetés" gomb nem hagyott nyomot,
        # tehát utólag csak az időbélyegek közti szünetből lehetett
        # sejteni, hol ér véget az egyik menet és hol kezdődik a másik.
        # Egy útvonal viszont csak azon belül értelmezhető: az állapot,
        # a megőrzött paraméterek és az előzmény mind a session-höz
        # tartoznak (`tools/utvonal.py`).
        #
        # A session-azonosító UUID, nem vásárlói adat — nem redaktáljuk,
        # de nem is köthető személyhez: minden indításnál új.
        "session_id": session_id,
        "bemenet": redaktal(bemenet),
        "normalizalt": redaktal(normalizalt),
        "reteg": reteg,
        "eszkoz": (ertelmezes or {}).get("eszkoz"),
        "parameterek": redaktal_ertekek((ertelmezes or {}).get("parameterek")),
        "bizonyossag": (ertelmezes or {}).get("bizonyossag"),
        "valasz_tipus": valasz_tipus,
        "uzenet_kulcs": uzenet_kulcs,
        "kapuor_ok": kapuor_ok,
        "egyetertes": egyetertes,
        # MELYIK MODELL és MELYIK PROMPT — fordulónként, nem futásonként.
        # A `reteg` mező csak azt mondja meg, KI oldotta meg a fordulót;
        # abból nem derül ki, hogy a tartalék azért dolgozott-e, mert
        # nem volt konfigurált modell, vagy mert a modell nem tudta
        # megoldani. Ez a két eset egy hét múlva, a naplóból nézve
        # megkülönböztethetetlen volt — pedig az egyik konfigurációs
        # hiba, a másik mérési eredmény.
        "modell": modell,
        "prompt_verzio": prompt_verzio,
        # ÁLLAPOT ÉS ÁTMENET (ADR-028). A `valasz_tipus` megmondja, mi
        # történt EBBEN a fordulóban; az állapot azt, hogy a beszélgetés
        # hol tartott előtte és hova jutott. Egy furcsa menetről eddig
        # csak a válaszok sorrendjéből lehetett kitalálni, hol tévedt el.
        "allapot": (allapot or {}).get("utana"),
        "atmenet": (
            f"{allapot['elotte']} -> {allapot['utana']}"
            if allapot and allapot.get("valtozott")
            else None
        ),
        "valaszido_masodperc": (
            None if valaszido_masodperc is None else round(valaszido_masodperc, 3)
        ),
        "nyomkovetes": redaktal_ertekek(nyomkovetes) if nyomkovetes else None,
    }
    with PROBA_NAPLO_UTVONAL.open("a", encoding="utf-8") as fajl:
        fajl.write(json.dumps(sor, ensure_ascii=False) + "\n")


def proba_naplo_olvas(utolso: int | None = None, utvonal: Path | None = None) -> list[dict]:
    """A próba-napló sorai, legrégebbitől a legújabbig. `utolso`
    megadásakor csak az utolsó N sor. Hiányzó fájl esetén üres lista —
    ez nem hiba, csak azt jelenti, hogy még nem volt forduló.

    `utvonal`: egy ARCHIVÁLT napló (`naplo/probak-20260831-195812.jsonl`)
    olvasásához — enélkül a jelenlegi naplót olvassa. Az elemző és a
    riport ezen keresztül kapja a `--fajl` kapcsolót: az archiválás
    (`proba_naplo_archival`) különben elvágná a hozzáférést attól, amit
    épp megőrizni akartunk.

    A sérült (nem JSON) sorokat átugorja: a napló megnyitása SOHA ne
    boruljon fel attól, hogy egy korábbi futás félbeszakadt."""
    fajl_utvonal = utvonal or PROBA_NAPLO_UTVONAL
    if not fajl_utvonal.exists():
        return []
    sorok = []
    for nyers in fajl_utvonal.read_text(encoding="utf-8").splitlines():
        if not nyers.strip():
            continue
        try:
            sorok.append(json.loads(nyers))
        except json.JSONDecodeError:
            continue
    return sorok[-utolso:] if utolso else sorok


def proba_naplo_archivumok() -> list[Path]:
    """Az archivált naplók, LEGÚJABBTÓL a legrégebbi felé. A név
    tartalmazza az időbélyeget, ezért a névsor fordítottja egyben
    időrend is — nem a fájlrendszer módosítási idejére támaszkodunk,
    ami egy másolás vagy egy git-művelet után hazudna."""
    return sorted(PROBA_NAPLO_UTVONAL.parent.glob(_ARCHIVUM_MINTA), reverse=True)


def proba_naplo_archival(most: datetime | None = None) -> Path | None:
    """A jelenlegi naplót dátumozott néven félreteszi, és üres naplóval
    indul újra. Az archív fájl útvonalát adja vissza, vagy `None`-t, ha
    nem volt mit archiválni (nincs fájl, vagy üres).

    **Átnevezés, nem másolás:** a napló egyetlen író folyamata a
    felület, és az átnevezés után a következő forduló egyszerűen új
    fájlt nyit (`_proba_naplo_ir` `"a"` módban) — nincs olyan pillanat,
    amikor egy sor mindkét fájlban benne van, vagy egyikben sem.

    Miért kell egyáltalán: a napló a próbák nyersanyaga (rejtett golden
    halmaz, `tools/naplo_elemzo.py`), és egy hosszú próbasorozat számai
    összemosódnak az előzőével, ha ugyanabba a fájlba folynak. Az
    archiválás a mérési határ kijelölése — a régi számok megmaradnak,
    csak nem keverednek az újakkal."""
    if (
        not PROBA_NAPLO_UTVONAL.exists()
        or not PROBA_NAPLO_UTVONAL.read_text(encoding="utf-8").strip()
    ):
        return None
    idobelyeg = (most or datetime.now(UTC)).strftime(_ARCHIVUM_IDOBELYEG)
    cel = PROBA_NAPLO_UTVONAL.with_name(f"probak-{idobelyeg}.jsonl")
    # Ütközés csak akkor lehet, ha egy másodpercen belül kétszer
    # archiválunk — a betűs utótag ezt is elviseli, ahelyett hogy
    # felülírná az előbbit.
    utotag = 0
    while cel.exists():
        utotag += 1
        cel = PROBA_NAPLO_UTVONAL.with_name(f"probak-{idobelyeg}-{utotag}.jsonl")
    PROBA_NAPLO_UTVONAL.rename(cel)
    return cel


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
            + (f" ({sor['uzenet_kulcs']})" if sor.get("uzenet_kulcs") else "")
            + (f"\n   kapuőr:       {sor['kapuor_ok']}" if sor.get("kapuor_ok") else "")
            + (
                f"\n   válaszidő:    {sor['valaszido_masodperc']} s"
                if sor.get("valaszido_masodperc") is not None
                else ""
            )
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
        # A SZERVEZET IDŐZÓNÁJA — minden képernyőre kerülő és minden
        # felolvasott időpont ezen megy át (`helyi_ido.py`). A tárolás
        # UTC marad (CLAUDE.md 4. invariáns); helyi idő csak itt, a
        # megjelenítésnél keletkezik.
        org = torzsadat_repo.org_load(self.conn, self.org_id) if self.org_id else None
        self.zona = org["idozona"] if org else None
        self.session_id = new_uuid()
        # A beszélgetés eddigi sorai (ki, mit) — ezt kapja meg az
        # értelmező (ADR-019). A felület vezeti, mert csak ő ismeri a
        # ténylegesen kimondott magyar mondatokat.
        self.szo_elozmenyek: list[tuple[str, str]] = []
        # A forduló alatt gyűlő rendszer-mondatok (csak beszélhető
        # módban telik meg) — l. modul docstring, "KIMENETI MÓD".
        self._rendszer_puffer: list[str] = []
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

    def _elomelegit(self) -> None:
        """A modell betöltése a HÁTTÉRBEN, indításkor.

        Az első éles próbában az első forduló 13,93 s volt, a többi
        3,5 s körül — a különbség a modell betöltése. Épp az első
        mondatnál a legdrágább: ott a vásárló még azt sem tudja, hogy
        működik-e a rendszer.

        A szál `daemon`, tehát az ablak bezárását nem várakoztatja, és
        a hibát elnyeli: ha nincs modell vagy nem fut a szolgáltatás,
        az indítási ellenőrzés már úgyis szólt róla."""
        if aktiv_modell_neve() is None:
            return
        self.melegites_cimke.config(text="modell: melegítés…", foreground="#7a3b00")

        def dolgozik() -> None:
            kezdet = time.monotonic()
            siker = elomelegites()
            telt = time.monotonic() - kezdet
            szoveg = f"modell: kész ({telt:.1f} s)" if siker else "modell: nem válaszol"
            szin = "#2d6a2d" if siker else "#a00"
            self.after(0, lambda: self.melegites_cimke.config(text=szoveg, foreground=szin))

        threading.Thread(target=dolgozik, daemon=True).start()

    def _indito_ellenorzes(self) -> bool:
        """MODÁLIS ellenőrzés indításkor: konfigurálva van-e a modell, és
        válaszol-e az Ollama. `True`, ha mehet tovább a felépítés.

        **Miért nem elég a sárga sáv.** Háromszor futott végig kézi
        próba a tartalék ágon úgy, hogy csak utólag derült ki — egy
        figyelmeztető sávot el lehet olvasni és el lehet felejteni,
        főleg ha a beszélgetés egyébként értelmes válaszokat ad. Itt
        DÖNTENI kell: a „Folytatom tartalékággal" érvényes választás
        (pl. amikor épp a determinisztikus réteget próbáljuk), csak nem
        lehet véletlen.

        **A szöveget nem ez a modul fogalmazza** (`assistant/valasz/
        __init__.py::indito_ellenorzes_szoveg`), és a modell-állapotot
        sem ez kérdezi le (`assistant/interpreter::indito_ellenorzes`) —
        a felület csak megjeleníti a kettőt.

        Az ellenőrzés KIHAGYHATÓ az `APRAJAFALVA_INDITO_ELLENORZES=ki`
        környezeti változóval: a fej nélküli végigjátszás
        (`tools/vegigjatszas.py`) és az automata tesztek nem tudnak
        gombot nyomni, és nem is nekik szól a kérdés."""
        if os.environ.get("APRAJAFALVA_INDITO_ELLENORZES") == "ki":
            return True
        allapot = indito_ellenorzes()
        szovegek = valasz_szoveg.indito_ellenorzes_szoveg(
            getattr(allapot, "hiany", None), getattr(allapot, "modell", None)
        )
        if szovegek is None:
            return True
        cim, uzenet, folytatas_cimke, kilepes_cimke = szovegek

        ablak = tk.Toplevel(self)
        ablak.title(cim)
        ablak.transient(self)
        ablak.resizable(False, False)
        tk.Label(
            ablak,
            text=uzenet,
            justify="left",
            anchor="w",
            wraplength=560,
            padx=16,
            pady=14,
        ).pack(fill="x")
        gombsor = ttk.Frame(ablak, padding=(16, 0, 16, 14))
        gombsor.pack(fill="x")

        dontes = {"folytat": False}

        def folytat() -> None:
            dontes["folytat"] = True
            ablak.destroy()

        # A KILÉPÉS az alapértelmezett (az ablak bezárása és az Escape is
        # ide fut): ha valaki gondolkodás nélkül elüti a kérdést, ne az
        # legyen az eredmény, hogy észrevétlenül tartalékágon mér.
        ttk.Button(gombsor, text=folytatas_cimke, command=folytat).pack(side="left")
        ttk.Button(gombsor, text=kilepes_cimke, command=ablak.destroy).pack(side="right")
        ablak.bind("<Escape>", lambda _esemeny: ablak.destroy())
        ablak.protocol("WM_DELETE_WINDOW", ablak.destroy)

        ablak.grab_set()
        self.wait_window(ablak)
        if not dontes["folytat"]:
            self.after(0, self._close)
            return False
        return True

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
        modell_nev = aktiv_modell_neve()

        # INDÍTÁSI ELLENŐRZÉS — a sárga sáv nem volt elég (l.
        # `_indito_ellenorzes`). Ha a válasz „Kilépek", az ablak itt
        # bezárul, és a szöveges fül el sem indul.
        if not self._indito_ellenorzes():
            return

        # NINCS MODELL — a legfeltűnőbb sor az ablakban, a többi FÖLÖTT.
        # A tartalék ág csendben átveszi a fordulót (helyes viselkedés),
        # de a próbálgatónak tudnia kell, hogy nem az éles utat méri.
        figyelmeztetes = valasz_szoveg.modell_figyelmeztetes_szoveg(modell_nev)
        if figyelmeztetes:
            # `tk.Label` (nem ttk): a háttérszín témafüggetlenül
            # állítható rajta — a figyelmeztetésnek látszania kell,
            # bármilyen ttk-témát használ a rendszer.
            self.modell_figyelmeztetes = tk.Label(
                self,
                text=figyelmeztetes,
                justify="left",
                anchor="w",
                background="#ffe9c7",
                foreground="#7a3b00",
                font=("TkDefaultFont", 10, "bold"),
                wraplength=780,
                padx=12,
                pady=8,
            )
            self.modell_figyelmeztetes.pack(anchor="w", fill="x")

        self.idoszak_cimke = ttk.Label(
            self,
            text=valasz_szoveg.rendszersor_szoveg(
                self.idoszak, self._most_iso(), _most_iso(), modell_nev
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

        gomb_keret = ttk.Frame(tab)
        gomb_keret.grid(row=3, column=0, columnspan=2, sticky="w", pady=(10, 0))
        ttk.Button(gomb_keret, text="Időpontok keresése", command=self._kop_kereses).pack(
            side="left"
        )
        # „A következő szabad időpont" ELSŐRENDŰ kérés (ADR-024), nem a
        # keresés egy esete: se napot, se napszakot nem használ, mert a
        # kérdésben nincs ilyen. A szöveges úton ugyanez a
        # `legkozelebbi_idopont` eszköz felel.
        ttk.Button(
            gomb_keret, text="A legkorábbi szabad időpont", command=self._kop_legkorabbi
        ).pack(side="left", padx=(8, 0))

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
        self.kop_nyugtazo.config(text=valasz_szoveg.nyugtazo_szoveg(parameterek, zona=self.zona))
        self.update_idletasks()

        valasz = self.orchestrator.kereses_strukturaltan(self.session_id, parameterek)
        self._eredmeny_render(self.kop_tartalom, valasz, self.kop_uzenet)

    def _kop_legkorabbi(self) -> None:
        bolt_slug = self._kop_bolt_nev_map.get(self.kop_bolt_valto.get())
        if not bolt_slug:
            self.kop_uzenet.config(text=valasz_szoveg.hiba_szoveg("hianyzo_bolt_es_nap"))
            return
        self.kop_uzenet.config(text="")

        parameterek = {"bolt_id": bolt_slug}
        self.kop_nyugtazo.config(text=valasz_szoveg.nyugtazo_szoveg(parameterek, zona=self.zona))
        self.update_idletasks()

        valasz = self.orchestrator.legkozelebbi_strukturaltan(
            self.session_id, parameterek, _most_iso()
        )
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
                    text=_idopont_cimke(jelolt["kezdet"], jelolt["veg"], self.zona),
                    # A TELJES jelölt megy tovább, nem csak az azonosító:
                    # a megerősítés visszaolvasásához (blueprint 7.)
                    # kell a kezdés időpontja is — hangon a „biztosan
                    # lefoglaljam EZT?" mutató névmásának nincs mire
                    # mutatnia.
                    command=lambda j=jelolt: self._jelolt_valaszt(keret, j, uzenet_label),
                ).pack(anchor="w", pady=2)
            return

        if not valasz.get("sikeres", True):
            kulcs = valasz.get("uzenet_kulcs", "")
            uzenet_label.config(text=valasz_szoveg.hiba_szoveg(kulcs, mod=self._mod()))
            return

        # Egyéb sikeres eszközválasz (bolt_info, foglalas_lemondas, ...)
        ttk.Label(
            keret,
            text=valasz_szoveg.tenyvalasz_szoveg(valasz, mod=self._mod()),
            wraplength=680,
        ).pack(anchor="w")

    def _gomb_naplo(self, akcio: str, bemenet: str, valasz: dict) -> None:
        """Egy KOPPINTÁSSAL kiváltott forduló a próba-naplóba.

        A napló sokáig csak a beírt mondatokat rögzítette, a
        gombnyomásokat nem — így a beszélgetés útvonala az ajánlatnál
        MEGSZAKADT: a naplóból nem derült ki, hogy a vásárló választott-e
        időpontot, megerősítette-e, és létrejött-e a foglalás. Épp az a
        rész hiányzott, ami miatt az egész van.

        A `reteg` itt `felulet:<akcio>`, nem `szabaly` vagy `llm`:
        koppintásnál nincs mit ÉRTELMEZNI, a szándék egyértelmű. Ez az
        útvonal-nézőben (`tools/utvonal.py`) is így látszik — és ez a
        lényeg: egy gombnyomás nem ugyanaz a bizonyíték, mint egy
        helyesen értelmezett mondat."""
        _proba_naplo_ir(
            bemenet,
            {"eszkoz": akcio, "parameterek": {}},
            f"felulet:{akcio}",
            valasz_tipus=valasz.get("tipus") or ("sikeres" if valasz.get("sikeres") else "hiba"),
            uzenet_kulcs=valasz.get("uzenet_kulcs"),
            allapot=self.orchestrator.utolso_allapot,
            session_id=self.session_id,
            nyomkovetes={
                "valasz_szovegesen": self._valasz_mondatok(valasz, valasz_szoveg.MOD_SZOVEGES),
                "valasz_beszelhetoen": self._valasz_mondatok(valasz, valasz_szoveg.MOD_BESZELHETO),
                "lepesek": [],
                "mezo_forras": {},
                "modellhivas_db": 0,
            },
        )

    def _jelolt_valaszt(self, keret: ttk.Frame, jelolt: dict, uzenet_label: ttk.Label) -> None:
        valasz = self.orchestrator.valaszt(self.session_id, jelolt["slot_id"])
        self._gomb_naplo(
            "jelolt_koppintas", _idopont_cimke(jelolt["kezdet"], jelolt["veg"], self.zona), valasz
        )
        if valasz.get("tipus") != "megerositest_ker":
            uzenet_label.config(
                text=valasz_szoveg.hiba_szoveg(
                    valasz.get("uzenet_kulcs", "ismeretlen_valasz"), mod=self._mod()
                )
            )
            return

        self._megerosites_urlap(keret, jelolt, uzenet_label)

    def _megerosites_urlap(self, keret: ttk.Frame, jelolt: dict, uzenet_label: ttk.Label) -> None:
        """A megerősítő űrlap: visszaolvasás, azonosító-mező, két gomb.

        **Két úton érkezhetünk ide**, és sokáig csak az egyik volt
        bekötve: koppintással egy időpont-gombra, VAGY szövegesen, egy
        sorszámos hivatkozással („a másodikat"). A fej nélküli
        végigjátszás fogta meg, hogy a második úton a képernyőn a
        „Nem értettem" mondat jelent meg — miközben a naplóban minden
        helyes volt (`megerositest_ker`, `orchestrator:sorszam`). A
        `megerositest_ker` választípust a szöveges ág egyszerűen nem
        ismerte, mert addig csak gombnyomásból keletkezhetett."""
        for widget in keret.winfo_children():
            widget.destroy()

        ttk.Label(
            keret,
            text=valasz_szoveg.megerosites_ker_szoveg(
                jelolt.get("kezdet"), mod=self._mod(), zona=self.zona
            ),
            wraplength=680,
        ).pack(anchor="w")
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
        mod = self._mod()
        if not azonosito_bevitel.strip():
            uzenet_label.config(
                text=valasz_szoveg.hiba_szoveg("hianyzo_azonosito_bevitel", mod=mod)
            )
            return
        kulcs_hash = ideiglenes_hash(azonosito_bevitel)
        valasz = self.orchestrator.megerosit(self.session_id, kulcs_hash)
        self._gomb_naplo("megerosites", "Igen, foglaljuk le", valasz)
        for widget in keret.winfo_children():
            widget.destroy()
        if valasz.get("tipus") == "visszaigazolas":
            ttk.Label(
                keret,
                text=valasz_szoveg.sikeres_foglalas_szoveg(valasz["foglalasi_kod"], mod=mod),
                font=("TkDefaultFont", 11, "bold"),
                wraplength=680,
            ).pack(anchor="w")
        else:
            kulcs = valasz.get("uzenet_kulcs", "")
            uzenet_label.config(text=valasz_szoveg.hiba_szoveg(kulcs, mod=mod))

    def _elvet(self, keret: ttk.Frame, uzenet_label: ttk.Label) -> None:
        self._gomb_naplo("elvetes", "Mégse", self.orchestrator.elvet(self.session_id) or {})
        for widget in keret.winfo_children():
            widget.destroy()
        uzenet_label.config(text=valasz_szoveg.elvetve_szoveg(mod=self._mod()))

    # ------------------------------------------------------------------
    # Szöveges út
    # ------------------------------------------------------------------

    def _szoveges_build(self) -> None:
        tab = self.szoveges_tab

        # KIMENETI MÓD-kapcsoló (M6). A címke és a két felirat itt
        # KIVÉTELESEN a felületen van: ez nem a vásárlónak szóló mondat,
        # hanem a próbálgató kapcsolója — ugyanabból a megfontolásból,
        # amiért a "Napló megnyitása" gomb felirata sem sablonból jön.
        mod_sor = ttk.Frame(tab, padding=(0, 0, 0, 6))
        mod_sor.pack(fill="x")
        ttk.Label(mod_sor, text="Kimenet:").pack(side="left", padx=(0, 6))
        self.kimeneti_mod = tk.StringVar(value=valasz_szoveg.MOD_SZOVEGES)
        for ertek, felirat in (
            (valasz_szoveg.MOD_SZOVEGES, "szöveges"),
            (valasz_szoveg.MOD_BESZELHETO, "beszélhető (felolvasásra)"),
        ):
            ttk.Radiobutton(mod_sor, text=felirat, variable=self.kimeneti_mod, value=ertek).pack(
                side="left"
            )

        # HANGKIMENET ÁLLAPOTA (ADR-029) — a kapcsoló MELLETT, mert ott
        # merül fel a kérdés. A beszélhető mód eddig CSENDBEN nem
        # szólalt meg: nem volt bekötve TTS, és a felületen ez sehol nem
        # látszott. A csend és a „nincs telepítve" ugyanúgy néz ki.
        # MODELL-ELŐMELEGÍTÉS (mérés: az első forduló 13,93 s volt, a
        # többi 3,5 s — a különbség a betöltés). Külön szálon, hogy az
        # ablak azonnal használható legyen; a címke a szál végén frissül.
        self.melegites_cimke = ttk.Label(mod_sor, text="")
        self.melegites_cimke.pack(side="left", padx=(16, 0))
        self._elomelegit()

        self.hang_allapot = hang.allapot()
        ttk.Label(
            mod_sor,
            text=valasz_szoveg.hang_allapot_szoveg(
                self.hang_allapot.hianyok,
                self.hang_allapot.hang.stem if self.hang_allapot.hang else None,
            ),
            foreground=("#7a3b00" if self.hang_allapot.hianyok else "#2d6a2d"),
            wraplength=520,
        ).pack(side="left", padx=(16, 0))

        self._hang_elomelegit()

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
        ttk.Button(
            also_gombsor, text="Napló megnyitása (böngészőben)", command=self._naplo_ablak
        ).pack(side="left", padx=(0, 6))
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
        # A félbemaradt beszélhető puffer sem csordulhat át az új
        # beszélgetésbe.
        self._rendszer_puffer.clear()
        for keret in (self.szo_gombsor, self.szo_jelolt_keret):
            for widget in keret.winfo_children():
                widget.destroy()
        self.szo_uzenet.config(text="")
        self.szo_naplo.config(state="normal")
        self.szo_naplo.delete("1.0", "end")
        self.szo_naplo.config(state="disabled")

    def _naplo_ablak(self) -> None:
        """A próba-napló BÖNGÉSZŐBEN, a beszélgetés-elemzővel
        (`tools/beszelgetes_riport.py`).

        Korábban ez a gomb a nyers naplót írta ki egy Tkinter-ablakba.
        Az olvasható volt, de csak addig, amíg egy forduló elfért nyolc
        sorban — a prompt, a nyers modellválasz és a dátumfeloldás már
        nem fér el, márpedig a „miért ezt csinálta" kérdésre pont azok
        felelnek. A böngésző ezt ingyen megoldja (összecsukható blokkok,
        kereshetőség, elküldhető fájl), és nem kell hozzá semmit
        megépíteni.

        **Ha a jelentés bármi okból nem áll elő, a régi szöveges ablak
        nyílik meg** — a napló megnézhetősége fontosabb, mint a formája,
        és egy hibakereső eszköz nem dőlhet el hibakeresés közben."""
        try:
            utvonal = self._riport_ir()
        except OSError as exc:
            self._naplo_ablak_szovegesen(f"A HTML-jelentés nem állt elő: {exc}\n\n")
            return
        webbrowser.open(utvonal.resolve().as_uri())

    def _riport_ir(self) -> Path:
        """A HTML-jelentés kiírása. Külön metódus, hogy a hibaág
        (`_naplo_ablak`) tesztelhető legyen."""
        from tools.beszelgetes_riport import ALAP_KIMENET, riport

        ALAP_KIMENET.parent.mkdir(parents=True, exist_ok=True)
        ALAP_KIMENET.write_text(
            riport(proba_naplo_olvas(), PROBA_NAPLO_UTVONAL.name), encoding="utf-8"
        )
        return ALAP_KIMENET

    def _naplo_ablak_szovegesen(self, elotag: str = "") -> None:
        """A RÉGI, Tkinter-ablakos nézet — tartalék, ha a jelentés nem
        áll elő."""
        ablak = tk.Toplevel(self)
        ablak.title("Próba-napló — naplo/probak.jsonl")
        ablak.geometry("760x520")
        szoveg = tk.Text(ablak, wrap="word")
        szoveg.pack(fill="both", expand=True)
        szoveg.insert("end", elotag + proba_naplo_szoveg(proba_naplo_olvas()))
        szoveg.config(state="disabled")

    # A kiút-gombok mögötti, előre megírt mondatok: a választás egy új
    # fordulóként megy vissza az orchestratorba, hogy onnantól a szokásos
    # út fusson (értelmező → állapotgép), ne külön ág.
    _KIUT_MONDAT = {
        # A „másik nap" a hét EGÉSZÉT nyitja meg, nem egy konkrét másik
        # napot: azt, hogy melyik nap jó, a keresés eredménye mondja meg,
        # nem mi találjuk ki helyette.
        "nap": "bármelyik nap jó ezen a héten",
        "napszak": "bármikor jó, bármelyik napszakban",
        # A `legkorabbi` a `bolt` helyére lépett (ADR-024). A mondat
        # szándékosan a vásárló szavaival kérdez, és az értelmező ezt
        # a `legkozelebbi_idopont` eszközre fordítja — nem kér rá
        # időablakot.
        "legkorabbi": "mikor tudok legkorábban menni?",
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
        szovegek = valasz_szoveg.alternativa_szoveg(dimenzio, mod=self._mod())
        if szovegek is None:
            return
        bevezetes, gomb_felirat = szovegek
        self._rendszer_mondat(bevezetes)
        ttk.Button(
            self.szo_gombsor,
            text=gomb_felirat,
            command=lambda d=dimenzio: self._alternativa_kereses(d),
        ).pack(side="left", padx=(0, 6))

    def _alternativa_kereses(self, dimenzio: str) -> None:
        for widget in self.szo_gombsor.winfo_children():
            widget.destroy()
        valasz = self.orchestrator.alternativa_kereses(self.session_id, dimenzio)
        self._gomb_naplo(f"alternativa:{dimenzio}", "(alternatíva-gomb)", valasz)
        self._szoveges_valasz_kezel(valasz)

    def _mod(self) -> str:
        """Az aktuális kimeneti mód. Külön metódus, mert a felület
        felépítése előtt (üres adatbázis) a kapcsoló még nem létezik, és
        a végigjátszás is állíthatja kívülről."""
        valto = getattr(self, "kimeneti_mod", None)
        return valto.get() if valto is not None else valasz_szoveg.MOD_SZOVEGES

    def _rendszer_mondat(self, szoveg: str, *, kulon_megszolalas: bool = False) -> None:
        """A rendszer egy mondata a szöveges úton.

        Szöveges módban azonnal kiíródik (mai viselkedés). Beszélhető
        módban PUFFERBE kerül, és a forduló végén megy ki egyben — így
        érvényesíthető a fordulónkénti két mondat és egy kérdés
        (`assistant/valasz/beszelheto.py`).

        `kulon_megszolalas=True` a nyugtázó soré: az a kétlépcsős válasz
        első lépcsője (blueprint 7.), tehát önálló megszólalás — nem
        foghatja el a tartalmi válasz kétmondatos keretét."""
        if self._mod() == valasz_szoveg.MOD_SZOVEGES or kulon_megszolalas:
            self._naplo_ir("Rendszer", szoveg)
            return
        self._rendszer_puffer.append(szoveg)

    def _rendszer_flush(self) -> None:
        """A forduló összegyűjtött rendszer-mondatai egy megszólalásként.
        Szöveges módban nincs mit tenni (a puffer üres marad)."""
        if not self._rendszer_puffer:
            return
        reszek, self._rendszer_puffer = self._rendszer_puffer, []
        szoveg = valasz_szoveg.fordulo_szoveg(reszek, self._mod())
        if szoveg:
            self._naplo_ir("Rendszer", szoveg)
            self._felolvas(szoveg)

    def _bolt_gombok(self, boltok: list[dict]) -> None:
        """A boltok GOMBKÉNT, leírással — a katalógus-válasz alatt.

        Egy felsorolás után a legtermészetesebb következő lépés a
        választás; ha ehhez újra be kell gépelni a bolt nevét, a
        felsorolás fele elveszett. Több bolt esetén jár csak: egyetlen
        boltnál nincs mit választani."""
        if len(boltok) < 2:
            return
        for bolt in boltok:
            nevek = ", ".join(sz["nev"] for sz in bolt["szolgaltatasok"])
            ttk.Button(
                self.szo_gombsor,
                text=f"{bolt['nev']} — {nevek}" if nevek else bolt["nev"],
                command=lambda b=bolt["bolt_id"]: self._szo_kuldes(b),
            ).pack(side="left", padx=(0, 6))

    def _hang_elomelegit(self) -> None:
        """A HANGMODELL betöltése a háttérben, indításkor.

        Ugyanaz az indok, mint a modell-előmelegítésnél: MÉRVE
        (2026-09-20) a hangmodell betöltése 1,54 s, és ez különben az
        ELSŐ megszólalás elejére kerülne — épp oda, ahol a vásárló még
        azt sem tudja, megszólal-e egyáltalán a rendszer.

        Akkor is lefut, ha a felület épp szöveges módban indul: a
        kapcsoló egy kattintás, és onnantól már ne kelljen várni. A
        szál `daemon`, a hibát pedig a `hang.elomelegit()` nyeli el —
        egy kényelmi lépés nem akadályozhatja meg az indulást."""
        if not self.hang_allapot.rendben:
            return
        threading.Thread(target=lambda: hang.elomelegit(self.hang_allapot), daemon=True).start()

    def _felolvas(self, szoveg: str) -> None:
        """A megszólalás FELOLVASÁSA, ha van mivel (ADR-029).

        Három dolog kell hozzá, és mindhárom hiányozhat: Piper, magyar
        hangmodell, lejátszó. Ha bármelyik hiányzik, NEM csendben marad
        el — az állapotsor a kapcsoló mellett kiírja, mi hiányzik, és
        egy hiba az üzenetsorba kerül, nem a semmibe.

        **Az ÚJ megszólalás elhallgattatja a régit** (`hang.leallit()`).
        A vásárló gyorsabban ír, mint ahogy a hang elhangzik; enélkül a
        két mondat egymásra csúszik, és egyik sem érthető. A vásárló
        kérdése fontosabb, mint az előző válasz vége.

        **Külön szálon**, mert a lejátszás blokkol: az eseményhurkon
        futtatva a felület a mondat végéig megfagyna. A szál `daemon`,
        tehát az ablak bezárása nem várja meg a mondat végét.

        **A DIAGNÓZIST nem futtatjuk újra** minden mondatnál: az
        `allapot()` fájlrendszert olvas (`shutil.which`, útvonalak), és
        az indulás óta nem változott. A gyorsítás mérhető része nem is
        itt van, hanem abban, hogy a hangmodell betöltve marad
        (`assistant/hang.py`) — mondatonként 2,07 s helyett 0,2."""
        if self._mod() != valasz_szoveg.MOD_BESZELHETO or not self.hang_allapot.rendben:
            return

        hang.leallit()
        allapot = self.hang_allapot

        def dolgozik() -> None:
            try:
                hang.lejatszik(hang.szintetizal(szoveg, allapot_=allapot), allapot_=allapot)
            except (RuntimeError, OSError) as exc:
                # A hibaszöveget MOST kell kinyerni: a Python az
                # `except ... as exc` nevet a blokk végén törli, tehát a
                # később lefutó lambda már nem érné el.
                uzenet = f"Felolvasási hiba: {exc}"
                # A felület szálán kell megjeleníteni (Tkinter nem
                # szálbiztos), ezért `after`-rel tesszük vissza.
                self.after(0, lambda: self.szo_uzenet.config(text=uzenet))

        threading.Thread(target=dolgozik, daemon=True).start()

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

    def _jeloltek_az_elozmenybe(self, jeloltek: list[dict]) -> None:
        """A felajánlott időpontok SORSZÁMOZVA a beszélgetés-előzménybe.

        A képernyőn a jelöltek gombok, tehát a szöveges naplóba (és így
        az előzménybe) eddig nem kerültek bele — a modell nem tudta,
        mit ajánlottunk fel, és egy „a másodikat" mondatra nem volt
        mire hivatkoznia.

        A determinisztikus felismerés (`assistant/sorszam.py`) ettől
        függetlenül működik; ez a sor a MODELL kedvéért van, arra az
        esetre, ha a mondat a zárt mintákba nem fér bele („az a fél
        kilences jó lesz"). Nem jelenik meg a képernyőn: a vásárló a
        gombokat látja, a beszélgetés-előzmény pedig nem a képernyő
        másolata, hanem az értelmező bemenete (ADR-019)."""
        if not jeloltek:
            return
        sorok = [
            f"{i}. {_idopont_cimke(j['kezdet'], j['veg'], self.zona)}"
            for i, j in enumerate(jeloltek, start=1)
            if j.get("kezdet") and j.get("veg")
        ]
        if sorok:
            self._elozmenyhez_ad(KI_RENDSZER, "Felajánlott időpontok: " + "; ".join(sorok))

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

        self.szo_allapot.config(
            text=valasz_szoveg.nyugtazo_szoveg({}, mod=self._mod(), zona=self.zona)
        )
        self.update_idletasks()

        # A válaszidő a TELJES fordulót méri (értelmezés + eszközhívás),
        # mert a vásárló is ezt érzékeli — nem csak a modellhívást.
        kezdet = time.monotonic()
        hivasok_elotte = self._modellhivasok_szama()
        valasz = self.orchestrator.fordulo(
            self.session_id, szoveg, self._most_iso(), elozmenyek=elozmenyek
        )
        valaszido = time.monotonic() - kezdet
        self.szo_allapot.config(text="")
        _proba_naplo_ir(
            szoveg,
            self.orchestrator.utolso_ertelmezes,
            # A réteget elsősorban a VÁLASZ mondja meg: van olyan út
            # (sorszámos hivatkozás), ahol az orchestrator dönt, és az
            # értelmező meg sem szólal — ilyenkor az ő `utolso_reteg`-je
            # az ELŐZŐ fordulóé lenne, ami néma félrevezetés a naplóban.
            valasz.get("reteg") or getattr(self.orchestrator.ertelmezo, "utolso_reteg", None),
            # A NORMALIZÁLT ALAK CSAK AKKOR, ha az értelmező tényleg
            # futott. Rövidzárnál (`orchestrator:sorszam`,
            # `orchestrator:megerosites`) a mondat el sem jut a
            # normalizálóig, tehát az attribútum még az ELŐZŐ fordulóé
            # — az útvonal-néző fogta meg, ahogy egy „a másodikat
            # kérem" mellett a két fordulóval korábbi „Törpillához
            # mennék holnap" állt normalizált alakként. Egy elavult
            # mező rosszabb, mint a hiányzó: úgy néz ki, mint egy tény.
            normalizalt=(
                getattr(self.orchestrator.ertelmezo, "utolso_normalizalt", None)
                if not (valasz.get("reteg") or "").startswith("orchestrator:")
                else None
            ),
            valasz_tipus=valasz.get("tipus") or ("sikeres" if valasz.get("sikeres") else "hiba"),
            valaszido_masodperc=valaszido,
            uzenet_kulcs=valasz.get("uzenet_kulcs"),
            kapuor_ok=valasz.get("kapuor_ok"),
            egyetertes=getattr(self.orchestrator.ertelmezo, "utolso_egyetertes", None),
            modell=aktiv_modell_neve(),
            prompt_verzio=getattr(self._llm_reteg(), "utolso_prompt_verzio", None),
            allapot=self.orchestrator.utolso_allapot,
            nyomkovetes=self._nyomkovetes(valasz, hivasok_elotte),
            session_id=self.session_id,
        )
        self._szoveges_valasz_kezel(valasz)

    def _llm_reteg(self):
        """A modell-hívó réteg, ha van — a nyomkövetéshez.

        A felület SOSEM importálja a modell-specifikus osztályokat
        (CLAUDE.md, "Modulhatárok": a `ui/` nem hívhat LLM-et
        közvetlenül), ezért `getattr`-ral kérdez: ha a felépített
        értelmezőnek van `llm` attribútuma, azon keresztül olvassuk a
        nyomkövetést. Determinisztikus úton ez `None`, és a
        nyomkövetés egyszerűen szegényebb lesz."""
        return getattr(self.orchestrator.ertelmezo, "llm", None)

    def _modellhivasok_szama(self) -> int:
        return getattr(self._llm_reteg(), "hivasok_szama", 0) or 0

    def _nyomkovetes(self, valasz: dict, hivasok_elotte: int) -> dict:
        """A forduló teljes nyomkövetése a beszélgetés-elemzőnek
        (`tools/beszelgetes_riport.py`).

        **A kimenő válasz MINDKÉT módban itt áll elő.** A `valasz`
        modul tiszta (nem dönt, nem hív semmit), tehát a másik mód
        mondatát utólag is elő lehet állítani — és épp ez a
        legérdekesebb összevetés: ugyanaz a döntés, kétféleképpen
        kimondva. Az előállítás nem befolyásolja azt, amit a vásárló
        lát: az már megtörtént."""
        ertelmezo = self.orchestrator.ertelmezo
        llm = self._llm_reteg()
        hivasok = max(0, self._modellhivasok_szama() - hivasok_elotte)

        # RÖVIDZÁR: van olyan út (sorszámos hivatkozás), ahol az
        # orchestrator dönt, és az értelmező meg sem szólal. Ilyenkor az
        # ő `utolso_nyomkovetes`-e az ELŐZŐ fordulóé — átmásolva néma
        # hazugság lenne a jelentésben (lépések, dátumfeloldás,
        # mezőforrás, mind a korábbi mondaté).
        rovidzar = valasz.get("reteg")
        if rovidzar:
            nyom: dict = {"lepesek": [], "mezo_forras": {}, "datum": {}, "rovidzar": rovidzar}
        else:
            nyom = dict(getattr(ertelmezo, "utolso_nyomkovetes", {}) or {})

        nyom["modell"] = aktiv_modell_neve()
        nyom["prompt_verzio"] = getattr(llm, "utolso_prompt_verzio", None)
        nyom["modellhivas_db"] = hivasok
        # A prompt és a nyers válasz UGYANEZ a csapda: a modell-hívó
        # réteg megőrzi az utolsó hívás adatait, tehát egy kapuőrös vagy
        # tartalék fordulóban a KORÁBBI forduló promptja állna itt. Csak
        # akkor vesszük át őket, ha ebben a fordulóban tényleg volt hívás.
        if hivasok:
            nyom["prompt"] = getattr(llm, "utolso_prompt", None)
            nyom["nyers_valasz"] = getattr(llm, "utolso_nyers_valasz", None)
            nyom["sema_ok"] = getattr(llm, "utolso_sema_ok", None)
            nyom["llm_hiba"] = getattr(llm, "utolso_hiba", None)
        else:
            nyom["prompt"] = None
            nyom["nyers_valasz"] = None
            nyom["sema_ok"] = None
            nyom["llm_hiba"] = None
        nyom["valasz_szovegesen"] = self._valasz_mondatok(valasz, valasz_szoveg.MOD_SZOVEGES)
        nyom["valasz_beszelhetoen"] = self._valasz_mondatok(valasz, valasz_szoveg.MOD_BESZELHETO)
        return nyom

    def _valasz_mondatok(self, valasz: dict, mod: str) -> str:
        """A kimenő válasz szövege egy adott módban — a képernyőtől
        FÜGGETLENÜL, mellékhatás nélkül.

        Ugyanazokat a `valasz`-hívásokat használja, mint a megjelenítés
        (`_szoveges_valasz_mondatok`), csak nem widgetet épít, hanem
        mondatokat gyűjt. A két kód azért nem közös, mert a
        megjelenítés gombokat is rajzol, és azt egy jelentéshez nem
        akarjuk lefuttatni."""
        tipus = valasz.get("tipus")
        reszek: list[str] = []
        if tipus in ("elutasitas", "kiut") and valasz.get("uzenet_kulcs"):
            if tipus == "kiut" and not valasz.get("emberhez"):
                eredeti_kulcs = valasz.get("eredeti_uzenet_kulcs")
                if eredeti_kulcs:
                    reszek.append(valasz_szoveg.hiba_szoveg(eredeti_kulcs, mod=mod))
                reszek.append(
                    valasz_szoveg.kiut_szoveg(
                        valasz.get("valaszthato_dimenziok", []),
                        mod=mod,
                        bevezetessel=not eredeti_kulcs,
                    )[0]
                )
            else:
                reszek.append(valasz_szoveg.hiba_szoveg(valasz["uzenet_kulcs"], mod=mod))
        elif tipus == "visszakerdezes":
            mondva = valasz.get("valaszthato_mondva") or {}
            reszek.append(
                valasz_szoveg.visszakerdezes_szoveg(
                    valasz.get("hianyzo_mezo"),
                    valasztek=[
                        mondva[e] for e in (valasz.get("valaszthato_ertekek") or []) if e in mondva
                    ]
                    or None,
                    mod=mod,
                )
            )
        elif tipus == "ajanlat":
            reszek.append(
                valasz_szoveg.nyugtazo_szoveg(
                    valasz.get("felismert_ablak", {}), mod=mod, zona=self.zona
                )
            )
            reszek.append(
                valasz_szoveg.ajanlat_mondat(
                    valasz.get("jeloltek") or [],
                    legkozelebbi=bool(valasz.get("legkozelebbi")),
                    mod=mod,
                    zona=self.zona,
                )
            )
        elif tipus == "ajanlat_valasz":
            reszek.append(valasz_szoveg.ajanlat_valasz_szoveg(valasz, mod=mod, zona=self.zona))
        elif tipus == "ajanlat_emlekezteto":
            reszek.append(
                valasz_szoveg.ajanlat_emlekezteto_szoveg(
                    valasz.get("jeloltek") or [], mod=mod, zona=self.zona
                )
            )
        elif tipus == "megerositest_ker":
            jelolt = valasz.get("valasztott_jelolt") or {}
            reszek.append(
                valasz_szoveg.megerosites_ker_szoveg(
                    jelolt.get("kezdet"),
                    mod=mod,
                    rendszer_valasztott=bool(valasz.get("rendszer_valasztott")),
                    zona=self.zona,
                )
            )
        elif tipus == "visszaigazolas":
            # A LÉTREJÖTT FOGLALÁS mondata. Sokáig kimaradt innen, mert
            # ez a metódus a naplózás és a riport kedvéért van, a
            # foglalás pedig gombnyomásból keletkezett — amit a napló
            # eddig nem is rögzített. Az útvonal-néző fogta meg: a
            # beszélgetés utolsó, LEGFONTOSABB fordulójánál üresen
            # maradt az „amit a vásárló látott" sor.
            reszek.append(
                valasz_szoveg.sikeres_foglalas_szoveg(valasz.get("foglalasi_kod", ""), mod=mod)
            )
        elif tipus == "elvetve":
            reszek.append(valasz_szoveg.elvetve_szoveg(mod=mod))
        elif valasz.get("uzenet_kulcs"):
            reszek.append(valasz_szoveg.hiba_szoveg(valasz["uzenet_kulcs"], mod=mod))
        elif valasz.get("sikeres"):
            reszek.append(valasz_szoveg.tenyvalasz_szoveg(valasz, mod=mod))
        return valasz_szoveg.fordulo_szoveg(reszek, mod)

    def _szoveges_valasz_kezel(self, valasz: dict) -> None:
        """A forduló válaszát mondatokká alakítja és kiírja.

        **A metódus MINDIG flush-sal zárul** (`try/finally`): a
        beszélhető mód pufferében maradt mondat különben a következő
        forduló elejére csúszna át, és a vásárló egy már megválaszolt
        kérdésre kapna feleletet."""
        try:
            self._szoveges_valasz_mondatok(valasz)
        finally:
            self._rendszer_flush()

    def _szoveges_valasz_mondatok(self, valasz: dict) -> None:
        tipus = valasz.get("tipus")
        mod = self._mod()

        if tipus == "elutasitas":
            self._rendszer_mondat(valasz_szoveg.hiba_szoveg(valasz["uzenet_kulcs"], mod=mod))
            return

        if tipus == "kiut":
            # Ugyanaz a válasz harmadszor nem megy ki — más mondat, zárt
            # választással (blueprint 7. szakasz, "Négy technika" 2.).
            # A frusztráció-figyelő MÁSODIK kiútja embert ajánl, nem
            # újabb szűkítést — ott nincs gomb, csak a mondat.
            if valasz.get("emberhez"):
                self._rendszer_mondat(valasz_szoveg.hiba_szoveg(valasz["uzenet_kulcs"], mod=mod))
                return
            # A kiút NEM nyelheti el a TÉNYT. A végigjátszás fogta meg:
            # a vásárló megadott egy új napot („jövő héten, vagy
            # 28-án"), a keresés megint üres lett, és a rendszer
            # egyből azt mondta, hogy „így nem jutunk előre" — a
            # vásárló meg sem tudta, hogy a jövő héten sincs időpont.
            # Az eredeti üzenet ezért a kiút ELÉ kerül; beszélhető
            # módban a fordulónkénti két mondat pont ezt a párost
            # engedi át (a tény + a zárt kérdés).
            eredeti_kulcs = valasz.get("eredeti_uzenet_kulcs")
            if eredeti_kulcs:
                self._rendszer_mondat(valasz_szoveg.hiba_szoveg(eredeti_kulcs, mod=mod))
            bevezetes, gombok = valasz_szoveg.kiut_szoveg(
                valasz.get("valaszthato_dimenziok", []),
                mod=mod,
                bevezetessel=not eredeti_kulcs,
            )
            self._rendszer_mondat(bevezetes)
            for dimenzio, felirat in gombok:
                ttk.Button(
                    self.szo_gombsor,
                    text=felirat,
                    command=lambda d=dimenzio: self._kiut_valasztas(d),
                ).pack(side="left", padx=(0, 6))
            # KERESÉS NÉLKÜLI KIÚT (ADR-032): nap/napszak helyett a
            # BOLTOK jönnek gombként. Enélkül a mondat kérdezne
            # („melyik boltba?"), de nem lenne mire koppintani.
            self._bolt_gombok(valasz.get("boltok") or [])
            if valasz.get("kinalat_gomb"):
                ttk.Button(
                    self.szo_gombsor,
                    text="Mit lehet itt?",
                    command=lambda: self._szo_kuldes("mit lehet itt?"),
                ).pack(side="left", padx=(12, 0))
            return

        if tipus == "ajanlat_valasz":
            # FELELET a felajánlott időpontokról szóló kérdésre
            # (ADR-035). Nem új keresés, nem új hold — a jelöltek
            # gombjai ott maradnak, ahol voltak.
            self._rendszer_mondat(
                valasz_szoveg.ajanlat_valasz_szoveg(valasz, mod=mod, zona=self.zona)
            )
            return

        if tipus == "ajanlat_emlekezteto":
            # AJÁNLAT KÖZBEN NEM KÉRDEZÜNK VISSZA (ADR-035). Ugyanazok a
            # jelöltek, ugyanazok a gombok — nincs új keresés, nincs új
            # hold. A vásárló ott folytatja, ahol tartott.
            self._rendszer_mondat(
                valasz_szoveg.ajanlat_emlekezteto_szoveg(
                    valasz.get("jeloltek") or [], mod=mod, zona=self.zona
                )
            )
            self._eredmeny_render(
                self.szo_jelolt_keret,
                {"tipus": "ajanlat", "jeloltek": valasz.get("jeloltek") or []},
                self.szo_uzenet,
            )
            return

        if tipus == "visszakerdezes":
            hianyzo = valasz.get("hianyzo_mezo")
            valasztek = valasz.get("valaszthato_ertekek") or []
            mondva = valasz.get("valaszthato_mondva") or {}
            self._rendszer_mondat(
                valasz_szoveg.visszakerdezes_szoveg(
                    hianyzo,
                    # Beszélhető módban a kérdés FELSOROLJA a
                    # lehetőségeket (nincs gomb, amire mutasson);
                    # szövegesen a gombok viszik, ott a mondat rövid marad.
                    valasztek=[mondva[e] for e in valasztek if e in mondva] or None,
                    mod=mod,
                )
            )
            # A GOMB FELIRATA LEÍRÁSSAL (ADR-032): „Szundi — altató".
            # A slug annak szól, aki már ismeri a boltokat; a leírás
            # annak, aki most találkozik a rendszerrel.
            leirasok = valasz.get("valaszthato_leirasok") or {}
            if valasz.get("kerdes_tipusa") == "zart" and valasztek:
                for ertek in valasztek:
                    cimke = leirasok.get(ertek) or katalogus.BOLT_NEVEK.get(ertek, ertek)
                    ttk.Button(
                        self.szo_gombsor,
                        text=cimke,
                        command=lambda e=ertek: self._szo_kuldes(e),
                    ).pack(side="left", padx=(0, 6))
                # „MIT LEHET ITT?" (ADR-032) — a zárt bolt-kérdés annak
                # szól, aki már tudja, mit akar; aki most találkozik a
                # rendszerrel, annak ez a gomb az első lépés. Nem
                # rejtett tudás: ugyanaz, amit begépelve is kérdezhetne.
                if hianyzo == "bolt_id":
                    ttk.Button(
                        self.szo_gombsor,
                        text="Mit lehet itt?",
                        command=lambda: self._szo_kuldes("mit lehet itt?"),
                    ).pack(side="left", padx=(12, 0))
            return

        if tipus in ("koszones", "kinalat"):
            # MI VAN ITT (ADR-032). Nem indít keresést, és nem rajzol
            # jelölt-gombokat — a boltok viszont GOMBKÉNT is megjelennek,
            # mert a kérdés végén úgyis választani kell.
            self._rendszer_mondat(
                valasz_szoveg.bemutatkozas_szoveg(
                    valasz.get("boltok") or [], koszones=(tipus == "koszones"), mod=mod
                )
            )
            self._bolt_gombok(valasz.get("boltok") or [])
            return

        if tipus == "meta_valasz":
            # A RENDSZERRŐL szóló kérdés (kapuőr, negyedik kategória):
            # rövid bemutatkozás. Nem indít keresést, és nem rajzol
            # gombokat — a beszélgetés ott folytatódik, ahol abbamaradt.
            self._rendszer_mondat(valasz_szoveg.meta_szoveg(mod=mod))
            return

        if tipus == "elvetve":
            # ÍRÁSBELI NEM a megerősítés-kérdésre („mégse kell") — az
            # orchestrator elengedte a választott időpontot
            # (`assistant/megerosites.py`). A többi jelölt még áll, ezért
            # ÚJRA felkínáljuk: a vásárló nemet mondott EGY időpontra,
            # nem az egész keresésre.
            self._rendszer_mondat(valasz_szoveg.elvetve_szoveg(mod=mod))
            jeloltek = valasz.get("jeloltek") or []
            if jeloltek:
                self._rendszer_mondat(
                    valasz_szoveg.ajanlat_mondat(jeloltek, mod=mod, zona=self.zona)
                )
                self._eredmeny_render(
                    self.szo_jelolt_keret,
                    {"tipus": "ajanlat", "jeloltek": jeloltek},
                    self.szo_uzenet,
                )
            return

        if tipus == "megerositest_ker":
            # SORSZÁMOS HIVATKOZÁS („a másodikat") — az orchestrator
            # rövidzárja (`assistant/sorszam.py`) ugyanoda vezet, mint a
            # koppintás: visszaolvasás, azonosító, megerősítés.
            jelolt = valasz.get("valasztott_jelolt") or {}
            self._rendszer_mondat(
                valasz_szoveg.megerosites_ker_szoveg(
                    jelolt.get("kezdet"),
                    mod=mod,
                    # „VÁLASSZ TE" — ilyenkor a vásárló nem látta, melyik
                    # időpontot vettük (a jelölt-gombok eltűntek), tehát a
                    # mondatnak ki kell mondania.
                    rendszer_valasztott=bool(valasz.get("rendszer_valasztott")),
                    zona=self.zona,
                )
            )
            self._megerosites_urlap(self.szo_jelolt_keret, jelolt, self.szo_uzenet)
            return

        if tipus == "ajanlat":
            # A nyugtázó sor — a hangcsatorna töltelékmondatának szöveges
            # próbája (docs/blueprint.md 7. szakasz) — külön naplósorban,
            # MIELŐTT a tényleges (tartalmi) eredmény megjelenik.
            self._rendszer_mondat(
                valasz_szoveg.nyugtazo_szoveg(
                    valasz.get("felismert_ablak", {}), mod=mod, zona=self.zona
                ),
                kulon_megszolalas=True,
            )
            # Beszélhető módban a jelölteket maga a MONDAT hordozza (a
            # legkorábbi + egy alternatíva), mert hangon nincs gomb;
            # szöveges módban a mondat csak bevezeti a gombokat.
            self._rendszer_mondat(
                valasz_szoveg.ajanlat_mondat(
                    valasz.get("jeloltek") or [],
                    legkozelebbi=bool(valasz.get("legkozelebbi")),
                    mod=mod,
                    zona=self.zona,
                )
            )
            self._eredmeny_render(self.szo_jelolt_keret, valasz, self.szo_uzenet)
            self._jeloltek_az_elozmenybe(valasz.get("jeloltek") or [])
            return

        if tipus == "eszkoz_hiba" or not valasz.get("sikeres", True):
            if valasz.get("felismert_ablak"):
                self._rendszer_mondat(
                    valasz_szoveg.nyugtazo_szoveg(
                        valasz["felismert_ablak"], mod=mod, zona=self.zona
                    ),
                    kulon_megszolalas=True,
                )
            kulcs = valasz.get("uzenet_kulcs", "")
            self._rendszer_mondat(valasz_szoveg.hiba_szoveg(kulcs, mod=mod))
            self._alternativa_felajanl(valasz.get("alternativ_dimenzio"))
            return

        if valasz.get("sikeres"):
            self._rendszer_mondat(valasz_szoveg.tenyvalasz_szoveg(valasz, mod=mod))
            return

        self._rendszer_mondat(valasz_szoveg.hiba_szoveg("ismeretlen_valasz", mod=mod))

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
