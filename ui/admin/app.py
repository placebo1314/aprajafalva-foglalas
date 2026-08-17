"""Admin beosztásszerkesztő — Tkinter, a legegyszerűbb működő forma.

Nem szép, működik: egy hét naptárnézete (pultok oszlopokban), műszak
felvitele sablonnal, a generált slotok/blokkok megjelenítése, és a
foglalások listája lemondással.

Minden adatművelet a `mag/api/adminszolgaltatas.py`-n keresztül megy —
ez a modul maga SQL-t nem tartalmaz és a `mag/repo/`-t sem importálja
közvetlenül (CLAUDE.md 5. invariáns, modulhatár-tábla).

Indítás:
    python -m felulet.admin
"""

from __future__ import annotations

import sys
import tkinter as tk
from datetime import date, datetime, timedelta
from pathlib import Path
from tkinter import messagebox, ttk

GYOKER = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(GYOKER))

from mag.api import adminszolgaltatas as api  # noqa: E402
from mag.repo import migracio  # noqa: E402
from seed.betolt import ALAP_DB_UTVONAL  # noqa: E402

_NAPOK = ["hétfő", "kedd", "szerda", "csütörtök", "péntek", "szombat", "vasárnap"]


def _het_hetfoje(d: date) -> date:
    return d - timedelta(days=d.weekday())


