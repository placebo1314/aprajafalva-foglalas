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

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.api import adminszolgaltatas as api  # noqa: E402
from core.repo import migracio  # noqa: E402
from seed.betolt import ALAP_DB_PATH  # noqa: E402

_DAYS = ["hétfő", "kedd", "szerda", "csütörtök", "péntek", "szombat", "vasárnap"]


def _week_monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


class AdminApp(tk.Tk):
    def __init__(self, db_path: str | None = None) -> None:
        super().__init__()
        self.title("Aprajafalva — admin beosztásszerkesztő")
        self.geometry("1100x700")

        self.db_path = db_path or str(ALAP_DB_PATH)
        self.conn = migracio.conn_nyitas(self.db_path)
        migracio.migral(self.conn)

        self.org_id: str | None = None
        self.shop_id: str | None = None
        self.week_start = _week_monday(date.today())
        self.counters: list[dict] = []
        self.shift_map: dict[tuple[str, str], dict] = {}  # (datum, pult_id) -> muszak
        self.selected_shift_id: str | None = None

        self.protocol("WM_DELETE_WINDOW", self._close)
        self._build()
        self._orgs_load()

    # ------------------------------------------------------------------
    # Felépítés
    # ------------------------------------------------------------------

    def _build(self) -> None:
        felso = ttk.Frame(self, padding=6)
        felso.pack(side="top", fill="x")

        ttk.Label(felso, text="Adatbázis:").pack(side="left")
        ttk.Label(felso, text=self.db_path, foreground="#555").pack(side="left", padx=(2, 12))
        ttk.Button(felso, text="Demóadat betöltése", command=self._demo_load).pack(
            side="left", padx=4
        )

        ttk.Label(felso, text="Szervezet:").pack(side="left", padx=(16, 2))
        self.org_selector = ttk.Combobox(felso, state="readonly", width=20)
        self.org_selector.pack(side="left")
        self.org_selector.bind("<<ComboboxSelected>>", self._org_selected)

        ttk.Label(felso, text="Bolt:").pack(side="left", padx=(16, 2))
        self.shop_selector = ttk.Combobox(felso, state="readonly", width=20)
        self.shop_selector.pack(side="left")
        self.shop_selector.bind("<<ComboboxSelected>>", self._shop_selected)

        tabs = ttk.Notebook(self)
        tabs.pack(side="top", fill="both", expand=True)

        self.calendar_tab = ttk.Frame(tabs, padding=6)
        self.bookings_tab = ttk.Frame(tabs, padding=6)
        self.template_tab = ttk.Frame(tabs, padding=6)
        self.master_data_tab = ttk.Frame(tabs, padding=6)
        self.conflict_tab = ttk.Frame(tabs, padding=6)
        tabs.add(self.calendar_tab, text="Naptár és műszakok")
        tabs.add(self.bookings_tab, text="Foglalások")
        tabs.add(self.template_tab, text="Sablonok és hét-másolás")
        tabs.add(self.master_data_tab, text="Törzsadat")
        tabs.add(self.conflict_tab, text="Ütközéslista")

        self._calendar_tab_build()
        self._bookings_tab_build()
        self._template_tab_build()
        self._master_data_tab_build()
        self._conflict_tab_build()

    def _calendar_tab_build(self) -> None:
        fejlec = ttk.Frame(self.calendar_tab)
        fejlec.pack(side="top", fill="x")
        ttk.Button(fejlec, text="◀ előző hét", command=self._previous_week).pack(side="left")
        self.week_label = ttk.Label(fejlec, text="", font=("TkDefaultFont", 10, "bold"))
        self.week_label.pack(side="left", padx=12)
        ttk.Button(fejlec, text="következő hét ▶", command=self._next_week).pack(side="left")

        also = ttk.Frame(self.calendar_tab)
        also.pack(side="top", fill="both", expand=True, pady=(8, 0))

        self.calendar_grid = ttk.Frame(also)
        self.calendar_grid.pack(side="left", fill="both", expand=True)

        jobb = ttk.Frame(also, width=380)
        jobb.pack(side="left", fill="y", padx=(12, 0))
        jobb.pack_propagate(False)

        ttk.Label(
            jobb, text="Kiválasztott műszak részletei", font=("TkDefaultFont", 9, "bold")
        ).pack(anchor="w")
        self.details_szoveg = tk.Text(jobb, height=16, width=44, state="disabled")
        self.details_szoveg.pack(fill="x", pady=(2, 12))

        ttk.Separator(jobb).pack(fill="x", pady=6)
        ttk.Label(jobb, text="Új műszak felvitele", font=("TkDefaultFont", 9, "bold")).pack(
            anchor="w"
        )
        self._shift_form_build(jobb)

    def _shift_form_build(self, szulo: tk.Widget) -> None:
        form = ttk.Frame(szulo)
        form.pack(fill="x", pady=4)

        def row(label: str) -> ttk.Combobox:
            frame = ttk.Frame(form)
            frame.pack(fill="x", pady=1)
            ttk.Label(frame, text=label, width=14).pack(side="left")
            box = ttk.Combobox(frame, state="readonly", width=24)
            box.pack(side="left", fill="x", expand=True)
            return box

        self.counter_selector = row("Pult:")
        self.employee_selector = row("Alkalmazott:")
        self.service_selector = row("Szolgáltatás:")
        self.template_selector = row("Sablon:")
        self.template_selector["values"] = [k for k in api.TEMPLATES]
        self.template_selector.set("gyors_penztar")
        self.template_selector.bind("<<ComboboxSelected>>", self._template_selected)

        def szoveg_row(label: str, alap: str = "") -> ttk.Entry:
            frame = ttk.Frame(form)
            frame.pack(fill="x", pady=1)
            ttk.Label(frame, text=label, width=14).pack(side="left")
            field = ttk.Entry(frame)
            field.insert(0, alap)
            field.pack(side="left", fill="x", expand=True)
            return field

        self.date_field = szoveg_row("Dátum (ÉÉÉÉ-HH-NN):", self.week_start.isoformat())
        self.start_hour_field = szoveg_row("Kezdő óra (0-23):", "8")
        self.end_hour_field = szoveg_row("Végző óra (0-23):", "16")
        self.duration_field = szoveg_row("Időtartam (perc):", "10")
        self.buffer_field = szoveg_row("Puffer utána (perc):", "0")
        self.min_grid_field = szoveg_row("Min. rács (perc):", "10")
        self.ratio_field = szoveg_row("Foglalható arány (0-1):", "1.0")

        ttk.Button(form, text="Létrehozás", command=self._shift_create).pack(fill="x", pady=(6, 0))
        self.form_message = ttk.Label(form, text="", foreground="#a00", wraplength=340)
        self.form_message.pack(fill="x", pady=(4, 0))

    def _bookings_tab_build(self) -> None:
        ttk.Button(self.bookings_tab, text="Frissítés", command=self._bookings_refresh).pack(
            anchor="w"
        )
        oszlopok = ("kod", "kezdet", "veg", "allapot")
        self.bookings_fa = ttk.Treeview(
            self.bookings_tab, columns=oszlopok, show="headings", height=20
        )
        for oszlop, cim in zip(
            oszlopok, ("Foglalási kód", "Kezdet", "Vég", "Állapot"), strict=True
        ):
            self.bookings_fa.heading(oszlop, text=cim)
        self.bookings_fa.pack(fill="both", expand=True, pady=6)
        ttk.Button(self.bookings_tab, text="Lemondás", command=self._booking_lemondasa).pack(
            anchor="w"
        )

    def _template_tab_build(self) -> None:
        bal = ttk.Frame(self.template_tab)
        bal.pack(side="left", fill="both", expand=True)
        jobb = ttk.Frame(self.template_tab, width=320)
        jobb.pack(side="left", fill="y", padx=(12, 0))
        jobb.pack_propagate(False)

        ttk.Label(bal, text="Mentett sablonok", font=("TkDefaultFont", 9, "bold")).pack(anchor="w")
        self.template_list = tk.Listbox(bal, height=12)
        self.template_list.pack(fill="both", expand=True, pady=(2, 8))
        self._template_id_list: list[str] = []

        mentes_frame = ttk.Frame(bal)
        mentes_frame.pack(fill="x", pady=4)
        ttk.Label(mentes_frame, text="Új sablon neve:").pack(side="left")
        self.template_name_field = ttk.Entry(mentes_frame)
        self.template_name_field.pack(side="left", fill="x", expand=True, padx=4)
        ttk.Button(
            mentes_frame,
            text="Mentés a kiválasztott műszakból",
            command=self._template_save_from_selected,
        ).pack(side="left")

        apply_frame = ttk.Frame(bal)
        apply_frame.pack(fill="x", pady=4)
        ttk.Label(apply_frame, text="Alkalmazás dátuma:").pack(side="left")
        self.template_apply_date_field = ttk.Entry(apply_frame, width=12)
        self.template_apply_date_field.insert(0, self.week_start.isoformat())
        self.template_apply_date_field.pack(side="left", padx=4)
        ttk.Button(apply_frame, text="Erre a napra", command=self._template_apply_for_day).pack(
            side="left", padx=2
        )
        ttk.Button(
            apply_frame,
            text="Erre a hétre (7 nap)",
            command=self._template_apply_for_week,
        ).pack(side="left", padx=2)

        ttk.Separator(bal).pack(fill="x", pady=8)
        ttk.Label(bal, text="Hét másolása", font=("TkDefaultFont", 9, "bold")).pack(anchor="w")
        copy_frame = ttk.Frame(bal)
        copy_frame.pack(fill="x", pady=4)
        ttk.Label(copy_frame, text="Forrás hét kezdete:").pack(side="left")
        self.copy_source_field = ttk.Entry(copy_frame, width=12)
        self.copy_source_field.insert(0, self.week_start.isoformat())
        self.copy_source_field.pack(side="left", padx=4)
        ttk.Label(copy_frame, text="Cél hét kezdete:").pack(side="left")
        self.copy_target_field = ttk.Entry(copy_frame, width=12)
        self.copy_target_field.pack(side="left", padx=4)
        ttk.Button(copy_frame, text="Másolás", command=self._week_copy).pack(side="left")

        ttk.Label(jobb, text="Eredmény", font=("TkDefaultFont", 9, "bold")).pack(anchor="w")
        self.template_message = tk.Text(jobb, height=20, width=42, state="disabled")
        self.template_message.pack(fill="both", expand=True, pady=(2, 0))

    def _master_data_tab_build(self) -> None:
        """Bolt/pult/alkalmazott/szolgáltatás felvitele+szerkesztése és
        kivételnap felvétele — ma csak a `seed`-ből jött adat volt
        elérhető, ez teszi lehetővé, hogy az admin saját maga bővítse.
        Nem szép, működik: egy-egy kis lista + két mező + két gomb
        (Hozzáadás / Kiválasztott szerkesztése) blokkonként."""
        bal = ttk.Frame(self.master_data_tab)
        bal.pack(side="left", fill="both", expand=True)
        jobb = ttk.Frame(self.master_data_tab, width=340)
        jobb.pack(side="left", fill="y", padx=(12, 0))
        jobb.pack_propagate(False)

        self.shop_list = self._master_data_block_build(
            bal,
            cim="Boltok",
            add_szoveg="Hozzáadás",
            add_fn=self._shop_add_ui,
            update_fn=self._shop_update_ui,
        )
        self.shop_list.bind("<<ListboxSelect>>", self._shop_list_selected)

        # "Bolti tudás" (docs/blueprint.md 10. szakasz): a bolt_info
        # eszköz ezt olvassa vissza — a modell sosem generálja. Kiválasztás
        # betölti a mezőt, hogy szerkesztéskor ne a semmiből kelljen újra
        # megírni egy már meglévő leírást.
        ttk.Label(bal, text="Megjelenés (a kiválasztott bolté)").pack(anchor="w", pady=(6, 0))
        self.shop_appearance_field = tk.Text(bal, height=3, wrap="word")
        self.shop_appearance_field.pack(fill="x", pady=(2, 2))
        ttk.Button(bal, text="Megjelenés mentése", command=self._shop_description_update_ui).pack(
            anchor="w", pady=(0, 10)
        )

        self.counter_list = self._master_data_block_build(
            bal,
            cim="Pultok (a kiválasztott boltban)",
            add_szoveg="Hozzáadás",
            add_fn=self._counter_add_ui,
            update_fn=self._counter_update_ui,
        )
        self.employee_list = self._master_data_block_build(
            bal,
            cim="Alkalmazottak (a kiválasztott boltban)",
            add_szoveg="Hozzáadás",
            add_fn=self._employee_add_ui,
            update_fn=self._employee_update_ui,
        )

        ttk.Label(
            jobb, text="Szolgáltatások (a kiválasztott boltban)", font=("TkDefaultFont", 9, "bold")
        ).pack(anchor="w")
        self.service_list = tk.Listbox(jobb, height=6)
        self.service_list.pack(fill="x", pady=(2, 4))
        self.service_list.bind("<<ListboxSelect>>", self._service_list_selected)
        service_form = ttk.Frame(jobb)
        service_form.pack(fill="x")
        ttk.Label(service_form, text="Név:").grid(row=0, column=0, sticky="w")
        self.service_name_field = ttk.Entry(service_form)
        self.service_name_field.grid(row=0, column=1, sticky="ew")
        ttk.Label(service_form, text="Időtartam (perc):").grid(row=1, column=0, sticky="w")
        self.service_duration_field = ttk.Entry(service_form)
        self.service_duration_field.grid(row=1, column=1, sticky="ew")
        # "Bolti tudás" (docs/blueprint.md 10. szakasz) — a bolt_info
        # "termek"/"ar" ága ezt olvassa vissza, a modell sosem generálja.
        ttk.Label(service_form, text="Termékleírás:").grid(row=2, column=0, sticky="nw")
        self.service_description_field = tk.Text(service_form, height=3, wrap="word")
        self.service_description_field.grid(row=2, column=1, sticky="ew")
        ttk.Label(service_form, text="Ár:").grid(row=3, column=0, sticky="w")
        self.service_price_field = ttk.Entry(service_form)
        self.service_price_field.grid(row=3, column=1, sticky="ew")
        service_form.columnconfigure(1, weight=1)
        service_buttons = ttk.Frame(jobb)
        service_buttons.pack(fill="x", pady=(2, 10))
        ttk.Button(service_buttons, text="Hozzáadás", command=self._service_add_ui).pack(
            side="left"
        )
        ttk.Button(
            service_buttons,
            text="Kiválasztott szerkesztése",
            command=self._service_update_ui,
        ).pack(side="left", padx=4)

        ttk.Separator(jobb).pack(fill="x", pady=6)
        ttk.Label(jobb, text="Kivételnapok", font=("TkDefaultFont", 9, "bold")).pack(anchor="w")
        self.exception_list = tk.Listbox(jobb, height=6)
        self.exception_list.pack(fill="x", pady=(2, 4))
        kiv_form = ttk.Frame(jobb)
        kiv_form.pack(fill="x")
        ttk.Label(kiv_form, text="Dátum (ÉÉÉÉ-HH-NN):").grid(row=0, column=0, sticky="w")
        self.exception_date_field = ttk.Entry(kiv_form)
        self.exception_date_field.grid(row=0, column=1, sticky="ew")
        ttk.Label(kiv_form, text="Indok:").grid(row=1, column=0, sticky="w")
        self.exception_reason_field = ttk.Entry(kiv_form)
        self.exception_reason_field.grid(row=1, column=1, sticky="ew")
        self.exception_only_shop_valtozo = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            kiv_form, text="csak a kiválasztott boltra", variable=self.exception_only_shop_valtozo
        ).grid(row=2, column=0, columnspan=2, sticky="w")
        kiv_form.columnconfigure(1, weight=1)
        ttk.Button(jobb, text="Kivételnap felvétele", command=self._exception_day_add_ui).pack(
            anchor="w", pady=(2, 10)
        )

        self.master_data_message = ttk.Label(jobb, text="", foreground="#a00", wraplength=320)
        self.master_data_message.pack(fill="x")

    def _master_data_block_build(self, szulo, *, cim, add_szoveg, add_fn, update_fn):
        ttk.Label(szulo, text=cim, font=("TkDefaultFont", 9, "bold")).pack(anchor="w", pady=(6, 0))
        listbox = tk.Listbox(szulo, height=4)
        listbox.pack(fill="x", pady=(2, 4))
        form = ttk.Frame(szulo)
        form.pack(fill="x")
        field = ttk.Entry(form)
        field.pack(side="left", fill="x", expand=True)
        ttk.Button(form, text=add_szoveg, command=lambda: add_fn(field)).pack(side="left", padx=2)
        ttk.Button(
            form, text="Kiválasztott szerkesztése", command=lambda: update_fn(listbox, field)
        ).pack(side="left")
        return listbox

    # ------------------------------------------------------------------
    # Adatbetöltés / -frissítés
    # ------------------------------------------------------------------

    def _orgs_load(self) -> None:
        orgs = api.orgs(self.conn)
        self._name_map_org = {s["nev"]: s["id"] for s in orgs}
        self.org_selector["values"] = list(self._name_map_org)
        if orgs:
            self.org_selector.current(0)
            self._org_selected()
        else:
            self.week_label.config(text="Nincs szervezet — töltsd be a demóadatot a fenti gombbal.")

    def _org_selected(self, _event=None) -> None:
        name = self.org_selector.get()
        self.org_id = self._name_map_org.get(name)
        self._shop_list_refresh(keep_selected=False)

    def _shop_list_refresh(self, *, keep_selected: bool = True) -> None:
        """A bolt-legördülő értékeinek frissítése — a törzsadat-fülről
        induló bolt hozzáadás/átnevezés ezt hívja, NEM a
        `_szervezet_valasztva`-t, mert az mindig az első boltra ugrana,
        elveszítve a felhasználó aktuális bolt-kiválasztását."""
        previous_shop_id = self.shop_id if keep_selected else None
        shops = api.shops(self.conn, org_id=self.org_id) if self.org_id else []
        self._name_map_shop = {b["nev"]: b["id"] for b in shops}
        self.shop_selector["values"] = list(self._name_map_shop)
        if not shops:
            return
        to_keep_name = next(
            (name for name, bid in self._name_map_shop.items() if bid == previous_shop_id), None
        )
        if to_keep_name is not None:
            self.shop_selector.set(to_keep_name)
        else:
            self.shop_selector.current(0)
        self._shop_selected()

    def _shop_selected(self, _event=None) -> None:
        name = self.shop_selector.get()
        self.shop_id = self._name_map_shop.get(name)
        if not self.shop_id:
            return
        counters = api.counters(self.conn, shop_id=self.shop_id)
        employees = api.employees(self.conn, shop_id=self.shop_id)
        services = api.services(self.conn, shop_id=self.shop_id)
        self._name_map_counter = {p["nev"]: p["id"] for p in counters}
        self._name_map_employee = {a["nev"]: a["id"] for a in employees}
        self._name_map_service = {s["nev"]: s["id"] for s in services}
        self.counter_selector["values"] = list(self._name_map_counter)
        self.employee_selector["values"] = list(self._name_map_employee)
        self.service_selector["values"] = list(self._name_map_service)
        if counters:
            self.counter_selector.current(0)
        if employees:
            self.employee_selector.current(0)
        if services:
            self.service_selector.current(0)
        self.counters = counters
        self._calendar_refresh()
        self._bookings_refresh()
        self._template_list_refresh()
        self._master_data_refresh()

    def _demo_load(self) -> None:
        from seed.betolt import betolt

        try:
            betolt(self.db_path)
        except Exception as exc:  # noqa: BLE001 - a felhasználónak jelezzük, nem omlunk össze
            messagebox.showinfo(
                "Demóadat",
                f"A demóadat betöltése nem sikerült (valószínűleg már be van töltve):\n{exc}",
            )
        self.conn.close()
        self.conn = migracio.conn_nyitas(self.db_path)
        self._orgs_load()

    # ------------------------------------------------------------------
    # Naptár
    # ------------------------------------------------------------------

    def _previous_week(self) -> None:
        self.week_start -= timedelta(days=7)
        self._calendar_refresh()

    def _next_week(self) -> None:
        self.week_start += timedelta(days=7)
        self._calendar_refresh()

    def _calendar_refresh(self) -> None:
        for gyerek in self.calendar_grid.winfo_children():
            gyerek.destroy()
        self.week_label.config(
            text=f"Hét: {self.week_start.isoformat()} – "
            f"{(self.week_start + timedelta(days=6)).isoformat()}"
        )
        if not self.shop_id:
            return

        shifts = api.week_shifts(
            self.conn,
            org_id=self.org_id,
            week_start_date=self.week_start.isoformat(),
            shop_id=self.shop_id,
        )
        self.shift_map = {(m["kezdet"][:10], m["pult_id"]): m for m in shifts}

        ttk.Label(self.calendar_grid, text="Nap", width=12).grid(row=0, column=0, sticky="w")
        for oszlop, counter in enumerate(self.counters, start=1):
            ttk.Label(
                self.calendar_grid, text=counter["nev"], width=18, font=("TkDefaultFont", 9, "bold")
            ).grid(row=0, column=oszlop, sticky="w")

        for row_index, day_name in enumerate(_DAYS, start=1):
            day = self.week_start + timedelta(days=row_index - 1)
            date_str = day.isoformat()
            ttk.Label(self.calendar_grid, text=f"{day_name} {date_str}").grid(
                row=row_index, column=0, sticky="w"
            )
            for oszlop, counter in enumerate(self.counters, start=1):
                shift = self.shift_map.get((date_str, counter["id"]))
                if shift is None:
                    ttk.Label(self.calendar_grid, text="—", foreground="#999").grid(
                        row=row_index, column=oszlop, sticky="w"
                    )
                    continue
                szoveg = (
                    f"{shift['kezdet'][11:16]}–{shift['veg'][11:16]} ({shift['slot_szam']} slot)"
                )
                button = ttk.Button(
                    self.calendar_grid,
                    text=szoveg,
                    command=lambda m=shift: self._shift_selection(m),
                )
                button.grid(row=row_index, column=oszlop, sticky="w", padx=1, pady=1)

    def _shift_selection(self, shift: dict) -> None:
        self.selected_shift_id = shift["muszak_id"]
        details = api.shift_details(self.conn, shift_id=shift["muszak_id"])
        rows = [
            f"Pult: {shift['pult_nev']}   Alkalmazott: {shift['alkalmazott_nev']}",
            f"Szolgáltatás: {shift['szolgaltatas_nev']}",
            f"Időablak: {shift['kezdet']} – {shift['veg']}",
            "",
            "Blokkok:",
        ]
        if not details["blokkok"]:
            rows.append("  (nincs)")
        for b in details["blokkok"]:
            rows.append(f"  {b['tipus']:12s} {b['kezdet'][11:16]}–{b['veg'][11:16]}")
        rows.append("")
        rows.append(f"Slotok ({len(details['slotok'])}):")
        for s in details["slotok"]:
            code = f"  [{s['foglalasi_kod']}]" if s["foglalasi_kod"] else ""
            rows.append(f"  {s['kezdet'][11:16]}–{s['veg'][11:16]}  {s['allapot']}{code}")

        self.details_szoveg.config(state="normal")
        self.details_szoveg.delete("1.0", "end")
        self.details_szoveg.insert("1.0", "\n".join(rows))
        self.details_szoveg.config(state="disabled")

    def _template_selected(self, _event=None) -> None:
        template = api.TEMPLATES.get(self.template_selector.get())
        if not template or template["idotartam_perc"] is None:
            return
        for field, key in (
            (self.duration_field, "idotartam_perc"),
            (self.buffer_field, "puffer_utana_perc"),
            (self.min_grid_field, "min_racs_perc"),
            (self.ratio_field, "foglalhato_arany"),
        ):
            field.delete(0, "end")
            field.insert(0, str(template[key]))

    def _shift_create(self) -> None:
        self.form_message.config(text="")
        try:
            counter_id = self._name_map_counter[self.counter_selector.get()]
            employee_id = self._name_map_employee[self.employee_selector.get()]
            service_id = self._name_map_service[self.service_selector.get()]
            date = self.date_field.get().strip()
            datetime.fromisoformat(date)  # csak formátum-ellenőrzés
            start_hour = int(self.start_hour_field.get())
            end_hour = int(self.end_hour_field.get())
            start = f"{date}T{start_hour:02d}:00:00Z"
            end = f"{date}T{end_hour:02d}:00:00Z"
            duration_minute = int(self.duration_field.get())
            buffer_after_minute = int(self.buffer_field.get())
            min_grid_minute = int(self.min_grid_field.get())
            bookable_ratio = float(self.ratio_field.get())
            block_rule = api.TEMPLATES.get(self.template_selector.get(), {}).get(
                "blokk_szabaly", {"szunetek": []}
            )
        except (KeyError, ValueError) as exc:
            self.form_message.config(text=f"Hibás mező: {exc}")
            return

        result = api.shift_felvitel(
            self.conn,
            org_id=self.org_id,
            shop_id=self.shop_id,
            counter_id=counter_id,
            employee_id=employee_id,
            service_id=service_id,
            start=start,
            end=end,
            duration_minute=duration_minute,
            buffer_after_minute=buffer_after_minute,
            min_grid_minute=min_grid_minute,
            bookable_ratio=bookable_ratio,
            block_rule=block_rule,
        )
        if result.get("hiba"):
            self.form_message.config(text=result["hiba"], foreground="#a00")
        elif result["kihagyva"]:
            self.form_message.config(
                text=f"Létrehozva, de kihagyva (kivétel nap: {result['kihagyas_oka']})",
                foreground="#a60",
            )
        else:
            self.form_message.config(
                text=f"Létrehozva: {result['slot_szam']} slot, {result['blokk_szam']} blokk.",
                foreground="#070",
            )
        self._calendar_refresh()

    # ------------------------------------------------------------------
    # Foglalások
    # ------------------------------------------------------------------

    def _bookings_refresh(self) -> None:
        for row in self.bookings_fa.get_children():
            self.bookings_fa.delete(row)
        if not self.shop_id:
            return
        for f in api.bookings(self.conn, org_id=self.org_id, shop_id=self.shop_id):
            self.bookings_fa.insert(
                "",
                "end",
                iid=f["foglalasi_kod"],
                values=(f["foglalasi_kod"], f["slot_kezdet"], f["slot_veg"], f["allapot"]),
            )

    def _booking_lemondasa(self) -> None:
        selected = self.bookings_fa.selection()
        if not selected:
            messagebox.showinfo("Lemondás", "Válassz ki egy foglalást a listából.")
            return
        booking_code = selected[0]
        result = api.booking_lemond(self.conn, booking_code=booking_code)
        messagebox.showinfo("Lemondás", f"Eredmény: {result.value}")
        self._bookings_refresh()
        self._calendar_refresh()

    # ------------------------------------------------------------------
    # Sablonok és hét-másolás
    # ------------------------------------------------------------------

    def _template_message_write(self, szoveg: str) -> None:
        self.template_message.config(state="normal")
        self.template_message.delete("1.0", "end")
        self.template_message.insert("1.0", szoveg)
        self.template_message.config(state="disabled")

    def _template_list_refresh(self) -> None:
        self.template_list.delete(0, "end")
        self._template_id_list = []
        if not self.shop_id:
            return
        for template in api.shift_templates(self.conn, org_id=self.org_id, shop_id=self.shop_id):
            self.template_list.insert(
                "end",
                f"{template['nev']} ({template['kezdet_ora']:02d}–{template['veg_ora']:02d} óra)",
            )
            self._template_id_list.append(template["id"])

    def _selected_template_id(self) -> str | None:
        selection = self.template_list.curselection()
        if not selection:
            return None
        return self._template_id_list[selection[0]]

    def _template_save_from_selected(self) -> None:
        if not self.selected_shift_id:
            self._template_message_write("Előbb válassz ki egy műszakot a Naptár fülön.")
            return
        name = self.template_name_field.get().strip() or "Névtelen sablon"
        result = api.shift_template_save(self.conn, shift_id=self.selected_shift_id, name=name)
        if result["hiba"]:
            self._template_message_write(f"Hiba: {result['hiba']}")
        else:
            self._template_message_write(f"Sablon elmentve: {name} (id: {result['sablon_id']})")
        self._template_list_refresh()

    def _template_apply_for_day(self) -> None:
        template_id = self._selected_template_id()
        if template_id is None:
            self._template_message_write("Előbb válassz ki egy sablont a listából.")
            return
        date = self.template_apply_date_field.get().strip()
        result = api.shift_template_apply_for_day(self.conn, template_id=template_id, date=date)
        if result["hiba"]:
            self._template_message_write(f"Hiba: {result['hiba']}")
        elif result["kihagyva"]:
            self._template_message_write(
                f"{date}: kihagyva (kivétel nap: {result['kihagyas_oka']})"
            )
        else:
            self._template_message_write(f"{date}: létrehozva, {result['slot_szam']} slot.")
        self._calendar_refresh()

    def _template_apply_for_week(self) -> None:
        template_id = self._selected_template_id()
        if template_id is None:
            self._template_message_write("Előbb válassz ki egy sablont a listából.")
            return
        week_start = self.template_apply_date_field.get().strip()
        results = api.shift_template_apply_for_week(
            self.conn, template_id=template_id, week_start_date=week_start
        )
        rows = [f"Hét: {week_start}-tól, 7 nap"]
        for i, result in enumerate(results):
            day = f"+{i} nap"
            if result["hiba"]:
                rows.append(f"  {day}: HIBA — {result['hiba']}")
            elif result["kihagyva"]:
                rows.append(f"  {day}: kihagyva ({result['kihagyas_oka']})")
            else:
                rows.append(f"  {day}: {result['slot_szam']} slot")
        self._template_message_write("\n".join(rows))
        self._calendar_refresh()

    def _week_copy(self) -> None:
        source = self.copy_source_field.get().strip()
        target = self.copy_target_field.get().strip()
        if not target:
            self._template_message_write("Add meg a cél hét kezdetét (ÉÉÉÉ-HH-NN).")
            return
        results = api.week_copy(
            self.conn,
            org_id=self.org_id,
            source_week_start=source,
            target_week_start=target,
            shop_id=self.shop_id,
        )
        if not results:
            self._template_message_write(
                f"A {source} hetén nincs másolható műszak ehhez a bolthoz."
            )
        else:
            rows = [f"{source} → {target}: {len(results)} műszak másolva"]
            for result in results:
                if result["hiba"]:
                    rows.append(f"  HIBA — {result['hiba']}")
                elif result["kihagyva"]:
                    rows.append(f"  kihagyva ({result['kihagyas_oka']})")
                else:
                    rows.append(f"  {result['slot_szam']} slot")
            self._template_message_write("\n".join(rows))
        self._calendar_refresh()

    # ------------------------------------------------------------------
    # Törzsadat-szerkesztés
    # ------------------------------------------------------------------

    def _master_data_message_write(self, szoveg: str) -> None:
        self.master_data_message.config(text=szoveg)

    def _master_data_refresh(self) -> None:
        self._shop_id_list = []
        self.shop_list.delete(0, "end")
        if self.org_id:
            for shop in api.shops(self.conn, org_id=self.org_id):
                self.shop_list.insert("end", shop["nev"])
                self._shop_id_list.append(shop["id"])

        self._counter_id_list = []
        self.counter_list.delete(0, "end")
        self._employee_id_list = []
        self.employee_list.delete(0, "end")
        self._service_id_list = []
        self.service_list.delete(0, "end")
        self._exception_id_list = []
        self.exception_list.delete(0, "end")
        if not self.shop_id:
            return

        for counter in api.counters(self.conn, shop_id=self.shop_id):
            self.counter_list.insert("end", counter["nev"])
            self._counter_id_list.append(counter["id"])
        for employee in api.employees(self.conn, shop_id=self.shop_id):
            self.employee_list.insert("end", employee["nev"])
            self._employee_id_list.append(employee["id"])
        self._service_details = {}
        for service in api.services(self.conn, shop_id=self.shop_id):
            self.service_list.insert(
                "end", f"{service['nev']} ({service['alap_idotartam_perc']} perc)"
            )
            self._service_id_list.append(service["id"])
            self._service_details[service["id"]] = service
        exception_shop = self.shop_id if self.exception_only_shop_valtozo.get() else None
        for exception in api.exception_days(self.conn, org_id=self.org_id, shop_id=exception_shop):
            level_indicator = "bolt" if exception["bolt_id"] else "szervezet"
            self.exception_list.insert(
                "end", f"{exception['datum']} — {exception['indok']} ({level_indicator})"
            )
            self._exception_id_list.append(exception["id"])

    def _selected_id(self, listbox: tk.Listbox, id_list: list[str]) -> str | None:
        selection = listbox.curselection()
        if not selection:
            return None
        return id_list[selection[0]]

    def _shop_add_ui(self, field: ttk.Entry) -> None:
        result = api.shop_add(self.conn, org_id=self.org_id, name=field.get())
        if result["hiba"]:
            self._master_data_message_write(f"Hiba: {result['hiba']}")
            return
        self._master_data_message_write("Bolt felvéve.")
        self._shop_list_refresh()
        self._master_data_refresh()

    def _shop_update_ui(self, listbox: tk.Listbox, field: ttk.Entry) -> None:
        shop_id = self._selected_id(listbox, self._shop_id_list)
        if shop_id is None:
            self._master_data_message_write("Előbb válassz ki egy boltot a listából.")
            return
        result = api.shop_update(self.conn, shop_id=shop_id, name=field.get())
        if result["hiba"]:
            self._master_data_message_write(f"Hiba: {result['hiba']}")
            return
        self._master_data_message_write("Bolt átnevezve.")
        self._shop_list_refresh()
        self._master_data_refresh()

    def _shop_list_selected(self, _event=None) -> None:
        """A Törzsadat fülön kiválasztott bolt megjelenés-mezőjét tölti
        be — hogy szerkesztéskor ne a semmiből kelljen újraírni egy már
        meglévő leírást (docs/blueprint.md 10. szakasz, "Bolti tudás")."""
        shop_id = self._selected_id(self.shop_list, self._shop_id_list)
        self.shop_appearance_field.delete("1.0", "end")
        if shop_id is None:
            return
        shop = api.shop_load(self.conn, shop_id=shop_id)
        if shop:
            self.shop_appearance_field.insert("1.0", shop["megjelenes"])

    def _shop_description_update_ui(self) -> None:
        shop_id = self._selected_id(self.shop_list, self._shop_id_list)
        if shop_id is None:
            self._master_data_message_write("Előbb válassz ki egy boltot a listából.")
            return
        megjelenes = self.shop_appearance_field.get("1.0", "end")
        result = api.shop_description_update(self.conn, shop_id=shop_id, megjelenes=megjelenes)
        self._master_data_message_write(result["hiba"] or "Megjelenés mentve.")

    def _counter_add_ui(self, field: ttk.Entry) -> None:
        if not self.shop_id:
            self._master_data_message_write("Előbb válassz ki egy boltot a felső sávban.")
            return
        result = api.counter_add(
            self.conn, org_id=self.org_id, shop_id=self.shop_id, name=field.get()
        )
        self._master_data_message_write(result["hiba"] or "Pult felvéve.")
        self._shop_selected()

    def _counter_update_ui(self, listbox: tk.Listbox, field: ttk.Entry) -> None:
        counter_id = self._selected_id(listbox, self._counter_id_list)
        if counter_id is None:
            self._master_data_message_write("Előbb válassz ki egy pultot a listából.")
            return
        result = api.counter_update(self.conn, counter_id=counter_id, name=field.get())
        self._master_data_message_write(result["hiba"] or "Pult átnevezve.")
        self._shop_selected()

    def _employee_add_ui(self, field: ttk.Entry) -> None:
        if not self.shop_id:
            self._master_data_message_write("Előbb válassz ki egy boltot a felső sávban.")
            return
        result = api.employee_add(
            self.conn, org_id=self.org_id, shop_id=self.shop_id, name=field.get()
        )
        self._master_data_message_write(result["hiba"] or "Alkalmazott felvéve.")
        self._shop_selected()

    def _employee_update_ui(self, listbox: tk.Listbox, field: ttk.Entry) -> None:
        employee_id = self._selected_id(listbox, self._employee_id_list)
        if employee_id is None:
            self._master_data_message_write("Előbb válassz ki egy alkalmazottat a listából.")
            return
        result = api.employee_update(self.conn, employee_id=employee_id, name=field.get())
        self._master_data_message_write(result["hiba"] or "Alkalmazott átnevezve.")
        self._shop_selected()

    def _service_add_ui(self) -> None:
        if not self.shop_id:
            self._master_data_message_write("Előbb válassz ki egy boltot a felső sávban.")
            return
        try:
            duration = int(self.service_duration_field.get())
        except ValueError:
            self._master_data_message_write("Az időtartam egész szám kell legyen.")
            return
        result = api.service_add(
            self.conn,
            org_id=self.org_id,
            shop_id=self.shop_id,
            name=self.service_name_field.get(),
            alap_duration_minute=duration,
        )
        self._master_data_message_write(result["hiba"] or "Szolgáltatás felvéve.")
        self._shop_selected()

    def _service_list_selected(self, _event=None) -> None:
        """A kiválasztott szolgáltatás termékleírását/árát tölti be —
        ugyanaz az indoklás, mint `_shop_list_selected`-nél."""
        service_id = self._selected_id(self.service_list, self._service_id_list)
        self.service_description_field.delete("1.0", "end")
        self.service_price_field.delete(0, "end")
        if service_id is None:
            return
        service = self._service_details.get(service_id)
        if service:
            self.service_description_field.insert("1.0", service["termekleiras"])
            self.service_price_field.insert(0, service["ar"])

    def _service_update_ui(self) -> None:
        service_id = self._selected_id(self.service_list, self._service_id_list)
        if service_id is None:
            self._master_data_message_write("Előbb válassz ki egy szolgáltatást a listából.")
            return
        try:
            duration = int(self.service_duration_field.get())
        except ValueError:
            self._master_data_message_write("Az időtartam egész szám kell legyen.")
            return
        result = api.service_update(
            self.conn,
            service_id=service_id,
            name=self.service_name_field.get(),
            alap_duration_minute=duration,
        )
        if result["hiba"]:
            self._master_data_message_write(f"Hiba: {result['hiba']}")
            return
        # A "Bolti tudás" mezőket (docs/blueprint.md 10. szakasz) ugyanaz
        # a gomb menti, mint a nevet/időtartamot — az admin egy kattintással
        # ment mindent, nem kell külön gomb a leírásnak.
        api.service_description_update(
            self.conn,
            service_id=service_id,
            termekleiras=self.service_description_field.get("1.0", "end"),
            ar=self.service_price_field.get(),
        )
        self._master_data_message_write("Szolgáltatás módosítva.")
        self._shop_selected()

    def _exception_day_add_ui(self) -> None:
        shop_id = self.shop_id if self.exception_only_shop_valtozo.get() else None
        result = api.exception_day_add(
            self.conn,
            org_id=self.org_id,
            shop_id=shop_id,
            date=self.exception_date_field.get().strip(),
            reason=self.exception_reason_field.get(),
        )
        self._master_data_message_write(result["hiba"] or "Kivételnap felvéve.")
        self._master_data_refresh()
        self._calendar_refresh()

    # ------------------------------------------------------------------
    # Ütközéslista
    # ------------------------------------------------------------------

    def _conflict_tab_build(self) -> None:
        fejlec = ttk.Frame(self.conflict_tab)
        fejlec.pack(side="top", fill="x")
        ttk.Button(
            fejlec, text="Frissítés (a teljes szervezetre)", command=self._conflict_list_refresh
        ).pack(side="left")
        ttk.Button(
            fejlec,
            text="Frissítés (csak a kiválasztott boltra)",
            command=lambda: self._conflict_list_refresh(shop_only=True),
        ).pack(side="left", padx=4)
        self.conflict_counter = ttk.Label(fejlec, text="")
        self.conflict_counter.pack(side="left", padx=12)

        oszlopok = ("tipus", "pult", "alkalmazott", "kezdet", "veg", "uzenet")
        self.conflict_fa = ttk.Treeview(
            self.conflict_tab, columns=oszlopok, show="headings", height=25
        )
        labels = ("Típus", "Pult", "Alkalmazott", "Kezdet", "Vég", "Üzenet")
        widths = (140, 120, 120, 150, 150, 400)
        for oszlop, cim, width in zip(oszlopok, labels, widths, strict=True):
            self.conflict_fa.heading(oszlop, text=cim)
            self.conflict_fa.column(oszlop, width=width)
        self.conflict_fa.pack(fill="both", expand=True, pady=6)

    def _conflict_list_refresh(self, *, shop_only: bool = False) -> None:
        for row in self.conflict_fa.get_children():
            self.conflict_fa.delete(row)
        if not self.org_id:
            return
        shop_id = self.shop_id if shop_only else None
        problems = api.conflict_list(self.conn, org_id=self.org_id, shop_id=shop_id)
        for p in problems:
            self.conflict_fa.insert(
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
        self.conflict_counter.config(text=f"{len(problems)} probléma")

    # ------------------------------------------------------------------

    def _close(self) -> None:
        self.conn.close()
        self.destroy()


def main() -> int:
    app = AdminApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
