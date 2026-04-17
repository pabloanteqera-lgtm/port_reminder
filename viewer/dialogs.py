"""Dialog windows for data entry."""

import datetime
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from .data.excel_io import BROKERS, add_broker, remove_broker, list_brokers


class AddValuesDialog(ctk.CTkToplevel):
    """Multi-row dialog for entering portfolio values across multiple days."""

    def __init__(self, parent, theme, auto_prompt=False):
        super().__init__(parent)
        self.title("Edit Portfolio Values")
        self.geometry("520x460")
        self.resizable(False, True)
        self.results = []  # list of (date, {broker: value})
        self.theme = theme

        broker_names = [b["name"] for b in BROKERS]
        today = datetime.date.today()
        num_rows = 1 if auto_prompt else 5

        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill=tk.X, padx=20, pady=(16, 8))

        ctk.CTkLabel(header, text="Enter portfolio values",
                      font=("Segoe UI", 14, "bold")).pack(anchor="w")
        ctk.CTkLabel(header, text="One row per day. Leave rows blank to skip.",
                      font=("Segoe UI", 11),
                      text_color=theme["MUTED"]).pack(anchor="w", pady=(2, 0))

        # Scrollable grid
        self.grid_frame = ctk.CTkScrollableFrame(self, fg_color="transparent",
                                                   height=300)
        self.grid_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=(4, 8))

        # Column headers
        hdr = ctk.CTkFrame(self.grid_frame, fg_color="transparent")
        hdr.pack(fill=tk.X, pady=(0, 4))
        ctk.CTkLabel(hdr, text="Date", font=("Segoe UI", 10, "bold"),
                      text_color=theme["MUTED"], width=110).pack(
            side=tk.LEFT, padx=(0, 4))
        for name in broker_names:
            currency = next((b["currency"] for b in BROKERS
                             if b["name"] == name), "EUR")
            symbol = {"EUR": "\u20ac", "USD": "$", "GBP": "\u00a3"
                      }.get(currency, currency)
            ctk.CTkLabel(hdr, text=f"{name} ({symbol})",
                          font=("Segoe UI", 10, "bold"),
                          text_color=theme["MUTED"], width=110).pack(
                side=tk.LEFT, padx=2)

        # Data rows
        self.rows = []
        for i in range(num_rows):
            row_date = today - datetime.timedelta(days=num_rows - 1 - i)
            self._add_row(row_date if not auto_prompt else today,
                          readonly_date=auto_prompt)

        # Buttons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill=tk.X, padx=20, pady=(4, 16))

        if not auto_prompt:
            ctk.CTkButton(btn_frame, text="+ Add row", width=90, height=28,
                          font=("Segoe UI", 11), corner_radius=6,
                          fg_color=theme["GRID"], hover_color=theme["BORDER"],
                          text_color=theme["MUTED"],
                          command=lambda: self._add_row(today)
                          ).pack(side=tk.LEFT, padx=(0, 8))

        ctk.CTkButton(btn_frame, text="Save all", width=90, height=32,
                      font=("Segoe UI", 12, "bold"), corner_radius=6,
                      fg_color=theme["POS"], hover_color="#009970",
                      text_color="white",
                      command=self._save).pack(side=tk.RIGHT, padx=(4, 0))

        skip_text = "Skip" if auto_prompt else "Cancel"
        ctk.CTkButton(btn_frame, text=skip_text, width=80, height=32,
                      font=("Segoe UI", 11), corner_radius=6,
                      fg_color=theme["GRID"], hover_color=theme["BORDER"],
                      text_color=theme["MUTED"],
                      command=self._skip).pack(side=tk.RIGHT)

        self.transient(parent)
        self.grab_set()
        # Focus first value entry
        if self.rows:
            entries = self.rows[0][1]
            if entries:
                first_key = list(entries.keys())[0]
                entries[first_key].focus()

    def _add_row(self, default_date, readonly_date=False):
        broker_names = [b["name"] for b in BROKERS]
        theme = self.theme

        row = ctk.CTkFrame(self.grid_frame, fg_color="transparent")
        row.pack(fill=tk.X, pady=2)

        date_entry = ctk.CTkEntry(row, width=110, height=28,
                                    font=("Segoe UI", 11), corner_radius=4,
                                    fg_color=theme["BG"],
                                    border_color=theme["BORDER"],
                                    text_color=theme["FG"], border_width=1)
        date_entry.pack(side=tk.LEFT, padx=(0, 4))
        date_entry.insert(0, str(default_date))
        if readonly_date:
            date_entry.configure(state="disabled")

        value_entries = {}
        for name in broker_names:
            entry = ctk.CTkEntry(row, width=110, height=28,
                                  font=("Segoe UI", 11), corner_radius=4,
                                  fg_color=theme["BG"],
                                  border_color=theme["BORDER"],
                                  text_color=theme["FG"], border_width=1,
                                  placeholder_text="0")
            entry.pack(side=tk.LEFT, padx=2)
            value_entries[name] = entry

        self.rows.append((date_entry, value_entries))

    def _skip(self):
        self.results = []
        self.destroy()

    def _save(self):
        self.results = []
        for date_entry, value_entries in self.rows:
            date_str = date_entry.get().strip()
            if not date_str:
                continue

            # Check if any value is filled
            any_filled = any(e.get().strip() for e in value_entries.values())
            if not any_filled:
                continue

            try:
                date = datetime.date.fromisoformat(date_str)
            except ValueError:
                messagebox.showerror("Invalid date",
                                     f"Bad date: {date_str}. Use YYYY-MM-DD.",
                                     parent=self)
                return

            values = {}
            for name, entry in value_entries.items():
                raw = entry.get().strip().replace(",", ".")
                if not raw:
                    raw = "0"
                try:
                    values[name] = float(raw)
                except ValueError:
                    messagebox.showerror("Invalid value",
                                         f"Bad number for {name} on {date_str}.",
                                         parent=self)
                    return
            self.results.append((date, values))

        self.destroy()