class AdminApp(tk.Tk):
    def __init__(self, db_utvonal: str | None = None) -> None:
        super().__init__()
        self.title("Aprajafalva — admin beosztásszerkesztő")
        self.geometry("1100x700")

        self.db_utvonal = db_utvonal or str(ALAP_DB_UTVONAL)
        self.conn = migracio.kapcsolat_nyitas(self.db_utvonal)
        migracio.migral(self.conn)

        self.szervezet_id: str | None = None
        self.bolt_id: str | None = None
        self.het_kezdete = _het_hetfoje(date.today())
        self.pultok: list[dict] = []
        self.muszak_terkep: dict[tuple[str, str], dict] = {}  # (datum, pult_id) -> muszak
        self.kivalasztott_muszak_id: str | None = None

        self.protocol("WM_DELETE_WINDOW", self._bezaras)
        self._felepit()
        self._szervezetek_betoltese()

    # ------------------------------------------------------------------
    # Felépítés
    # ------------------------------------------------------------------

    def _felepit(self) -> None:
        felso = ttk.Frame(self, padding=6)
        felso.pack(side="top", fill="x")

        ttk.Label(felso, text="Adatbázis:").pack(side="left")
        ttk.Label(felso, text=self.db_utvonal, foreground="#555").pack(side="left", padx=(2, 12))
        ttk.Button(felso, text="Demóadat betöltése", command=self._demo_betoltese).pack(
            side="left", padx=4
        )

        ttk.Label(felso, text="Szervezet:").pack(side="left", padx=(16, 2))
        self.szervezet_valaszto = ttk.Combobox(felso, state="readonly", width=20)
        self.szervezet_valaszto.pack(side="left")
        self.szervezet_valaszto.bind("<<ComboboxSelected>>", self._szervezet_valasztva)

        ttk.Label(felso, text="Bolt:").pack(side="left", padx=(16, 2))
        self.bolt_valaszto = ttk.Combobox(felso, state="readonly", width=20)
        self.bolt_valaszto.pack(side="left")
        self.bolt_valaszto.bind("<<ComboboxSelected>>", self._bolt_valasztva)

        fulek = ttk.Notebook(self)
        fulek.pack(side="top", fill="both", expand=True)

        self.naptar_ful = ttk.Frame(fulek, padding=6)
        self.foglalasok_ful = ttk.Frame(fulek, padding=6)
        self.sablon_ful = ttk.Frame(fulek, padding=6)
        self.torzsadat_ful = ttk.Frame(fulek, padding=6)
        self.utkozes_ful = ttk.Frame(fulek, padding=6)
        fulek.add(self.naptar_ful, text="Naptár és műszakok")
        fulek.add(self.foglalasok_ful, text="Foglalások")
        fulek.add(self.sablon_ful, text="Sablonok és hét-másolás")
        fulek.add(self.torzsadat_ful, text="Törzsadat")
        fulek.add(self.utkozes_ful, text="Ütközéslista")

        self._naptar_fulet_felepit()
        self._foglalasok_fulet_felepit()
        self._sablon_fulet_felepit()
        self._torzsadat_fulet_felepit()
        self._utkozes_fulet_felepit()

    def _naptar_fulet_felepit(self) -> None:
        fejlec = ttk.Frame(self.naptar_ful)
        fejlec.pack(side="top", fill="x")
        ttk.Button(fejlec, text="◀ előző hét", command=self._elozo_het).pack(side="left")
        self.het_cimke = ttk.Label(fejlec, text="", font=("TkDefaultFont", 10, "bold"))
        self.het_cimke.pack(side="left", padx=12)
        ttk.Button(fejlec, text="következő hét ▶", command=self._kovetkezo_het).pack(side="left")

        also = ttk.Frame(self.naptar_ful)
        also.pack(side="top", fill="both", expand=True, pady=(8, 0))

        self.naptar_grid = ttk.Frame(also)
        self.naptar_grid.pack(side="left", fill="both", expand=True)

        jobb = ttk.Frame(also, width=380)
        jobb.pack(side="left", fill="y", padx=(12, 0))
        jobb.pack_propagate(False)

        ttk.Label(
            jobb, text="Kiválasztott műszak részletei", font=("TkDefaultFont", 9, "bold")
        ).pack(anchor="w")
        self.reszletek_szoveg = tk.Text(jobb, height=16, width=44, state="disabled")
        self.reszletek_szoveg.pack(fill="x", pady=(2, 12))

        ttk.Separator(jobb).pack(fill="x", pady=6)
        ttk.Label(jobb, text="Új műszak felvitele", font=("TkDefaultFont", 9, "bold")).pack(
            anchor="w"
        )
        self._muszak_urlapot_felepit(jobb)

    def _muszak_urlapot_felepit(self, szulo: tk.Widget) -> None:
        urlap = ttk.Frame(szulo)
        urlap.pack(fill="x", pady=4)

        def sor(cimke: str) -> ttk.Combobox:
            keret = ttk.Frame(urlap)
            keret.pack(fill="x", pady=1)
            ttk.Label(keret, text=cimke, width=14).pack(side="left")
            box = ttk.Combobox(keret, state="readonly", width=24)
            box.pack(side="left", fill="x", expand=True)
            return box

        self.pult_valaszto = sor("Pult:")
        self.alkalmazott_valaszto = sor("Alkalmazott:")
        self.szolgaltatas_valaszto = sor("Szolgáltatás:")
        self.sablon_valaszto = sor("Sablon:")
        self.sablon_valaszto["values"] = [k for k in api.SABLONOK]
        self.sablon_valaszto.set("gyors_penztar")
        self.sablon_valaszto.bind("<<ComboboxSelected>>", self._sablon_valasztva)

        def szoveg_sor(cimke: str, alap: str = "") -> ttk.Entry:
            keret = ttk.Frame(urlap)
            keret.pack(fill="x", pady=1)
            ttk.Label(keret, text=cimke, width=14).pack(side="left")
            mezo = ttk.Entry(keret)
            mezo.insert(0, alap)
            mezo.pack(side="left", fill="x", expand=True)
            return mezo

        self.datum_mezo = szoveg_sor("Dátum (ÉÉÉÉ-HH-NN):", self.het_kezdete.isoformat())
        self.kezdet_ora_mezo = szoveg_sor("Kezdő óra (0-23):", "8")
        self.veg_ora_mezo = szoveg_sor("Végző óra (0-23):", "16")
        self.idotartam_mezo = szoveg_sor("Időtartam (perc):", "10")
        self.puffer_mezo = szoveg_sor("Puffer utána (perc):", "0")
        self.min_racs_mezo = szoveg_sor("Min. rács (perc):", "10")
        self.arany_mezo = szoveg_sor("Foglalható arány (0-1):", "1.0")

        ttk.Button(urlap, text="Létrehozás", command=self._muszak_letrehozasa).pack(
            fill="x", pady=(6, 0)
        )
        self.urlap_uzenet = ttk.Label(urlap, text="", foreground="#a00", wraplength=340)
        self.urlap_uzenet.pack(fill="x", pady=(4, 0))

    def _foglalasok_fulet_felepit(self) -> None:
        ttk.Button(self.foglalasok_ful, text="Frissítés", command=self._foglalasok_frissitese).pack(
            anchor="w"
        )
        oszlopok = ("kod", "kezdet", "veg", "allapot")
        self.foglalasok_fa = ttk.Treeview(
            self.foglalasok_ful, columns=oszlopok, show="headings", height=20
        )
        for oszlop, cim in zip(
            oszlopok, ("Foglalási kód", "Kezdet", "Vég", "Állapot"), strict=True
        ):
            self.foglalasok_fa.heading(oszlop, text=cim)
        self.foglalasok_fa.pack(fill="both", expand=True, pady=6)
        ttk.Button(self.foglalasok_ful, text="Lemondás", command=self._foglalas_lemondasa).pack(
            anchor="w"
        )

    def _sablon_fulet_felepit(self) -> None:
        bal = ttk.Frame(self.sablon_ful)
        bal.pack(side="left", fill="both", expand=True)
        jobb = ttk.Frame(self.sablon_ful, width=320)
        jobb.pack(side="left", fill="y", padx=(12, 0))
        jobb.pack_propagate(False)

        ttk.Label(bal, text="Mentett sablonok", font=("TkDefaultFont", 9, "bold")).pack(anchor="w")
        self.sablon_lista = tk.Listbox(bal, height=12)
        self.sablon_lista.pack(fill="both", expand=True, pady=(2, 8))
        self._sablon_id_lista: list[str] = []

        mentes_keret = ttk.Frame(bal)
        mentes_keret.pack(fill="x", pady=4)
        ttk.Label(mentes_keret, text="Új sablon neve:").pack(side="left")
        self.sablon_nev_mezo = ttk.Entry(mentes_keret)
        self.sablon_nev_mezo.pack(side="left", fill="x", expand=True, padx=4)
        ttk.Button(
            mentes_keret,
            text="Mentés a kiválasztott műszakból",
            command=self._sablon_mentese_kivalasztottbol,
        ).pack(side="left")

        alkalmaz_keret = ttk.Frame(bal)
        alkalmaz_keret.pack(fill="x", pady=4)
        ttk.Label(alkalmaz_keret, text="Alkalmazás dátuma:").pack(side="left")
        self.sablon_alkalmaz_datum_mezo = ttk.Entry(alkalmaz_keret, width=12)
        self.sablon_alkalmaz_datum_mezo.insert(0, self.het_kezdete.isoformat())
        self.sablon_alkalmaz_datum_mezo.pack(side="left", padx=4)
        ttk.Button(
            alkalmaz_keret, text="Erre a napra", command=self._sablon_alkalmazasa_napra
        ).pack(side="left", padx=2)
        ttk.Button(
            alkalmaz_keret,
            text="Erre a hétre (7 nap)",
            command=self._sablon_alkalmazasa_hetre,
        ).pack(side="left", padx=2)

        ttk.Separator(bal).pack(fill="x", pady=8)
        ttk.Label(bal, text="Hét másolása", font=("TkDefaultFont", 9, "bold")).pack(anchor="w")
        masolas_keret = ttk.Frame(bal)
        masolas_keret.pack(fill="x", pady=4)
        ttk.Label(masolas_keret, text="Forrás hét kezdete:").pack(side="left")
        self.masolas_forras_mezo = ttk.Entry(masolas_keret, width=12)
        self.masolas_forras_mezo.insert(0, self.het_kezdete.isoformat())
        self.masolas_forras_mezo.pack(side="left", padx=4)
        ttk.Label(masolas_keret, text="Cél hét kezdete:").pack(side="left")
        self.masolas_cel_mezo = ttk.Entry(masolas_keret, width=12)
        self.masolas_cel_mezo.pack(side="left", padx=4)
        ttk.Button(masolas_keret, text="Másolás", command=self._het_masolasa).pack(side="left")

        ttk.Label(jobb, text="Eredmény", font=("TkDefaultFont", 9, "bold")).pack(anchor="w")
        self.sablon_uzenet = tk.Text(jobb, height=20, width=42, state="disabled")
        self.sablon_uzenet.pack(fill="both", expand=True, pady=(2, 0))

    def _torzsadat_fulet_felepit(self) -> None:
        """Bolt/pult/alkalmazott/szolgáltatás felvitele+szerkesztése és
        kivételnap felvétele — ma csak a `seed`-ből jött adat volt
        elérhető, ez teszi lehetővé, hogy az admin saját maga bővítse.
        Nem szép, működik: egy-egy kis lista + két mező + két gomb
        (Hozzáadás / Kiválasztott szerkesztése) blokkonként."""
        bal = ttk.Frame(self.torzsadat_ful)
        bal.pack(side="left", fill="both", expand=True)
        jobb = ttk.Frame(self.torzsadat_ful, width=340)
        jobb.pack(side="left", fill="y", padx=(12, 0))
        jobb.pack_propagate(False)

        self.bolt_lista = self._torzsadat_blokk_felepit(
            bal,
            cim="Boltok",
            hozzaadas_szoveg="Hozzáadás",
            hozzaadas_fn=self._bolt_hozzaadasa_ui,
            szerkesztes_fn=self._bolt_szerkesztese_ui,
        )
        self.pult_lista = self._torzsadat_blokk_felepit(
            bal,
            cim="Pultok (a kiválasztott boltban)",
            hozzaadas_szoveg="Hozzáadás",
            hozzaadas_fn=self._pult_hozzaadasa_ui,
            szerkesztes_fn=self._pult_szerkesztese_ui,
        )
        self.alkalmazott_lista = self._torzsadat_blokk_felepit(
            bal,
            cim="Alkalmazottak (a kiválasztott boltban)",
            hozzaadas_szoveg="Hozzáadás",
            hozzaadas_fn=self._alkalmazott_hozzaadasa_ui,
            szerkesztes_fn=self._alkalmazott_szerkesztese_ui,
        )

        ttk.Label(
            jobb, text="Szolgáltatások (a kiválasztott boltban)", font=("TkDefaultFont", 9, "bold")
        ).pack(anchor="w")
        self.szolgaltatas_lista = tk.Listbox(jobb, height=6)
        self.szolgaltatas_lista.pack(fill="x", pady=(2, 4))
        szolg_urlap = ttk.Frame(jobb)
        szolg_urlap.pack(fill="x")
        ttk.Label(szolg_urlap, text="Név:").grid(row=0, column=0, sticky="w")
        self.szolgaltatas_nev_mezo = ttk.Entry(szolg_urlap)
        self.szolgaltatas_nev_mezo.grid(row=0, column=1, sticky="ew")
        ttk.Label(szolg_urlap, text="Időtartam (perc):").grid(row=1, column=0, sticky="w")
        self.szolgaltatas_idotartam_mezo = ttk.Entry(szolg_urlap)
        self.szolgaltatas_idotartam_mezo.grid(row=1, column=1, sticky="ew")
        szolg_urlap.columnconfigure(1, weight=1)
        szolg_gombok = ttk.Frame(jobb)
        szolg_gombok.pack(fill="x", pady=(2, 10))
        ttk.Button(szolg_gombok, text="Hozzáadás", command=self._szolgaltatas_hozzaadasa_ui).pack(
            side="left"
        )
        ttk.Button(
            szolg_gombok,
            text="Kiválasztott szerkesztése",
            command=self._szolgaltatas_szerkesztese_ui,
        ).pack(side="left", padx=4)

        ttk.Separator(jobb).pack(fill="x", pady=6)
        ttk.Label(jobb, text="Kivételnapok", font=("TkDefaultFont", 9, "bold")).pack(anchor="w")
        self.kivetel_lista = tk.Listbox(jobb, height=6)
        self.kivetel_lista.pack(fill="x", pady=(2, 4))
        kiv_urlap = ttk.Frame(jobb)
        kiv_urlap.pack(fill="x")
        ttk.Label(kiv_urlap, text="Dátum (ÉÉÉÉ-HH-NN):").grid(row=0, column=0, sticky="w")
        self.kivetel_datum_mezo = ttk.Entry(kiv_urlap)
        self.kivetel_datum_mezo.grid(row=0, column=1, sticky="ew")
        ttk.Label(kiv_urlap, text="Indok:").grid(row=1, column=0, sticky="w")
        self.kivetel_indok_mezo = ttk.Entry(kiv_urlap)
        self.kivetel_indok_mezo.grid(row=1, column=1, sticky="ew")
        self.kivetel_csak_bolt_valtozo = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            kiv_urlap, text="csak a kiválasztott boltra", variable=self.kivetel_csak_bolt_valtozo
        ).grid(row=2, column=0, columnspan=2, sticky="w")
        kiv_urlap.columnconfigure(1, weight=1)
        ttk.Button(jobb, text="Kivételnap felvétele", command=self._kivetel_nap_hozzaadasa_ui).pack(
            anchor="w", pady=(2, 10)
        )

        self.torzsadat_uzenet = ttk.Label(jobb, text="", foreground="#a00", wraplength=320)
        self.torzsadat_uzenet.pack(fill="x")

    def _torzsadat_blokk_felepit(
        self, szulo, *, cim, hozzaadas_szoveg, hozzaadas_fn, szerkesztes_fn
    ):
        ttk.Label(szulo, text=cim, font=("TkDefaultFont", 9, "bold")).pack(anchor="w", pady=(6, 0))
        lista = tk.Listbox(szulo, height=4)
        lista.pack(fill="x", pady=(2, 4))
        urlap = ttk.Frame(szulo)
        urlap.pack(fill="x")
        mezo = ttk.Entry(urlap)
        mezo.pack(side="left", fill="x", expand=True)
        ttk.Button(urlap, text=hozzaadas_szoveg, command=lambda: hozzaadas_fn(mezo)).pack(
            side="left", padx=2
        )
        ttk.Button(
            urlap, text="Kiválasztott szerkesztése", command=lambda: szerkesztes_fn(lista, mezo)
        ).pack(side="left")
        return lista

    # ------------------------------------------------------------------
    # Adatbetöltés / -frissítés
    # ------------------------------------------------------------------

    def _szervezetek_betoltese(self) -> None:
        szervezetek = api.szervezetek(self.conn)
        self._nevterkep_szervezet = {s["nev"]: s["id"] for s in szervezetek}
        self.szervezet_valaszto["values"] = list(self._nevterkep_szervezet)
        if szervezetek:
            self.szervezet_valaszto.current(0)
            self._szervezet_valasztva()
        else:
            self.het_cimke.config(text="Nincs szervezet — töltsd be a demóadatot a fenti gombbal.")

    def _szervezet_valasztva(self, _esemeny=None) -> None:
        nev = self.szervezet_valaszto.get()
        self.szervezet_id = self._nevterkep_szervezet.get(nev)
        self._bolt_lista_frissitese(tartsd_meg_a_kivalasztottat=False)

    def _bolt_lista_frissitese(self, *, tartsd_meg_a_kivalasztottat: bool = True) -> None:
        """A bolt-legördülő értékeinek frissítése — a törzsadat-fülről
        induló bolt hozzáadás/átnevezés ezt hívja, NEM a
        `_szervezet_valasztva`-t, mert az mindig az első boltra ugrana,
        elveszítve a felhasználó aktuális bolt-kiválasztását."""
        elozo_bolt_id = self.bolt_id if tartsd_meg_a_kivalasztottat else None
        boltok = api.boltok(self.conn, szervezet_id=self.szervezet_id) if self.szervezet_id else []
        self._nevterkep_bolt = {b["nev"]: b["id"] for b in boltok}
        self.bolt_valaszto["values"] = list(self._nevterkep_bolt)
        if not boltok:
            return
        megtartando_nev = next(
            (nev for nev, bid in self._nevterkep_bolt.items() if bid == elozo_bolt_id), None
        )
        if megtartando_nev is not None:
            self.bolt_valaszto.set(megtartando_nev)
        else:
            self.bolt_valaszto.current(0)
        self._bolt_valasztva()

    def _bolt_valasztva(self, _esemeny=None) -> None:
        nev = self.bolt_valaszto.get()
        self.bolt_id = self._nevterkep_bolt.get(nev)
        if not self.bolt_id:
            return
        pultok = api.pultok(self.conn, bolt_id=self.bolt_id)
        alkalmazottak = api.alkalmazottak(self.conn, bolt_id=self.bolt_id)
        szolgaltatasok = api.szolgaltatasok(self.conn, bolt_id=self.bolt_id)
        self._nevterkep_pult = {p["nev"]: p["id"] for p in pultok}
        self._nevterkep_alkalmazott = {a["nev"]: a["id"] for a in alkalmazottak}
        self._nevterkep_szolgaltatas = {s["nev"]: s["id"] for s in szolgaltatasok}
        self.pult_valaszto["values"] = list(self._nevterkep_pult)
        self.alkalmazott_valaszto["values"] = list(self._nevterkep_alkalmazott)
        self.szolgaltatas_valaszto["values"] = list(self._nevterkep_szolgaltatas)
        if pultok:
            self.pult_valaszto.current(0)
        if alkalmazottak:
            self.alkalmazott_valaszto.current(0)
        if szolgaltatasok:
            self.szolgaltatas_valaszto.current(0)
        self.pultok = pultok
        self._naptar_frissitese()
        self._foglalasok_frissitese()
        self._sablon_lista_frissitese()
        self._torzsadat_frissitese()

    def _demo_betoltese(self) -> None:
        from seed.betolt import betolt

        try:
            betolt(self.db_utvonal)
        except Exception as exc:  # noqa: BLE001 - a felhasználónak jelezzük, nem omlunk össze
            messagebox.showinfo(
                "Demóadat",
                f"A demóadat betöltése nem sikerült (valószínűleg már be van töltve):\n{exc}",
            )
        self.conn.close()
        self.conn = migracio.kapcsolat_nyitas(self.db_utvonal)
        self._szervezetek_betoltese()

    # ------------------------------------------------------------------
    # Naptár
    # ------------------------------------------------------------------

    def _elozo_het(self) -> None:
        self.het_kezdete -= timedelta(days=7)
        self._naptar_frissitese()

    def _kovetkezo_het(self) -> None:
        self.het_kezdete += timedelta(days=7)
        self._naptar_frissitese()

    def _naptar_frissitese(self) -> None:
        for gyerek in self.naptar_grid.winfo_children():
            gyerek.destroy()
        self.het_cimke.config(
            text=f"Hét: {self.het_kezdete.isoformat()} – "
            f"{(self.het_kezdete + timedelta(days=6)).isoformat()}"
        )
        if not self.bolt_id:
            return

        muszakok = api.het_muszakjai(
            self.conn,
            szervezet_id=self.szervezet_id,
            het_kezdete_datum=self.het_kezdete.isoformat(),
            bolt_id=self.bolt_id,
        )
        self.muszak_terkep = {(m["kezdet"][:10], m["pult_id"]): m for m in muszakok}

        ttk.Label(self.naptar_grid, text="Nap", width=12).grid(row=0, column=0, sticky="w")
        for oszlop, pult in enumerate(self.pultok, start=1):
            ttk.Label(
                self.naptar_grid, text=pult["nev"], width=18, font=("TkDefaultFont", 9, "bold")
            ).grid(row=0, column=oszlop, sticky="w")

        for sor_index, nap_nev in enumerate(_NAPOK, start=1):
            nap = self.het_kezdete + timedelta(days=sor_index - 1)
            datum_str = nap.isoformat()
            ttk.Label(self.naptar_grid, text=f"{nap_nev} {datum_str}").grid(
                row=sor_index, column=0, sticky="w"
            )
            for oszlop, pult in enumerate(self.pultok, start=1):
                muszak = self.muszak_terkep.get((datum_str, pult["id"]))
                if muszak is None:
                    ttk.Label(self.naptar_grid, text="—", foreground="#999").grid(
                        row=sor_index, column=oszlop, sticky="w"
                    )
                    continue
                szoveg = (
                    f"{muszak['kezdet'][11:16]}–{muszak['veg'][11:16]} ({muszak['slot_szam']} slot)"
                )
                gomb = ttk.Button(
                    self.naptar_grid,
                    text=szoveg,
                    command=lambda m=muszak: self._muszak_kivalasztasa(m),
                )
                gomb.grid(row=sor_index, column=oszlop, sticky="w", padx=1, pady=1)

    def _muszak_kivalasztasa(self, muszak: dict) -> None:
        self.kivalasztott_muszak_id = muszak["muszak_id"]
        reszletek = api.muszak_reszletei(self.conn, muszak_id=muszak["muszak_id"])
        sorok = [
            f"Pult: {muszak['pult_nev']}   Alkalmazott: {muszak['alkalmazott_nev']}",
            f"Szolgáltatás: {muszak['szolgaltatas_nev']}",
            f"Időablak: {muszak['kezdet']} – {muszak['veg']}",
            "",
            "Blokkok:",
        ]
        if not reszletek["blokkok"]:
            sorok.append("  (nincs)")
        for b in reszletek["blokkok"]:
            sorok.append(f"  {b['tipus']:12s} {b['kezdet'][11:16]}–{b['veg'][11:16]}")
        sorok.append("")
        sorok.append(f"Slotok ({len(reszletek['slotok'])}):")
        for s in reszletek["slotok"]:
            kod = f"  [{s['foglalasi_kod']}]" if s["foglalasi_kod"] else ""
            sorok.append(f"  {s['kezdet'][11:16]}–{s['veg'][11:16]}  {s['allapot']}{kod}")

        self.reszletek_szoveg.config(state="normal")
        self.reszletek_szoveg.delete("1.0", "end")
        self.reszletek_szoveg.insert("1.0", "\n".join(sorok))
        self.reszletek_szoveg.config(state="disabled")

    def _sablon_valasztva(self, _esemeny=None) -> None:
        sablon = api.SABLONOK.get(self.sablon_valaszto.get())
        if not sablon or sablon["idotartam_perc"] is None:
            return
        for mezo, kulcs in (
            (self.idotartam_mezo, "idotartam_perc"),
            (self.puffer_mezo, "puffer_utana_perc"),
            (self.min_racs_mezo, "min_racs_perc"),
            (self.arany_mezo, "foglalhato_arany"),
        ):
            mezo.delete(0, "end")
            mezo.insert(0, str(sablon[kulcs]))

    def _muszak_letrehozasa(self) -> None:
        self.urlap_uzenet.config(text="")
        try:
            pult_id = self._nevterkep_pult[self.pult_valaszto.get()]
            alkalmazott_id = self._nevterkep_alkalmazott[self.alkalmazott_valaszto.get()]
            szolgaltatas_id = self._nevterkep_szolgaltatas[self.szolgaltatas_valaszto.get()]
            datum = self.datum_mezo.get().strip()
            datetime.fromisoformat(datum)  # csak formátum-ellenőrzés
            kezdo_ora = int(self.kezdet_ora_mezo.get())
            veg_ora = int(self.veg_ora_mezo.get())
            kezdet = f"{datum}T{kezdo_ora:02d}:00:00Z"
            veg = f"{datum}T{veg_ora:02d}:00:00Z"
            idotartam_perc = int(self.idotartam_mezo.get())
            puffer_utana_perc = int(self.puffer_mezo.get())
            min_racs_perc = int(self.min_racs_mezo.get())
            foglalhato_arany = float(self.arany_mezo.get())
            blokk_szabaly = api.SABLONOK.get(self.sablon_valaszto.get(), {}).get(
                "blokk_szabaly", {"szunetek": []}
            )
        except (KeyError, ValueError) as exc:
            self.urlap_uzenet.config(text=f"Hibás mező: {exc}")
            return

        eredmeny = api.muszak_felvitel(
            self.conn,
            szervezet_id=self.szervezet_id,
            bolt_id=self.bolt_id,
            pult_id=pult_id,
            alkalmazott_id=alkalmazott_id,
            szolgaltatas_id=szolgaltatas_id,
            kezdet=kezdet,
            veg=veg,
            idotartam_perc=idotartam_perc,
            puffer_utana_perc=puffer_utana_perc,
            min_racs_perc=min_racs_perc,
            foglalhato_arany=foglalhato_arany,
            blokk_szabaly=blokk_szabaly,
        )
        if eredmeny.get("hiba"):
            self.urlap_uzenet.config(text=eredmeny["hiba"], foreground="#a00")
        elif eredmeny["kihagyva"]:
            self.urlap_uzenet.config(
                text=f"Létrehozva, de kihagyva (kivétel nap: {eredmeny['kihagyas_oka']})",
                foreground="#a60",
            )
        else:
            self.urlap_uzenet.config(
                text=f"Létrehozva: {eredmeny['slot_szam']} slot, {eredmeny['blokk_szam']} blokk.",
                foreground="#070",
            )
        self._naptar_frissitese()

    # ------------------------------------------------------------------
    # Foglalások
    # ------------------------------------------------------------------

    def _foglalasok_frissitese(self) -> None:
        for sor in self.foglalasok_fa.get_children():
            self.foglalasok_fa.delete(sor)
        if not self.bolt_id:
            return
        for f in api.foglalasok(self.conn, szervezet_id=self.szervezet_id, bolt_id=self.bolt_id):
            self.foglalasok_fa.insert(
                "",
                "end",
                iid=f["foglalasi_kod"],
                values=(f["foglalasi_kod"], f["slot_kezdet"], f["slot_veg"], f["allapot"]),
            )

    def _foglalas_lemondasa(self) -> None:
        kivalasztott = self.foglalasok_fa.selection()
        if not kivalasztott:
            messagebox.showinfo("Lemondás", "Válassz ki egy foglalást a listából.")
            return
        foglalasi_kod = kivalasztott[0]
        eredmeny = api.foglalas_lemond(self.conn, foglalasi_kod=foglalasi_kod)
        messagebox.showinfo("Lemondás", f"Eredmény: {eredmeny.value}")
        self._foglalasok_frissitese()
        self._naptar_frissitese()

    # ------------------------------------------------------------------
    # Sablonok és hét-másolás
    # ------------------------------------------------------------------

    def _sablon_uzenet_ir(self, szoveg: str) -> None:
        self.sablon_uzenet.config(state="normal")
        self.sablon_uzenet.delete("1.0", "end")
        self.sablon_uzenet.insert("1.0", szoveg)
        self.sablon_uzenet.config(state="disabled")

    def _sablon_lista_frissitese(self) -> None:
        self.sablon_lista.delete(0, "end")
        self._sablon_id_lista = []
        if not self.bolt_id:
            return
        for sablon in api.muszak_sablonok(
            self.conn, szervezet_id=self.szervezet_id, bolt_id=self.bolt_id
        ):
            self.sablon_lista.insert(
                "end", f"{sablon['nev']} ({sablon['kezdet_ora']:02d}–{sablon['veg_ora']:02d} óra)"
            )
            self._sablon_id_lista.append(sablon["id"])

    def _kivalasztott_sablon_id(self) -> str | None:
        kijeloles = self.sablon_lista.curselection()
        if not kijeloles:
            return None
        return self._sablon_id_lista[kijeloles[0]]

    def _sablon_mentese_kivalasztottbol(self) -> None:
        if not self.kivalasztott_muszak_id:
            self._sablon_uzenet_ir("Előbb válassz ki egy műszakot a Naptár fülön.")
            return
        nev = self.sablon_nev_mezo.get().strip() or "Névtelen sablon"
        eredmeny = api.muszak_sablon_mentese(
            self.conn, muszak_id=self.kivalasztott_muszak_id, nev=nev
        )
        if eredmeny["hiba"]:
            self._sablon_uzenet_ir(f"Hiba: {eredmeny['hiba']}")
        else:
            self._sablon_uzenet_ir(f"Sablon elmentve: {nev} (id: {eredmeny['sablon_id']})")
        self._sablon_lista_frissitese()

    def _sablon_alkalmazasa_napra(self) -> None:
        sablon_id = self._kivalasztott_sablon_id()
        if sablon_id is None:
            self._sablon_uzenet_ir("Előbb válassz ki egy sablont a listából.")
            return
        datum = self.sablon_alkalmaz_datum_mezo.get().strip()
        eredmeny = api.muszak_sablon_alkalmazasa_napra(self.conn, sablon_id=sablon_id, datum=datum)
        if eredmeny["hiba"]:
            self._sablon_uzenet_ir(f"Hiba: {eredmeny['hiba']}")
        elif eredmeny["kihagyva"]:
            self._sablon_uzenet_ir(f"{datum}: kihagyva (kivétel nap: {eredmeny['kihagyas_oka']})")
        else:
            self._sablon_uzenet_ir(f"{datum}: létrehozva, {eredmeny['slot_szam']} slot.")
        self._naptar_frissitese()

    def _sablon_alkalmazasa_hetre(self) -> None:
        sablon_id = self._kivalasztott_sablon_id()
        if sablon_id is None:
            self._sablon_uzenet_ir("Előbb válassz ki egy sablont a listából.")
            return
        het_kezdete = self.sablon_alkalmaz_datum_mezo.get().strip()
        eredmenyek = api.muszak_sablon_alkalmazasa_hetre(
            self.conn, sablon_id=sablon_id, het_kezdete_datum=het_kezdete
        )
        sorok = [f"Hét: {het_kezdete}-tól, 7 nap"]
        for i, eredmeny in enumerate(eredmenyek):
            nap = f"+{i} nap"
            if eredmeny["hiba"]:
                sorok.append(f"  {nap}: HIBA — {eredmeny['hiba']}")
            elif eredmeny["kihagyva"]:
                sorok.append(f"  {nap}: kihagyva ({eredmeny['kihagyas_oka']})")
            else:
                sorok.append(f"  {nap}: {eredmeny['slot_szam']} slot")
        self._sablon_uzenet_ir("\n".join(sorok))
        self._naptar_frissitese()

    def _het_masolasa(self) -> None:
        forras = self.masolas_forras_mezo.get().strip()
        cel = self.masolas_cel_mezo.get().strip()
        if not cel:
            self._sablon_uzenet_ir("Add meg a cél hét kezdetét (ÉÉÉÉ-HH-NN).")
            return
        eredmenyek = api.het_masolasa(
            self.conn,
            szervezet_id=self.szervezet_id,
            forras_het_kezdete=forras,
            cel_het_kezdete=cel,
            bolt_id=self.bolt_id,
        )
        if not eredmenyek:
            self._sablon_uzenet_ir(f"A {forras} hetén nincs másolható műszak ehhez a bolthoz.")
        else:
            sorok = [f"{forras} → {cel}: {len(eredmenyek)} műszak másolva"]
            for eredmeny in eredmenyek:
                if eredmeny["hiba"]:
                    sorok.append(f"  HIBA — {eredmeny['hiba']}")
                elif eredmeny["kihagyva"]:
                    sorok.append(f"  kihagyva ({eredmeny['kihagyas_oka']})")
                else:
                    sorok.append(f"  {eredmeny['slot_szam']} slot")
            self._sablon_uzenet_ir("\n".join(sorok))
        self._naptar_frissitese()

    # ------------------------------------------------------------------
    # Törzsadat-szerkesztés
    # ------------------------------------------------------------------

    def _torzsadat_uzenet_ir(self, szoveg: str) -> None:
        self.torzsadat_uzenet.config(text=szoveg)

    def _torzsadat_frissitese(self) -> None:
        self._bolt_id_lista = []
        self.bolt_lista.delete(0, "end")
        if self.szervezet_id:
            for bolt in api.boltok(self.conn, szervezet_id=self.szervezet_id):
                self.bolt_lista.insert("end", bolt["nev"])
                self._bolt_id_lista.append(bolt["id"])

        self._pult_id_lista = []
        self.pult_lista.delete(0, "end")
        self._alkalmazott_id_lista = []
        self.alkalmazott_lista.delete(0, "end")
        self._szolgaltatas_id_lista = []
        self.szolgaltatas_lista.delete(0, "end")
        self._kivetel_id_lista = []
        self.kivetel_lista.delete(0, "end")
        if not self.bolt_id:
            return

        for pult in api.pultok(self.conn, bolt_id=self.bolt_id):
            self.pult_lista.insert("end", pult["nev"])
            self._pult_id_lista.append(pult["id"])
        for alkalmazott in api.alkalmazottak(self.conn, bolt_id=self.bolt_id):
            self.alkalmazott_lista.insert("end", alkalmazott["nev"])
            self._alkalmazott_id_lista.append(alkalmazott["id"])
        for szolgaltatas in api.szolgaltatasok(self.conn, bolt_id=self.bolt_id):
            self.szolgaltatas_lista.insert(
                "end", f"{szolgaltatas['nev']} ({szolgaltatas['alap_idotartam_perc']} perc)"
            )
            self._szolgaltatas_id_lista.append(szolgaltatas["id"])
        kivetel_bolt = self.bolt_id if self.kivetel_csak_bolt_valtozo.get() else None
        for kivetel in api.kivetel_napok(
            self.conn, szervezet_id=self.szervezet_id, bolt_id=kivetel_bolt
        ):
            szintjelzo = "bolt" if kivetel["bolt_id"] else "szervezet"
            self.kivetel_lista.insert(
                "end", f"{kivetel['datum']} — {kivetel['indok']} ({szintjelzo})"
            )
            self._kivetel_id_lista.append(kivetel["id"])

    def _kivalasztott_id(self, lista: tk.Listbox, id_lista: list[str]) -> str | None:
        kijeloles = lista.curselection()
        if not kijeloles:
            return None
        return id_lista[kijeloles[0]]

    def _bolt_hozzaadasa_ui(self, mezo: ttk.Entry) -> None:
        eredmeny = api.bolt_hozzaadasa(self.conn, szervezet_id=self.szervezet_id, nev=mezo.get())
        if eredmeny["hiba"]:
            self._torzsadat_uzenet_ir(f"Hiba: {eredmeny['hiba']}")
            return
        self._torzsadat_uzenet_ir("Bolt felvéve.")
        self._bolt_lista_frissitese()
        self._torzsadat_frissitese()

    def _bolt_szerkesztese_ui(self, lista: tk.Listbox, mezo: ttk.Entry) -> None:
        bolt_id = self._kivalasztott_id(lista, self._bolt_id_lista)
        if bolt_id is None:
            self._torzsadat_uzenet_ir("Előbb válassz ki egy boltot a listából.")
            return
        eredmeny = api.bolt_szerkesztese(self.conn, bolt_id=bolt_id, nev=mezo.get())
        if eredmeny["hiba"]:
            self._torzsadat_uzenet_ir(f"Hiba: {eredmeny['hiba']}")
            return
        self._torzsadat_uzenet_ir("Bolt átnevezve.")
        self._bolt_lista_frissitese()
        self._torzsadat_frissitese()

    def _pult_hozzaadasa_ui(self, mezo: ttk.Entry) -> None:
        if not self.bolt_id:
            self._torzsadat_uzenet_ir("Előbb válassz ki egy boltot a felső sávban.")
            return
        eredmeny = api.pult_hozzaadasa(
            self.conn, szervezet_id=self.szervezet_id, bolt_id=self.bolt_id, nev=mezo.get()
        )
        self._torzsadat_uzenet_ir(eredmeny["hiba"] or "Pult felvéve.")
        self._bolt_valasztva()

    def _pult_szerkesztese_ui(self, lista: tk.Listbox, mezo: ttk.Entry) -> None:
        pult_id = self._kivalasztott_id(lista, self._pult_id_lista)
        if pult_id is None:
            self._torzsadat_uzenet_ir("Előbb válassz ki egy pultot a listából.")
            return
        eredmeny = api.pult_szerkesztese(self.conn, pult_id=pult_id, nev=mezo.get())
        self._torzsadat_uzenet_ir(eredmeny["hiba"] or "Pult átnevezve.")
        self._bolt_valasztva()

    def _alkalmazott_hozzaadasa_ui(self, mezo: ttk.Entry) -> None:
        if not self.bolt_id:
            self._torzsadat_uzenet_ir("Előbb válassz ki egy boltot a felső sávban.")
            return
        eredmeny = api.alkalmazott_hozzaadasa(
            self.conn, szervezet_id=self.szervezet_id, bolt_id=self.bolt_id, nev=mezo.get()
        )
        self._torzsadat_uzenet_ir(eredmeny["hiba"] or "Alkalmazott felvéve.")
        self._bolt_valasztva()

    def _alkalmazott_szerkesztese_ui(self, lista: tk.Listbox, mezo: ttk.Entry) -> None:
        alkalmazott_id = self._kivalasztott_id(lista, self._alkalmazott_id_lista)
        if alkalmazott_id is None:
            self._torzsadat_uzenet_ir("Előbb válassz ki egy alkalmazottat a listából.")
            return
        eredmeny = api.alkalmazott_szerkesztese(
            self.conn, alkalmazott_id=alkalmazott_id, nev=mezo.get()
        )
        self._torzsadat_uzenet_ir(eredmeny["hiba"] or "Alkalmazott átnevezve.")
        self._bolt_valasztva()

    def _szolgaltatas_hozzaadasa_ui(self) -> None:
        if not self.bolt_id:
            self._torzsadat_uzenet_ir("Előbb válassz ki egy boltot a felső sávban.")
            return
        try:
            idotartam = int(self.szolgaltatas_idotartam_mezo.get())
        except ValueError:
            self._torzsadat_uzenet_ir("Az időtartam egész szám kell legyen.")
            return
        eredmeny = api.szolgaltatas_hozzaadasa(
            self.conn,
            szervezet_id=self.szervezet_id,
            bolt_id=self.bolt_id,
            nev=self.szolgaltatas_nev_mezo.get(),
            alap_idotartam_perc=idotartam,
        )
        self._torzsadat_uzenet_ir(eredmeny["hiba"] or "Szolgáltatás felvéve.")
        self._bolt_valasztva()

    def _szolgaltatas_szerkesztese_ui(self) -> None:
        szolgaltatas_id = self._kivalasztott_id(
            self.szolgaltatas_lista, self._szolgaltatas_id_lista
        )
        if szolgaltatas_id is None:
            self._torzsadat_uzenet_ir("Előbb válassz ki egy szolgáltatást a listából.")
            return
        try:
            idotartam = int(self.szolgaltatas_idotartam_mezo.get())
        except ValueError:
            self._torzsadat_uzenet_ir("Az időtartam egész szám kell legyen.")
            return
        eredmeny = api.szolgaltatas_szerkesztese(
            self.conn,
            szolgaltatas_id=szolgaltatas_id,
            nev=self.szolgaltatas_nev_mezo.get(),
            alap_idotartam_perc=idotartam,
        )
        self._torzsadat_uzenet_ir(eredmeny["hiba"] or "Szolgáltatás módosítva.")
        self._bolt_valasztva()

    def _kivetel_nap_hozzaadasa_ui(self) -> None:
        bolt_id = self.bolt_id if self.kivetel_csak_bolt_valtozo.get() else None
        eredmeny = api.kivetel_nap_hozzaadasa(
            self.conn,
            szervezet_id=self.szervezet_id,
            bolt_id=bolt_id,
            datum=self.kivetel_datum_mezo.get().strip(),
            indok=self.kivetel_indok_mezo.get(),
        )
        self._torzsadat_uzenet_ir(eredmeny["hiba"] or "Kivételnap felvéve.")
        self._torzsadat_frissitese()
        self._naptar_frissitese()

    # ------------------------------------------------------------------
    # Ütközéslista
    # ------------------------------------------------------------------

    def _utkozes_fulet_felepit(self) -> None:
        fejlec = ttk.Frame(self.utkozes_ful)
        fejlec.pack(side="top", fill="x")
        ttk.Button(
            fejlec, text="Frissítés (a teljes szervezetre)", command=self._utkozeslista_frissitese
        ).pack(side="left")
        ttk.Button(
            fejlec,
            text="Frissítés (csak a kiválasztott boltra)",
            command=lambda: self._utkozeslista_frissitese(csak_bolt=True),
        ).pack(side="left", padx=4)
        self.utkozes_szamlalo = ttk.Label(fejlec, text="")
        self.utkozes_szamlalo.pack(side="left", padx=12)

        oszlopok = ("tipus", "pult", "alkalmazott", "kezdet", "veg", "uzenet")
        self.utkozes_fa = ttk.Treeview(
            self.utkozes_ful, columns=oszlopok, show="headings", height=25
        )
        cimek = ("Típus", "Pult", "Alkalmazott", "Kezdet", "Vég", "Üzenet")
        szelessegek = (140, 120, 120, 150, 150, 400)
        for oszlop, cim, szelesseg in zip(oszlopok, cimek, szelessegek, strict=True):
            self.utkozes_fa.heading(oszlop, text=cim)
            self.utkozes_fa.column(oszlop, width=szelesseg)
        self.utkozes_fa.pack(fill="both", expand=True, pady=6)

    def _utkozeslista_frissitese(self, *, csak_bolt: bool = False) -> None:
        for sor in self.utkozes_fa.get_children():
            self.utkozes_fa.delete(sor)
        if not self.szervezet_id:
            return
        bolt_id = self.bolt_id if csak_bolt else None
        problemak = api.utkozeslista(self.conn, szervezet_id=self.szervezet_id, bolt_id=bolt_id)
        for p in problemak:
            self.utkozes_fa.insert(
                "",
                "end",
                values=(
                    f"{p['tipus']} / {p['szabaly']}",
                    p["pult_nev"],
                    p["alkalmazott_nev"],
                    p["kezdet"],
                    p["veg"],
                    p["uzenet"],
                ),
            )
        self.utkozes_szamlalo.config(text=f"{len(problemak)} probléma")

    # ------------------------------------------------------------------

    def _bezaras(self) -> None:
        self.conn.close()
        self.destroy()


def main() -> int:
    app = AdminApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
