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

**A `valasz` modul (M5, magyar mondatgenerálás) még nincs megírva** — a
`_UZENET_KULCS_SZOVEG` szótár egy dokumentált, IDEIGLENES helyettesítő,
amíg az elkészül.

**A vásárlóazonosító hash-elése is ideiglenes**: a végleges HMAC+pepper
megoldás (CLAUDE.md 2. invariáns) még nincs megírva — amíg nincs, a
`privacy/hash_ideiglenes.py` (sima SHA-256) helyettesíti. A nyers
azonosítót ez a modul (ui/vasarlo.py) sosem kapja meg szimbólumnévként
— rögtön a `privacy/` hívásának adja át, onnantól csak a hash kering.

**A koppintós "Nap" választó a valódi rendszerórától számított 7 napot
ajánl fel** — a `python feladat.py seed` demóadata viszont egy fix,
2026-12-21-gyel kezdődő hétre generál beosztást (`seed/betolt.py`).
Kézi kipróbáláskor emiatt a legördülőben más dátumot kell választani,
mint a mai nap — ez dokumentált korlát, nem hiba (`docs/TESZTELES.md`).

Indítás:
    python -m ui.vasarlo
"""

from __future__ import annotations

import sys
import tkinter as tk
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from tkinter import ttk

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from assistant.interpreter.rule_based import SzabalyAlapuErtelmezo  # noqa: E402
from assistant.orchestrator import Orchestrator  # noqa: E402
from assistant.tools import katalogus  # noqa: E402
from core.azonosito import new_uuid  # noqa: E402
from core.repo import migracio, torzsadat_repo  # noqa: E402
from privacy.hash_ideiglenes import ideiglenes_hash  # noqa: E402
from seed.betolt import ALAP_DB_PATH  # noqa: E402

_NAPSZAKOK = [
    ("delelott", "délelőtt"),
    ("delutan", "délután"),
    ("este", "este"),
    ("barmikor", "bármikor"),
]

_UZENET_KULCS_SZOVEG = {
    "nem_foglalasi_kerdes": "Ez a kérdés nem foglalással kapcsolatos, ebben nem tudok segíteni.",
    "nincs_szabad_hely_az_ablakban": "Sajnos nincs szabad időpont ebben az ablakban.",
    "jeloltek_kozben_elfogytak": "Éppen lefoglalták előlünk ezeket az időpontokat — próbáld újra.",
    "ismeretlen_bolt": "Ezt a boltot nem ismerem.",
    "ismeretlen_szolgaltatas": "Ezt a szolgáltatást nem ismerem ebben a boltban.",
    "ervenytelen_kereses": "Ezt a kérést nem tudtam értelmezni.",
    "slot_elfogyott": "Sajnos közben elfogyott ez az időpont.",
    "nincs_ilyen_slot": "Ez az időpont már nem érvényes — keress újat.",
    "ervenytelen_foglalasi_kod": "Nem találtam ilyen foglalási kódot.",
    "mar_lemondott_foglalas": "Ez a foglalás már le van mondva.",
    "uj_slot_elfogyott": "Az új időpontot közben elfoglalták.",
    "nem_ajanlott_jelolt": "Ez az időpont már nem szerepel az ajánlatban.",
    "nincs_folyamatban_levo_valasztas": "Előbb válassz egy időpontot.",
}


def _most_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _idopont_cimke(kezdet_iso: str, veg_iso: str) -> str:
    kezdet = datetime.fromisoformat(kezdet_iso.replace("Z", "+00:00"))
    veg = datetime.fromisoformat(veg_iso.replace("Z", "+00:00"))
    return f"{kezdet.strftime('%Y-%m-%d %H:%M')}–{veg.strftime('%H:%M')} (UTC)"


_NAPSZAK_SZOVEG = {"delelott": "délelőtt", "delutan": "délután", "este": "este"}


def _ablak_datum_szoveg(datum_tol: str, datum_ig: str, napszak: str) -> str:
    nap_resz = _NAPSZAK_SZOVEG.get(napszak, "")
    if datum_tol[:10] == datum_ig[:10]:
        alap = datum_tol[:10]
    else:
        alap = f"{datum_tol[:10]} és {datum_ig[:10]} között"
    return f"{alap} {nap_resz}".strip()


def nyugtazo_szoveg(felismert_ablak: dict) -> str:
    """A keresés elindítása UTÁN, az eredmény megérkezése ELŐTT
    felolvasható sor — a hangcsatorna töltelékmondatának (docs/
    blueprint.md 7. szakasz, "Kétlépcsős válasz") szöveges próbája.

    Csak azt mondja, amit MÁR biztosan tud — a blueprint 7. szakasz
    "mondható" oszlopa szerint: a felismert dátumablakot (a
    dátumparserből) és a zárt halmazból beazonosított boltot. Konkrét
    szabad időpontot vagy darabszámot SOSEM tartalmaz, mert azok csak a
    tényleges keresés lefutása után derülnek ki."""
    if not felismert_ablak:
        return "Egy pillanat, nézem…"

    reszek = []
    bolt_slug = felismert_ablak.get("bolt_id")
    if bolt_slug:
        reszek.append(f"a(z) {katalogus.BOLT_NEVEK.get(bolt_slug, bolt_slug)} boltban")
    datum_tol = felismert_ablak.get("datum_tol")
    datum_ig = felismert_ablak.get("datum_ig")
    if datum_tol and datum_ig:
        reszek.append(
            _ablak_datum_szoveg(datum_tol, datum_ig, felismert_ablak.get("napszak", "barmikor"))
        )

    if not reszek:
        return "Egy pillanat, nézem…"
    return "Nézem, mi van " + ", ".join(reszek) + "…"


def tenyvalasz_szoveg(valasz: dict) -> str:
    """A `bolt_info` sikeres válaszát olvasható mondatba fogalmazza —
    IDEIGLENES, amíg a `valasz` modul (M5) nincs megírva. A tényt maga a
    `bolt_info` kereste ki egy szerkesztett mezőből (docs/blueprint.md
    10. szakasz, "Bolti tudás") — ez a függvény csak megfogalmazza,
    nem generál új tartalmat."""
    mezok = {k: v for k, v in valasz.items() if k != "sikeres"}

    if "nyitvatartas" in mezok:
        return f"Nyitvatartás: {mezok['nyitvatartas'] or 'ezt még nem adtuk meg'}"
    if "cim" in mezok:
        return f"Cím: {mezok['cim'] or 'ezt még nem adtuk meg'}"
    if "megjelenes" in mezok:
        return mezok["megjelenes"] or "Erről még nincs leírásunk."
    if "szolgaltatasok" in mezok:
        szolgaltatasok = mezok["szolgaltatasok"]
        if not szolgaltatasok:
            return "Erről nincs adatunk."
        sorok = []
        for sz in szolgaltatasok:
            reszek = [sz["nev"]]
            if sz.get("termekleiras"):
                reszek.append(sz["termekleiras"])
            if sz.get("ar"):
                reszek.append(f"({sz['ar']})")
            if "idotartam_perc" in sz:
                reszek.append(f"{sz['idotartam_perc']} perc")
            sorok.append(" — ".join(reszek))
        return "; ".join(sorok)
    return str(mezok)


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
        self.orchestrator = Orchestrator(self.conn, SzabalyAlapuErtelmezo(), org_id=self.org_id)

        self.protocol("WM_DELETE_WINDOW", self._close)
        self._build()

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
        napok = [(date.today() + timedelta(days=i)).isoformat() for i in range(7)]
        self.kop_nap_valto = tk.StringVar()
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
            self.kop_uzenet.config(text="Válassz boltot és napot.")
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
        self.kop_nyugtazo.config(text=nyugtazo_szoveg(parameterek))
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
            uzenet_label.config(text=_UZENET_KULCS_SZOVEG.get(kulcs, f"Hiba: {kulcs}"))
            return

        # Egyéb sikeres eszközválasz (bolt_info, foglalas_lemondas, ...)
        ttk.Label(keret, text=tenyvalasz_szoveg(valasz), wraplength=680).pack(anchor="w")

    def _jelolt_valaszt(self, keret: ttk.Frame, slot_id: str, uzenet_label: ttk.Label) -> None:
        valasz = self.orchestrator.valaszt(self.session_id, slot_id)
        if valasz.get("tipus") != "megerositest_ker":
            uzenet_label.config(
                text=_UZENET_KULCS_SZOVEG.get(valasz.get("uzenet_kulcs", ""), "Ismeretlen hiba.")
            )
            return

        for widget in keret.winfo_children():
            widget.destroy()

        ttk.Label(keret, text="Biztosan lefoglaljam ezt az időpontot?").pack(anchor="w")
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
            uzenet_label.config(text="Add meg az azonosítót a foglaláshoz.")
            return
        kulcs_hash = ideiglenes_hash(azonosito_bevitel)
        valasz = self.orchestrator.megerosit(self.session_id, kulcs_hash)
        for widget in keret.winfo_children():
            widget.destroy()
        if valasz.get("tipus") == "visszaigazolas":
            ttk.Label(
                keret,
                text=f"Foglalás létrejött! Foglalási kód: {valasz['foglalasi_kod']}",
                font=("TkDefaultFont", 11, "bold"),
            ).pack(anchor="w")
        else:
            kulcs = valasz.get("uzenet_kulcs", "")
            uzenet_label.config(text=_UZENET_KULCS_SZOVEG.get(kulcs, "Nem sikerült a foglalás."))

    def _elvet(self, keret: ttk.Frame, uzenet_label: ttk.Label) -> None:
        self.orchestrator.elvet(self.session_id)
        for widget in keret.winfo_children():
            widget.destroy()
        uzenet_label.config(text="Rendben, nem foglaltuk le. Kereshetsz újra.")

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

    def _naplo_ir(self, ki_be: str, szoveg: str) -> None:
        self.szo_naplo.config(state="normal")
        self.szo_naplo.insert("end", f"{ki_be}: {szoveg}\n")
        self.szo_naplo.config(state="disabled")
        self.szo_naplo.see("end")

    def _szo_kuldes(self, elore_kitoltott: str | None = None) -> None:
        szoveg = elore_kitoltott if elore_kitoltott is not None else self.szo_beviteli_valto.get()
        if not szoveg.strip():
            return
        self.szo_beviteli_valto.set("")
        self._naplo_ir("Te", szoveg)

        for widget in self.szo_gombsor.winfo_children():
            widget.destroy()
        self.szo_uzenet.config(text="")

        valasz = self.orchestrator.fordulo(self.session_id, szoveg, _most_iso())
        self._szoveges_valasz_kezel(valasz)

    def _szoveges_valasz_kezel(self, valasz: dict) -> None:
        tipus = valasz.get("tipus")

        if tipus == "elutasitas":
            self._naplo_ir("Rendszer", _UZENET_KULCS_SZOVEG.get(valasz["uzenet_kulcs"], "—"))
            return

        if tipus == "visszakerdezes":
            hianyzo = valasz.get("hianyzo_mezo", "")
            self._naplo_ir("Rendszer", f"Ehhez még kellene: {hianyzo}. Melyiket szeretnéd?")
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
            self._naplo_ir("Rendszer", nyugtazo_szoveg(valasz.get("felismert_ablak", {})))
            self._naplo_ir("Rendszer", "Ezeket az időpontokat találtam — melyik jó?")
            self._eredmeny_render(self.szo_jelolt_keret, valasz, self.szo_uzenet)
            return

        if tipus == "eszkoz_hiba" or not valasz.get("sikeres", True):
            if valasz.get("felismert_ablak"):
                self._naplo_ir("Rendszer", nyugtazo_szoveg(valasz["felismert_ablak"]))
            kulcs = valasz.get("uzenet_kulcs", "")
            self._naplo_ir("Rendszer", _UZENET_KULCS_SZOVEG.get(kulcs, f"Hiba: {kulcs}"))
            return

        if valasz.get("sikeres"):
            self._naplo_ir("Rendszer", tenyvalasz_szoveg(valasz))
            return

        self._naplo_ir("Rendszer", "Nem értettem, próbáld másképp megfogalmazni.")

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