class ManageBrokersDialog(ctk.CTkToplevel):
    """Dialog for adding and removing brokers."""

    def __init__(self, parent, theme):
        super().__init__(parent)
        self.title("Manage Brokers")
        self.geometry("440x420")
        self.resizable(False, True)
        self.theme = theme
        self.changed = False  # True if brokers were added/removed

        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=16)

        # Header
        ctk.CTkLabel(frame, text="Manage Brokers",
                      font=("Segoe UI", 14, "bold")).pack(anchor="w")
        ctk.CTkLabel(frame, text="Add or remove broker accounts.",
                      font=("Segoe UI", 11),
                      text_color=theme["MUTED"]).pack(anchor="w", pady=(2, 12))

        # ── Current brokers list ──
        self.list_frame = ctk.CTkScrollableFrame(frame, fg_color="transparent",
                                                   height=180)
        self.list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 12))
        self._refresh_list()

        # ── Add new broker ──
        sep = ctk.CTkFrame(frame, fg_color=theme["GRID"], height=1,
                            corner_radius=0)
        sep.pack(fill=tk.X, pady=(0, 12))

        ctk.CTkLabel(frame, text="ADD NEW BROKER",
                      font=("Segoe UI", 10, "bold"),
                      text_color=theme["MUTED"]).pack(anchor="w", pady=(0, 6))

        add_row = ctk.CTkFrame(frame, fg_color="transparent")
        add_row.pack(fill=tk.X)

        self.name_entry = ctk.CTkEntry(add_row, width=150, height=30,
                                         font=("Segoe UI", 11), corner_radius=4,
                                         border_width=1,
                                         border_color=theme["BORDER"],
                                         placeholder_text="Broker name")
        self.name_entry.pack(side=tk.LEFT, padx=(0, 6))

        self.currency_var = tk.StringVar(value="EUR")
        ctk.CTkOptionMenu(add_row, variable=self.currency_var,
                            values=["EUR", "USD", "GBP", "CHF", "JPY"],
                            width=80, height=30, font=("Segoe UI", 11),
                            corner_radius=4, fg_color=theme["GRID"],
                            button_color=theme["BORDER"],
                            text_color=theme["FG"]).pack(side=tk.LEFT, padx=(0, 6))

        ctk.CTkButton(add_row, text="+ Add", width=70, height=30,
                      font=("Segoe UI", 11, "bold"), corner_radius=6,
                      fg_color=theme["POS"], hover_color="#009970",
                      text_color="white",
                      command=self._add_broker).pack(side=tk.LEFT)

        self.error_label = ctk.CTkLabel(frame, text="",
                                          font=("Segoe UI", 10),
                                          text_color="#F56565")
        self.error_label.pack(anchor="w", pady=(6, 0))

        # Close button
        ctk.CTkButton(frame, text="Close", width=80, height=32,
                      font=("Segoe UI", 11), corner_radius=6,
                      fg_color=theme["GRID"], hover_color=theme["BORDER"],
                      text_color=theme["MUTED"],
                      command=self.destroy).pack(anchor="e", pady=(8, 0))

        self.transient(parent)
        self.grab_set()

    def _refresh_list(self):
        """Rebuild the broker list UI."""
        for widget in self.list_frame.winfo_children():
            widget.destroy()

        brokers = list_brokers()
        theme = self.theme

        for b in brokers:
            row = ctk.CTkFrame(self.list_frame, fg_color=theme["GRID"],
                                corner_radius=6, height=36)
            row.pack(fill=tk.X, pady=2)
            row.pack_propagate(False)

            ctk.CTkLabel(row, text=b["name"], font=("Segoe UI", 12, "bold"),
                          text_color=theme["FG"]).pack(
                side=tk.LEFT, padx=(12, 8))
            ctk.CTkLabel(row, text=f"{b['currency']}  ·  {b['type']}",
                          font=("Segoe UI", 10),
                          text_color=theme["MUTED"]).pack(
                side=tk.LEFT, padx=(0, 8))

            if len(brokers) > 1:
                broker_name = b["name"]
                ctk.CTkButton(
                    row, text="✕", width=28, height=24,
                    font=("Segoe UI", 11), corner_radius=4,
                    fg_color="transparent", hover_color="#F5656530",
                    text_color="#F56565",
                    command=lambda n=broker_name: self._remove_broker(n)
                ).pack(side=tk.RIGHT, padx=(0, 6))

    def _add_broker(self):
        name = self.name_entry.get().strip()
        if not name:
            self.error_label.configure(text="Enter a broker name.")
            return

        currency = self.currency_var.get()
        err = add_broker(name, currency)
        if err:
            self.error_label.configure(text=err)
            return

        self.error_label.configure(text="")
        self.name_entry.delete(0, tk.END)
        self.changed = True
        self._refresh_list()

    def _remove_broker(self, name):
        confirm = messagebox.askyesno(
            "Remove broker",
            f"Remove '{name}'?\n\nThis will delete its column from the Excel data.",
            parent=self)
        if not confirm:
            return

        err = remove_broker(name)
        if err:
            self.error_label.configure(text=err)
            return

        self.error_label.configure(text="")
        self.changed = True
        self._refresh_list()


