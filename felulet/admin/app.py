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
        fulek.add(self.naptar_ful, text="Naptár és műszakok")
        fulek.add(self.foglalasok_ful, text="Foglalások")

        self._naptar_fulet_felepit()
        self._foglalasok_fulet_felepit()

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
        boltok = api.boltok(self.conn, szervezet_id=self.szervezet_id) if self.szervezet_id else []
        self._nevterkep_bolt = {b["nev"]: b["id"] for b in boltok}
        self.bolt_valaszto["values"] = list(self._nevterkep_bolt)
        if boltok:
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
        if eredmeny["kihagyva"]:
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

    def _bezaras(self) -> None:
        self.conn.close()
        self.destroy()


def main() -> int:
    app = AdminApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
