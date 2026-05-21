import json
import os
import threading
from datetime import datetime, timedelta
from tkinter import filedialog, messagebox

import customtkinter as ctk
import matplotlib.dates as mdates
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from PIL import Image

from Config import (
    BG_PRIMARY, BG_SECONDARY, BG_CARD,
    ACCENT, ACCENT_HOVER, TEXT_PRIMARY, TEXT_MUTED,
    GREEN, YELLOW, DATA_FILE, PORT,
    resource_path,
)
from core.Data import load_data, save_data, clear_data, merge_steps
from core.Importer import import_samsung_csv, import_apple_xml
from core.Server import StepsServer

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")


class StepsApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Ikona
        try:
            img = Image.open(resource_path("Logo_2.png"))
            img.save("icon.ico", format="ICO",
                     sizes=[(256, 256), (128, 128), (64, 64), (32, 32), (16, 16)])
            self.iconbitmap("icon.ico")
        except Exception:
            pass

        self.title("Steps Analyzer")
        self.geometry("1200x750")
        self.minsize(1000, 650)
        self.configure(fg_color=BG_PRIMARY)

        self.data: dict[str, int] = {}
        self.press = None
        self.chart_dates: list[str] = []
        self._tooltip = None

        self._server = StepsServer(
            on_data_received=self._on_server_data,
            on_log=self._log,
        )

        self._build_ui()
        self._load_data()

    # ══════════════════════════════════════════════════════════
    # UI
    # ══════════════════════════════════════════════════════════

    def _build_ui(self):
        self._build_nav()
        self._build_main()

    def _build_nav(self):
        self.nav = ctk.CTkFrame(self, width=220, fg_color=BG_SECONDARY, corner_radius=0)
        self.nav.pack(side="left", fill="y")
        self.nav.pack_propagate(False)

        ctk.CTkLabel(
            self.nav, text="Steps\nAnalyzer",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=ACCENT
        ).pack(pady=(30, 10))

        ctk.CTkLabel(
            self.nav, text="Panel sterowania",
            font=ctk.CTkFont(size=11),
            text_color=TEXT_MUTED
        ).pack(pady=(0, 20))

        # Serwer
        self._nav_section("SERWER")
        self.btn_server = ctk.CTkButton(
            self.nav, text="▶  Uruchom serwer",
            fg_color=GREEN, hover_color="#388e3c",
            command=self._toggle_server, height=38
        )
        self.btn_server.pack(padx=16, pady=4, fill="x")

        self.lbl_server_ip = ctk.CTkLabel(
            self.nav, text="IP: —",
            font=ctk.CTkFont(size=11), text_color=TEXT_MUTED
        )
        self.lbl_server_ip.pack(pady=(0, 4))

        self.lbl_server_status = ctk.CTkLabel(
            self.nav, text="●  Zatrzymany",
            font=ctk.CTkFont(size=11), text_color=ACCENT
        )
        self.lbl_server_status.pack()

        # Import i usuwanie
        self._nav_section("IMPORT I USUWANIE DANYCH")

        ctk.CTkButton(
            self.nav, text="📂  Importuj CSV (Samsung)",
            fg_color=BG_CARD, hover_color=ACCENT,
            command=self._import_csv, height=38
        ).pack(padx=16, pady=4, fill="x")

        ctk.CTkButton(
            self.nav, text="🍎  Importuj XML (Apple)",
            fg_color=BG_CARD, hover_color=ACCENT,
            command=self._import_apple_xml, height=38
        ).pack(padx=16, pady=4, fill="x")

        ctk.CTkButton(
            self.nav, text="🔄  Odśwież dane",
            fg_color=BG_CARD, hover_color=ACCENT,
            command=self._load_data, height=38
        ).pack(padx=16, pady=4, fill="x")

        ctk.CTkButton(
            self.nav, text="🗑  Usuń dane",
            fg_color=BG_CARD, hover_color=ACCENT,
            command=self._clear_data, height=38
        ).pack(padx=16, pady=4, fill="x")

        # Zakres wykresu
        self._nav_section("ZAKRES WYKRESU")
        self.range_var = ctk.StringVar(value="30")
        for label, val in [("7 dni", "7"), ("30 dni", "30"), ("365 dni", "365"), ("Wszystko", "all")]:
            ctk.CTkRadioButton(
                self.nav, text=label, variable=self.range_var, value=val,
                command=self._refresh_all,
                fg_color=ACCENT, hover_color=ACCENT_HOVER,
                text_color=TEXT_PRIMARY
            ).pack(anchor="w", padx=24, pady=2)

        # Eksport
        self._nav_section("EKSPORT")
        ctk.CTkButton(
            self.nav, text="💾  Eksportuj JSON",
            fg_color=BG_CARD, hover_color=ACCENT,
            command=self._export_json, height=38
        ).pack(padx=16, pady=4, fill="x")

        # Log serwera
        ctk.CTkLabel(
            self.nav, text="LOG SERWERA",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=TEXT_MUTED
        ).pack(side="bottom", pady=(0, 2))

        self.log_box = ctk.CTkTextbox(
            self.nav, height=130, fg_color="#000000",
            text_color=TEXT_MUTED,
            font=ctk.CTkFont(family="Courier", size=10),
            state="disabled"
        )
        self.log_box.pack(side="bottom", padx=8, pady=(0, 6), fill="x")

    def _build_main(self):
        self.main = ctk.CTkFrame(self, fg_color=BG_PRIMARY)
        self.main.pack(side="left", fill="both", expand=True, padx=12, pady=12)

        # Karty statystyk
        self.stats_frame = ctk.CTkFrame(self.main, fg_color="transparent")
        self.stats_frame.pack(fill="x", pady=(0, 10))

        self.stat_cards = {}
        stats = [
            ("today", "Dzisiaj", "0", "kroków"),
            ("avg", "Średnia/dzień", "0", "kroków"),
            ("max", "Rekord", "0", "kroków"),
            ("total", "Łącznie", "0", "kroków"),
            ("days", "Dni z danymi", "0", "dni"),
        ]
        for i, (key, title, val, unit) in enumerate(stats):
            card = self._make_stat_card(self.stats_frame, title, val, unit)
            padx = (0, 10) if i < len(stats) - 1 else 0
            card.pack(side="left", expand=True, fill="x", padx=padx)
            self.stat_cards[key] = card

        # Wykres
        chart_frame = ctk.CTkFrame(self.main, fg_color=BG_SECONDARY, corner_radius=12)
        chart_frame.pack(fill="both", expand=True, pady=(0, 10))

        self.fig = Figure(figsize=(8, 3.2), dpi=100, facecolor=BG_SECONDARY)
        self.ax = self.fig.add_subplot(111)
        self._style_ax()

        self.canvas = FigureCanvasTkAgg(self.fig, master=chart_frame)
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=8, pady=8)
        self.canvas.mpl_connect("scroll_event", self._on_scroll)
        self.canvas.mpl_connect("pick_event", self._on_pick)
        self.canvas.mpl_connect("button_press_event", self._on_press)
        self.canvas.mpl_connect("button_release_event", self._on_release)
        self.canvas.mpl_connect("motion_notify_event", self._on_motion)

        # Tabela
        table_frame = ctk.CTkFrame(self.main, fg_color=BG_SECONDARY, corner_radius=12)
        table_frame.pack(fill="both", expand=True)

        ctk.CTkLabel(
            table_frame, text="Historia kroków",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=TEXT_PRIMARY
        ).pack(anchor="w", padx=14, pady=(10, 4))

        hdr = ctk.CTkFrame(table_frame, fg_color=BG_CARD, corner_radius=6)
        hdr.pack(fill="x", padx=10, pady=(0, 2))
        for col, w in [("Data", 120), ("Kroki", 100), ("Pasek postępu", 300), ("Względem średniej", 100)]:
            ctk.CTkLabel(
                hdr, text=col, width=w,
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=TEXT_MUTED, anchor="w"
            ).pack(side="left", padx=8, pady=6)

        self.table_scroll = ctk.CTkScrollableFrame(
            table_frame, fg_color="transparent", height=160
        )
        self.table_scroll.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    # ── Pomocnicze widgety ─────────────────────────────────────

    def _nav_section(self, title: str):
        ctk.CTkLabel(
            self.nav, text=title,
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=TEXT_MUTED
        ).pack(anchor="w", padx=16, pady=(14, 2))

    def _make_stat_card(self, parent, title, value, unit):
        frame = ctk.CTkFrame(parent, fg_color=BG_SECONDARY, corner_radius=10)
        ctk.CTkLabel(frame, text=title, font=ctk.CTkFont(size=10), text_color=TEXT_MUTED).pack(pady=(10, 0))
        lbl_val = ctk.CTkLabel(frame, text=value, font=ctk.CTkFont(size=22, weight="bold"), text_color=ACCENT)
        lbl_val.pack()
        ctk.CTkLabel(frame, text=unit, font=ctk.CTkFont(size=10), text_color=TEXT_MUTED).pack(pady=(0, 10))
        frame._value_label = lbl_val
        return frame

    def _style_ax(self):
        self.ax.set_facecolor(BG_SECONDARY)
        self.ax.tick_params(colors=TEXT_MUTED, labelsize=9)
        self.ax.spines["bottom"].set_color("#000000")
        self.ax.spines["left"].set_color("#000000")
        self.ax.spines["top"].set_visible(False)
        self.ax.spines["right"].set_visible(False)
        self.ax.yaxis.label.set_color(TEXT_MUTED)
        self.ax.set_ylabel("Kroki", color=TEXT_MUTED, fontsize=9)
        self.fig.tight_layout(pad=1.5)

    # ══════════════════════════════════════════════════════════
    # Interakcja z wykresem
    # ══════════════════════════════════════════════════════════

    def _on_scroll(self, event):
        if event.inaxes != self.ax:
            return
        cur_xlim = self.ax.get_xlim()
        scale_factor = 1 / 1.1 if event.button == "up" else 1.1
        new_width = (cur_xlim[1] - cur_xlim[0]) * scale_factor
        rel_pos = (event.xdata - cur_xlim[0]) / (cur_xlim[1] - cur_xlim[0])
        self.ax.set_xlim([
            event.xdata - new_width * rel_pos,
            event.xdata + new_width * (1 - rel_pos),
        ])
        self.canvas.draw()

    def _on_press(self, event):
        if event.inaxes != self.ax:
            return
        self.press = event.xdata, event.ydata

    def _on_release(self, event):
        self.press = None
        self.canvas.draw()

    def _on_motion(self, event):
        if self.press is None or event.inaxes != self.ax:
            return
        dx = self.press[0] - event.xdata
        cur = self.ax.get_xlim()
        self.ax.set_xlim(cur[0] + dx, cur[1] + dx)
        self.canvas.draw()

    def _on_pick(self, event):
        if event.mouseevent.button not in (1, 3):
            return
        if not self.chart_dates:
            return
        try:
            bars = self.ax.patches
            if event.artist not in bars:
                return
            index = bars.index(event.artist)
            if index >= len(self.chart_dates):
                return
            date_str = self.chart_dates[index]
            steps = self.data.get(date_str, 0)
            self._log(f"WYBRANO: {date_str} -> {steps:,} kroków")
            self._show_tooltip(event, f" {date_str}\n {steps:,} kroków")
        except Exception as e:
            self._log(f"BŁĄD _on_pick: {type(e).__name__}: {e}")

    def _show_tooltip(self, event, text: str):
        self._hide_tooltip()
        try:
            mouse = event.mouseevent
            self._tooltip = self.ax.annotate(
                text,
                xy=(mouse.xdata, mouse.ydata),
                xytext=(5, 5),
                textcoords="offset points",
                fontsize=10,
                color=TEXT_PRIMARY,
                bbox=dict(boxstyle="round,pad=0.6", facecolor=BG_CARD,
                          edgecolor=BG_CARD, linewidth=1.5, alpha=0.95),
                zorder=10,
            )
            self.canvas.draw()
            self.after(3000, self._hide_tooltip)
        except Exception as e:
            self._log(f"TOOLTIP ERROR: {type(e).__name__}: {e}")

    def _hide_tooltip(self):
        if self._tooltip:
            try:
                self._tooltip.remove()
                self.canvas.draw()
            except Exception:
                pass
            self._tooltip = None

    # ══════════════════════════════════════════════════════════
    # Dane
    # ══════════════════════════════════════════════════════════

    def _load_data(self):
        self.data = load_data()
        #self._log(f"Wczytano {len(self.data)} dni danych")
        self._refresh_all()

    def _save_data(self):
        save_data(self.data)

    def _clear_data(self):
        if not messagebox.askyesno("Potwierdzenie", "Czy na pewno chcesz usunąć WSZYSTKIE dane z bazy?"):
            return
        try:
            self.data.clear()
            clear_data()
            self._refresh_all()
            self._log("Baza danych została wyczyszczona.")
            messagebox.showinfo("Sukces", "Wszystkie dane zostały usunięte.")
        except Exception as e:
            self._log(f"Błąd podczas usuwania: {e}")
            messagebox.showerror("Błąd", f"Nie udało się wyczyścić pliku: {e}")

    def _refresh_all(self):
        self._update_stats()
        self._refresh_chart()
        self._refresh_table()

    def _update_stats(self):
        #self._log(f"_update_stats: data ma {len(self.data)} wpisów")
        if not self.data:
            return
        today_str = datetime.now().strftime("%Y-%m-%d")
        values = list(self.data.values())
        avg = int(sum(values) / len(values)) if values else 0
        updates = {
            "today": f"{self.data.get(today_str, 0):,}",
            "avg": f"{avg:,}",
            "max": f"{max(values):,}" if values else "0",
            "total": f"{sum(values):,}",
            "days": str(len(self.data)),
        }
        for key, val in updates.items():
            self.stat_cards[key]._value_label.configure(text=val)

    def _refresh_chart(self):
        self.ax.clear()
        self._style_ax()

        if not self.data:
            self.canvas.draw()
            return

        rng = self.range_var.get()
        sorted_dates = sorted(self.data.keys())

        if rng != "all":
            cutoff = (datetime.now() - timedelta(days=int(rng))).strftime("%Y-%m-%d")
            sorted_dates = [d for d in sorted_dates if d >= cutoff]

        if not sorted_dates:
            self.canvas.draw()
            return

        xs = [datetime.strptime(d, "%Y-%m-%d") for d in sorted_dates]
        ys = [self.data[d] for d in sorted_dates]
        avg = sum(ys) / len(ys) if ys else 0

        colors = [GREEN if y >= avg else ACCENT for y in ys]
        self.ax.bar(xs, ys, color=colors, width=0.8, alpha=0.85, picker=True)
        self.chart_dates = sorted_dates

        self.ax.axhline(avg, color=YELLOW, linewidth=1.2, linestyle="--",
                        alpha=0.7, label=f"Średnia: {int(avg):,}")
        self.ax.legend(facecolor=BG_CARD, edgecolor="none",
                       labelcolor=TEXT_PRIMARY, fontsize=9)

        if len(xs) <= 14:
            self.ax.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m"))
            self.ax.xaxis.set_major_locator(mdates.DayLocator())
        elif len(xs) <= 60:
            self.ax.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m"))
            self.ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=1))
        else:
            self.ax.xaxis.set_major_formatter(mdates.DateFormatter("%m.%Y"))
            self.ax.xaxis.set_major_locator(mdates.MonthLocator())

        self.fig.autofmt_xdate(rotation=35, ha="right")
        self.canvas.draw()

    def _refresh_table(self):
        for w in self.table_scroll.winfo_children():
            w.destroy()

        if not self.data:
            return

        values = list(self.data.values())
        avg = sum(values) / len(values) if values else 1
        max_val = max(values) if values else 1

        rng = self.range_var.get()
        sorted_dates = sorted(self.data.keys(), reverse=True)

        if rng != "all":
            cutoff = (datetime.now() - timedelta(days=int(rng))).strftime("%Y-%m-%d")
            sorted_dates = [d for d in sorted_dates if d >= cutoff]

        if len(sorted_dates) > 366:
            ctk.CTkLabel(
                self.table_scroll,
                text=f"⚠️ Zbyt dużo danych ({len(sorted_dates)} dni).\n"
                     f"Wybierz zakres 7, 30 lub 365 dni.",
                font=ctk.CTkFont(size=12),
                text_color=YELLOW,
                justify="center",
            ).pack(expand=True, pady=40)
            return

        for index, date in enumerate(sorted_dates):
            steps = self.data[date]
            pct = steps / max_val if max_val else 0
            vs_avg = ((steps - avg) / avg * 100) if avg else 0

            row = ctk.CTkFrame(
                self.table_scroll,
                fg_color=BG_CARD if index % 2 == 0 else BG_SECONDARY,
                corner_radius=4, height=32,
            )
            row.pack(fill="x", pady=1)
            row.pack_propagate(False)

            ctk.CTkLabel(row, text=date, width=120, font=ctk.CTkFont(size=11),
                         text_color=TEXT_PRIMARY, anchor="w").pack(side="left", padx=8)
            ctk.CTkLabel(row, text=f"{steps:,}", width=100,
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color=ACCENT, anchor="w").pack(side="left", padx=8)

            pb = ctk.CTkProgressBar(row, width=280, height=8,
                                    progress_color=GREEN if steps >= avg else ACCENT,
                                    fg_color="#000000")
            pb.set(pct)
            pb.pack(side="left", padx=8)

            sign = "+" if vs_avg >= 0 else ""
            ctk.CTkLabel(row, text=f"{sign}{vs_avg:.1f}%", width=100,
                         font=ctk.CTkFont(size=11),
                         text_color=GREEN if vs_avg >= 0 else ACCENT,
                         anchor="w").pack(side="left", padx=8)

    # ══════════════════════════════════════════════════════════
    # Serwer
    # ══════════════════════════════════════════════════════════

    def _toggle_server(self):
        if self._server.running:
            self._server.stop()
            self.lbl_server_status.configure(text="●  Zatrzymany", text_color=ACCENT)
            self.btn_server.configure(text="▶  Uruchom serwer",
                                      fg_color=GREEN, hover_color="#388e3c")
            self.lbl_server_ip.configure(text="IP: —")
            self._log("Serwer zatrzymany")
        else:
            try:
                local_ip = self._server.start()
                self.lbl_server_ip.configure(text=f"IP: {local_ip}")
                self.lbl_server_status.configure(text="● Działa", text_color=GREEN)
                self.btn_server.configure(text="■  Zatrzymaj serwer",
                                          fg_color=ACCENT, hover_color=ACCENT_HOVER)
                self._log(f"Serwer uruchomiony na {local_ip}:{PORT}")
            except Exception as e:
                self._log(f"Błąd: {e}")
                messagebox.showerror("Błąd serwera", str(e))

    def _on_server_data(self, steps: dict):
        """Callback wywoływany przez serwer po odebraniu danych."""
        self.data, _ = merge_steps(self.data, steps)
        save_data(self.data)
        self.after(100, self._refresh_all)

    # ══════════════════════════════════════════════════════════
    # Import / Eksport
    # ══════════════════════════════════════════════════════════

    def _import_csv(self):
        path = filedialog.askopenfilename(
            title="Wybierz plik CSV z Samsung Health",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if not path:
            return
        self._log("Importuję CSV Samsung Health...")
        threading.Thread(target=self._run_import_csv, args=(path,), daemon=True).start()

    def _run_import_csv(self, path: str):
        try:
            daily_steps, processed, total_days = import_samsung_csv(path)
            self.data, imported = merge_steps(self.data, daily_steps)
            save_data(self.data)
            self.after(0, lambda: self._finalize_import(processed, total_days, imported, "Samsung CSV"))
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Błąd", f"Błąd importu CSV: {e}"))

    def _import_apple_xml(self):
        path = filedialog.askopenfilename(
            title="Wybierz plik eksportu Apple Health",
            filetypes=[("XML files", "*.xml"), ("All files", "*.*")]
        )
        if not path:
            return
        self._log("Importuję XML Apple Health (może chwilę potrwać)...")
        threading.Thread(target=self._run_import_apple, args=(path,), daemon=True).start()

    def _run_import_apple(self, path: str):
        try:
            daily_steps, processed, total_days = import_apple_xml(path)
            self.data, imported = merge_steps(self.data, daily_steps)
            save_data(self.data)
            self.after(0, lambda: self._finalize_import(processed, total_days, imported, "Apple Health"))
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Błąd", f"Błąd importu Apple Health: {e}"))

    def _finalize_import(self, proc: int, total_days: int, imported: int, source: str):
        self._refresh_all()
        self._log(f"Import {source}: {proc} rekordów → {total_days} dni")
        messagebox.showinfo(
            "Import zakończony",
            f"Źródło: {source}\n"
            f"Przetworzono: {proc} rekordów\n"
            f"Dni w pliku: {total_days}\n"
            f"Nowych/zaktualizowanych: {imported}"
        )

    def _export_json(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
            initialfile="steps_export.json"
        )
        if not path:
            return
        with open(path, "w") as f:
            json.dump(self.data, f, indent=2)
        self._log(f"Eksport → {os.path.basename(path)}")
        messagebox.showinfo("Eksport", f"Zapisano {len(self.data)} dni danych.")

    # ══════════════════════════════════════════════════════════
    # Log
    # ══════════════════════════════════════════════════════════

    def _log(self, msg: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{timestamp}] {msg}\n"
        self.log_box.configure(state="normal")
        self.log_box.insert("end", line)
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