class CashFlowDialog(ctk.CTkToplevel):
    """Dialog for recording deposits and withdrawals."""

    def __init__(self, parent, theme):
        super().__init__(parent)
        self.title("Record Deposit / Withdrawal")
        self.geometry("360x280")
        self.resizable(False, False)
        self.result = None

        broker_names = [b["name"] for b in BROKERS]

        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.pack(fill=tk.BOTH, expand=True, padx=24, pady=20)

        # Date
        ctk.CTkLabel(frame, text="Date", font=("Segoe UI", 11),
                      text_color=theme["MUTED"]).grid(
            row=0, column=0, sticky="w", pady=4)
        self.date_entry = ctk.CTkEntry(frame, width=160, height=30,
                                         font=("Segoe UI", 11), corner_radius=4,
                                         border_width=1,
                                         border_color=theme["BORDER"])
        self.date_entry.grid(row=0, column=1, pady=4, padx=(8, 0))
        self.date_entry.insert(0, str(datetime.date.today()))

        # Broker
        ctk.CTkLabel(frame, text="Broker", font=("Segoe UI", 11),
                      text_color=theme["MUTED"]).grid(
            row=1, column=0, sticky="w", pady=4)
        self.broker_var = tk.StringVar(value=broker_names[0])
        ctk.CTkOptionMenu(frame, variable=self.broker_var, values=broker_names,
                            width=160, height=30, font=("Segoe UI", 11),
                            corner_radius=4, fg_color=theme["GRID"],
                            button_color=theme["BORDER"],
                            text_color=theme["FG"]).grid(
            row=1, column=1, pady=4, padx=(8, 0))

        # Type
        ctk.CTkLabel(frame, text="Type", font=("Segoe UI", 11),
                      text_color=theme["MUTED"]).grid(
            row=2, column=0, sticky="w", pady=4)
        self.type_var = tk.StringVar(value="deposit")
        seg = ctk.CTkSegmentedButton(frame, values=["deposit", "withdrawal"],
                                       variable=self.type_var,
                                       font=("Segoe UI", 11),
                                       corner_radius=4, height=30,
                                       selected_color=theme["POS"],
                                       unselected_color=theme["GRID"],
                                       text_color=theme["FG"])
        seg.grid(row=2, column=1, pady=4, padx=(8, 0), sticky="w")

        # Amount
        ctk.CTkLabel(frame, text="Amount (\u20ac)", font=("Segoe UI", 11),
                      text_color=theme["MUTED"]).grid(
            row=3, column=0, sticky="w", pady=4)
        self.amount_entry = ctk.CTkEntry(frame, width=160, height=30,
                                           font=("Segoe UI", 11),
                                           corner_radius=4, border_width=1,
                                           border_color=theme["BORDER"],
                                           placeholder_text="0")
        self.amount_entry.grid(row=3, column=1, pady=4, padx=(8, 0))
        self.amount_entry.focus()

        # Buttons
        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.grid(row=4, column=0, columnspan=2, pady=(16, 0))

        ctk.CTkButton(btn_frame, text="Save", width=80, height=32,
                      font=("Segoe UI", 12, "bold"), corner_radius=6,
                      fg_color=theme["POS"], hover_color="#009970",
                      text_color="white",
                      command=self._save).pack(side=tk.LEFT, padx=4)
        ctk.CTkButton(btn_frame, text="Cancel", width=80, height=32,
                      font=("Segoe UI", 11), corner_radius=6,
                      fg_color=theme["GRID"], hover_color=theme["BORDER"],
                      text_color=theme["MUTED"],
                      command=self.destroy).pack(side=tk.LEFT, padx=4)

        self.transient(parent)
        self.grab_set()

    def _save(self):
        try:
            date = datetime.date.fromisoformat(self.date_entry.get().strip())
        except ValueError:
            messagebox.showerror("Invalid date", "Use YYYY-MM-DD format.",
                                 parent=self)
            return

        raw = self.amount_entry.get().strip().replace(",", ".")
        if not raw:
            messagebox.showerror("Missing amount", "Enter an amount.",
                                 parent=self)
            return
        try:
            amount = float(raw)
        except ValueError:
            messagebox.showerror("Invalid amount", "Enter a valid number.",
                                 parent=self)
            return

        self.result = (date, self.broker_var.get(), amount, self.type_var.get())
        self.destroy()
