"""Tkinter interface that consolidates the project's presentation workflow."""

from __future__ import annotations

import json
import os
import queue
import threading
import tkinter as tk
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk
from typing import Any

from mcp_host.chatbot import ChatSession
from mcp_host.config import create_clients
from mcp_host.llm import OpenAiProvider
from mcp_host.logging import McpAuditLogger

from .controller import (
    RuntimeSettings,
    health_url,
    normalize_url,
    parse_tool_arguments,
    run_module,
    tool_argument_template,
)

BG = "#0b1114"
SURFACE = "#111a1f"
SURFACE_ALT = "#172329"
TEXT = "#e7eef0"
MUTED = "#91a2a9"
ACCENT = "#52d18b"
ACCENT_DARK = "#1d8f5a"
ERROR = "#ff746c"
BORDER = "#2a3a41"


class ProjectApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.project_root = Path.cwd().resolve()
        self.session: ChatSession | None = None
        self.events: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.busy = False

        self.api_key = tk.StringVar(value=os.environ.get("LLM_API_KEY", ""))
        self.model = tk.StringVar(value=os.environ.get("LLM_MODEL", "gemini-3.1-flash-lite"))
        self.base_url = tk.StringVar(
            value=os.environ.get("LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")
        )
        self.remote_url = tk.StringVar(
            value=os.environ.get("PLANT_MCP_REMOTE_URL", "https://plant-energy-mcp.onrender.com/mcp")
        )
        self.remote_token = tk.StringVar(value=os.environ.get("PLANT_MCP_AUTH_TOKEN", ""))
        self.status_text = tk.StringVar(value="Sin conectar")
        self.server_flags = {
            "plant-local": tk.BooleanVar(value=True),
            "filesystem": tk.BooleanVar(value=True),
            "git": tk.BooleanVar(value=True),
            "plant-remote": tk.BooleanVar(value=True),
        }

        self._configure_window()
        self._build_styles()
        self._build_layout()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(100, self._drain_events)

    def _configure_window(self) -> None:
        self.root.title("Plant Energy MCP — Panel de demostración")
        self.root.geometry("1240x780")
        self.root.minsize(1040, 680)
        self.root.configure(bg=BG)

    def _build_styles(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TFrame", background=BG)
        style.configure("Surface.TFrame", background=SURFACE)
        style.configure("TLabel", background=BG, foreground=TEXT, font=("Segoe UI", 10))
        style.configure("Muted.TLabel", foreground=MUTED)
        style.configure("Title.TLabel", font=("Segoe UI Semibold", 22), foreground=TEXT)
        style.configure("Section.TLabel", font=("Segoe UI Semibold", 11), foreground=TEXT, background=SURFACE)
        style.configure("Status.TLabel", font=("Segoe UI Semibold", 10), foreground=ACCENT, background=BG)
        style.configure(
            "Accent.TButton",
            background=ACCENT,
            foreground="#06100a",
            borderwidth=0,
            padding=(16, 10),
            font=("Segoe UI Semibold", 10),
        )
        style.map("Accent.TButton", background=[("active", "#6fe3a1"), ("disabled", BORDER)])
        style.configure(
            "Quiet.TButton",
            background=SURFACE_ALT,
            foreground=TEXT,
            bordercolor=BORDER,
            padding=(12, 9),
        )
        style.map("Quiet.TButton", background=[("active", "#213139")])
        style.configure("TCheckbutton", background=SURFACE, foreground=TEXT, padding=4)
        style.map("TCheckbutton", background=[("active", SURFACE)], foreground=[("disabled", MUTED)])
        style.configure("TEntry", fieldbackground="#0e171b", foreground=TEXT, insertcolor=TEXT, bordercolor=BORDER)
        style.configure("Horizontal.TProgressbar", troughcolor=SURFACE_ALT, background=ACCENT, borderwidth=0)

    def _build_layout(self) -> None:
        header = ttk.Frame(self.root, padding=(24, 18, 24, 12))
        header.pack(fill="x")
        ttk.Label(header, text="PLANT ENERGY MCP", style="Title.TLabel").pack(side="left")
        ttk.Label(header, textvariable=self.status_text, style="Status.TLabel").pack(side="right", pady=8)

        self.progress = ttk.Progressbar(self.root, mode="indeterminate", style="Horizontal.TProgressbar")
        self.progress.pack(fill="x")

        body = ttk.Panedwindow(self.root, orient="horizontal")
        body.pack(fill="both", expand=True, padx=24, pady=(14, 18))

        config = ttk.Frame(body, style="Surface.TFrame", padding=20, width=330)
        workspace = ttk.Frame(body, style="Surface.TFrame", padding=20)
        body.add(config, weight=0)
        body.add(workspace, weight=1)
        self._build_config(config)
        self._build_workspace(workspace)

    def _field(self, parent: ttk.Frame, label: str, variable: tk.StringVar, *, secret: bool = False) -> None:
        ttk.Label(parent, text=label, style="Muted.TLabel", background=SURFACE).pack(anchor="w", pady=(10, 4))
        ttk.Entry(parent, textvariable=variable, show="•" if secret else "").pack(fill="x")

    def _build_config(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Configuración", style="Section.TLabel").pack(anchor="w")
        ttk.Label(
            parent,
            text="Las claves viven solo en esta ventana y no se guardan.",
            style="Muted.TLabel",
            background=SURFACE,
            wraplength=280,
        ).pack(anchor="w", pady=(4, 8))
        self._field(parent, "API key de Gemini", self.api_key, secret=True)
        self._field(parent, "Modelo", self.model)
        self._field(parent, "Base URL de Gemini", self.base_url)
        self._field(parent, "URL MCP remota", self.remote_url)
        self._field(parent, "Token MCP de Render", self.remote_token, secret=True)

        ttk.Label(parent, text="Servidores", style="Section.TLabel").pack(anchor="w", pady=(18, 4))
        labels = {
            "plant-local": "Industrial local",
            "filesystem": "Filesystem oficial",
            "git": "Git oficial",
            "plant-remote": "Industrial remoto",
        }
        for name, flag in self.server_flags.items():
            ttk.Checkbutton(parent, text=labels[name], variable=flag).pack(anchor="w")

        self.connect_button = ttk.Button(parent, text="Conectar proyecto", style="Accent.TButton", command=self.connect)
        self.connect_button.pack(fill="x", pady=(18, 8))
        ttk.Button(parent, text="Comprobar Render", style="Quiet.TButton", command=self.check_remote).pack(fill="x")

    def _build_workspace(self, parent: ttk.Frame) -> None:
        self.notebook = ttk.Notebook(parent)
        self.notebook.pack(fill="both", expand=True)
        chat_tab = ttk.Frame(self.notebook, style="Surface.TFrame", padding=14)
        self.demo_tab = ttk.Frame(self.notebook, style="Surface.TFrame", padding=14)
        self.notebook.add(chat_tab, text="  Conversación  ")
        self.notebook.add(self.demo_tab, text="  Demostraciones  ")

        ttk.Label(chat_tab, text="Chatbot anfitrión", style="Section.TLabel").pack(anchor="w")
        self.chat = scrolledtext.ScrolledText(
            chat_tab,
            bg="#0e171b",
            fg=TEXT,
            insertbackground=TEXT,
            selectbackground=ACCENT_DARK,
            relief="flat",
            font=("Segoe UI", 10),
            padx=14,
            pady=14,
            wrap="word",
            state="disabled",
        )
        self.chat.pack(fill="both", expand=True, pady=(10, 10))
        self.chat.tag_configure("user", foreground="#9dd9ff", font=("Segoe UI Semibold", 10))
        self.chat.tag_configure("bot", foreground=TEXT)
        self.chat.tag_configure("system", foreground=MUTED)
        quick = ttk.Frame(chat_tab, style="Surface.TFrame")
        quick.pack(fill="x", pady=(0, 8))
        ttk.Button(
            quick,
            text="Alan Turing",
            style="Quiet.TButton",
            command=lambda: self.prompt.set("¿Quién fue Alan Turing?"),
        ).pack(side="left", padx=(0, 6))
        ttk.Button(
            quick,
            text="Continuación",
            style="Quiet.TButton",
            command=lambda: self.prompt.set("¿En qué año nació?"),
        ).pack(side="left", padx=6)
        ttk.Button(
            quick,
            text="Reporte remoto",
            style="Quiet.TButton",
            command=lambda: self.prompt.set("Usa plant_remote__get_energy_report y dime qué equipo supera su umbral."),
        ).pack(side="left", padx=6)
        ttk.Button(quick, text="Ver log", style="Quiet.TButton", command=self.show_log).pack(side="right")
        ttk.Button(quick, text="Herramientas", style="Quiet.TButton", command=self.open_tool_picker).pack(
            side="right", padx=(0, 8)
        )

        composer = ttk.Frame(chat_tab, style="Surface.TFrame")
        composer.pack(fill="x")
        self.prompt = tk.StringVar()
        entry = ttk.Entry(composer, textvariable=self.prompt)
        entry.pack(side="left", fill="x", expand=True, padx=(0, 10), ipady=7)
        entry.bind("<Return>", lambda _: self.send_message())
        self.send_button = ttk.Button(composer, text="Enviar", style="Accent.TButton", command=self.send_message)
        self.send_button.pack(side="right")

        ttk.Label(self.demo_tab, text="Recorrido de presentación", style="Section.TLabel").pack(anchor="w")
        ttk.Label(
            self.demo_tab,
            text="Ejecuta cada evidencia desde aquí. No necesitas abrir tres terminales.",
            style="Muted.TLabel",
            background=SURFACE,
        ).pack(anchor="w", pady=(4, 12))
        actions = ttk.Frame(self.demo_tab, style="Surface.TFrame")
        actions.pack(fill="x")
        ttk.Button(actions, text="1  Comprobar Render", style="Quiet.TButton", command=self.check_remote).pack(
            side="left", padx=(0, 6)
        )
        ttk.Button(actions, text="2  Local ↔ remoto", style="Quiet.TButton", command=self.run_parity).pack(
            side="left", padx=6
        )
        ttk.Button(actions, text="3  Filesystem + Git", style="Quiet.TButton", command=self.run_filesystem_git).pack(
            side="left", padx=6
        )
        ttk.Button(actions, text="4  Pruebas", style="Quiet.TButton", command=self.run_tests).pack(side="left", padx=6)

        self.output = scrolledtext.ScrolledText(
            self.demo_tab,
            bg="#0e171b",
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            font=("Cascadia Mono", 9),
            padx=14,
            pady=14,
            wrap="word",
            state="disabled",
        )
        self.output.pack(fill="both", expand=True, pady=(12, 0))
        self._write_output("Listo. Comienza con “Comprobar Render”.")

    def _settings(self) -> RuntimeSettings:
        return RuntimeSettings(
            api_key=self.api_key.get(),
            model=self.model.get(),
            base_url=self.base_url.get(),
            remote_url=self.remote_url.get(),
            remote_token=self.remote_token.get(),
        )

    def _set_busy(self, value: bool, label: str = "") -> None:
        self.busy = value
        state = "disabled" if value else "normal"
        self.connect_button.configure(state=state)
        self.send_button.configure(state=state)
        if value:
            self.status_text.set(label or "Procesando…")
            self.progress.start(12)
        else:
            self.progress.stop()

    def _run_async(
        self,
        label: str,
        task: Callable[[], Any],
        on_success: Callable[[Any], None],
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        if self.busy:
            return
        self._set_busy(True, label)

        def worker() -> None:
            try:
                self.events.put(("success", (on_success, task())))
            except Exception as exc:
                self.events.put(("error", (exc, on_error)))

        threading.Thread(target=worker, daemon=True).start()

    def _drain_events(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                self._set_busy(False)
                if kind == "success":
                    callback, result = payload
                    callback(result)
                else:
                    error, callback = payload
                    self.status_text.set("Error")
                    if callback:
                        callback(error)
                    messagebox.showerror("No se pudo completar", str(error))
        except queue.Empty:
            pass
        self.root.after(100, self._drain_events)

    def _confirm_tool(self, prompt: str) -> bool:
        event = threading.Event()
        answer = {"value": False}

        def ask() -> None:
            answer["value"] = messagebox.askyesno("Confirmar herramienta", prompt)
            event.set()

        self.root.after(0, ask)
        event.wait()
        return answer["value"]

    def connect(self) -> None:
        settings = self._settings()
        selected = [name for name, flag in self.server_flags.items() if flag.get()]

        def task() -> tuple[ChatSession, list[str]]:
            if not selected:
                raise ValueError("Selecciona al menos un servidor MCP.")
            settings.validate(require_remote="plant-remote" in selected)
            os.environ.update(settings.environment())
            provider = OpenAiProvider(
                settings.api_key.strip(), settings.model.strip(), normalize_url(settings.base_url)
            )
            clients, notes = create_clients(selected, self.project_root)
            started, errors = [], list(notes)
            for client in clients:
                try:
                    started.append(client.start())
                except Exception as exc:
                    errors.append(f"{client.name}: {exc}")
            if not started:
                raise RuntimeError("Ningún servidor MCP pudo conectarse. " + " | ".join(errors))
            logger = McpAuditLogger(project_root=self.project_root)
            return ChatSession(provider, started, confirm=self._confirm_tool, logger=logger), errors

        def done(result: tuple[ChatSession, list[str]]) -> None:
            if self.session:
                self.session.close()
            self.session, notes = result
            self.status_text.set(f"Conectado · {len(self.session.clients)} servidores")
            self._append_chat("system", f"Conectado. Herramientas disponibles: {len(self.session.tools)}")
            for note in notes:
                self._append_chat("system", f"Aviso: {note}")

        self._run_async("Conectando servidores…", task, done)

    def send_message(self) -> None:
        text = self.prompt.get().strip()
        if not text:
            return
        command = text.lower()
        if command == "/help":
            self.prompt.set("")
            self._append_chat(
                "system",
                "Comandos locales: /tools abre el selector MCP, /log muestra el registro y /exit cierra la GUI.",
            )
            return
        if command == "/log":
            self.prompt.set("")
            self.show_log()
            return
        if command == "/exit":
            self.close()
            return
        if not self.session:
            messagebox.showinfo("Primero conecta", "Pulsa “Conectar proyecto” antes de enviar mensajes.")
            return
        if command == "/tools":
            self.prompt.set("")
            self.open_tool_picker()
            return
        if text in self.session.tools:
            self.prompt.set("")
            self.run_tool_directly(text, {})
            return
        self.prompt.set("")
        self._append_chat("user", f"Tú\n{text}")

        def done(reply: str) -> None:
            self.status_text.set(f"Conectado · {len(self.session.clients) if self.session else 0} servidores")
            self._append_chat("bot", f"Bot\n{reply}")

        self._run_async(
            "Consultando Gemini…",
            lambda: self.session.ask(text) if self.session else "",
            done,
            on_error=lambda _: self.prompt.set(text),
        )

    def open_tool_picker(self) -> None:
        if not self.session:
            messagebox.showinfo("Primero conecta", "Pulsa “Conectar proyecto” antes de abrir las herramientas.")
            return

        window = tk.Toplevel(self.root)
        window.title("Herramientas MCP disponibles")
        window.geometry("900x590")
        window.minsize(760, 500)
        window.configure(bg=BG)
        window.transient(self.root)

        header = ttk.Frame(window, padding=(22, 18, 22, 12))
        header.pack(fill="x")
        ttk.Label(header, text="HERRAMIENTAS MCP", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="Selecciona una herramienta. Se ejecutará directamente contra MCP, sin llamar a Gemini.",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(4, 0))

        body = ttk.Panedwindow(window, orient="horizontal")
        body.pack(fill="both", expand=True, padx=22, pady=(0, 14))
        list_panel = ttk.Frame(body, style="Surface.TFrame", padding=12)
        detail_panel = ttk.Frame(body, style="Surface.TFrame", padding=16)
        body.add(list_panel, weight=2)
        body.add(detail_panel, weight=3)

        names = sorted(self.session.tools)
        listbox = tk.Listbox(
            list_panel,
            bg="#0e171b",
            fg=TEXT,
            selectbackground=ACCENT_DARK,
            selectforeground=TEXT,
            relief="flat",
            font=("Cascadia Mono", 9),
            activestyle="none",
            exportselection=False,
        )
        scrollbar = ttk.Scrollbar(list_panel, orient="vertical", command=listbox.yview)
        listbox.configure(yscrollcommand=scrollbar.set)
        listbox.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        for name in names:
            listbox.insert("end", name)

        selected_name = tk.StringVar(value="Selecciona una herramienta")
        ttk.Label(detail_panel, textvariable=selected_name, style="Section.TLabel", wraplength=450).pack(anchor="w")
        description = tk.Text(
            detail_panel,
            height=5,
            bg=SURFACE,
            fg=MUTED,
            relief="flat",
            wrap="word",
            font=("Segoe UI", 10),
        )
        description.pack(fill="x", pady=(8, 12))
        description.configure(state="disabled")
        ttk.Label(detail_panel, text="Parámetros JSON", style="Section.TLabel").pack(anchor="w")
        ttk.Label(
            detail_panel,
            text="Para herramientas sin parámetros deja {}. Los campos obligatorios aparecen como plantilla.",
            style="Muted.TLabel",
            background=SURFACE,
            wraplength=450,
        ).pack(anchor="w", pady=(3, 7))
        arguments = scrolledtext.ScrolledText(
            detail_panel,
            height=12,
            bg="#0e171b",
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            font=("Cascadia Mono", 10),
            padx=10,
            pady=10,
            wrap="word",
        )
        arguments.pack(fill="both", expand=True)

        def selection() -> str | None:
            indexes = listbox.curselection()
            return names[indexes[0]] if indexes else None

        def update_detail(_: Any = None) -> None:
            name = selection()
            if not name or not self.session:
                return
            definition = self.session.tools[name].definition
            selected_name.set(name)
            description.configure(state="normal")
            description.delete("1.0", "end")
            description.insert("1.0", definition.get("description") or "Sin descripción.")
            description.configure(state="disabled")
            template = tool_argument_template(definition.get("inputSchema", {}))
            arguments.delete("1.0", "end")
            arguments.insert("1.0", json.dumps(template, ensure_ascii=False, indent=2))

        def execute(_: Any = None) -> None:
            name = selection()
            if not name:
                messagebox.showinfo("Selecciona una herramienta", "Elige una herramienta de la lista.", parent=window)
                return
            try:
                parsed = parse_tool_arguments(arguments.get("1.0", "end").strip())
            except (json.JSONDecodeError, ValueError) as exc:
                messagebox.showerror("Parámetros JSON inválidos", str(exc), parent=window)
                return
            window.destroy()
            self.run_tool_directly(name, parsed)

        footer = ttk.Frame(window, padding=(22, 0, 22, 18))
        footer.pack(fill="x")
        ttk.Button(footer, text="Cancelar", style="Quiet.TButton", command=window.destroy).pack(side="right")
        ttk.Button(footer, text="Ejecutar herramienta", style="Accent.TButton", command=execute).pack(
            side="right", padx=(0, 10)
        )

        listbox.bind("<<ListboxSelect>>", update_detail)
        listbox.bind("<Double-Button-1>", execute)
        listbox.bind("<Return>", execute)
        if names:
            listbox.selection_set(0)
            listbox.activate(0)
            update_detail()
        window.grab_set()
        listbox.focus_set()

    def run_tool_directly(self, name: str, arguments: dict[str, Any]) -> None:
        if not self.session:
            return
        shown_arguments = json.dumps(arguments, ensure_ascii=False)
        self._append_chat("user", f"Herramienta MCP\n{name} {shown_arguments}")

        def done(result: dict[str, Any]) -> None:
            self.status_text.set(f"Herramienta completada · {name}")
            rendered = json.dumps(result, ensure_ascii=False, indent=2)
            self._append_chat("bot", f"Resultado MCP\n{rendered}")

        self._run_async(
            f"Ejecutando {name}…",
            lambda: self.session.call_tool(name, arguments) if self.session else {},
            done,
        )

    def show_log(self) -> None:
        logger = self.session.logger if self.session else McpAuditLogger(project_root=self.project_root)
        records = logger.tail()
        if records:
            content = json.dumps(records, ensure_ascii=False, indent=2)
            self.status_text.set(f"Log MCP · {len(records)} entradas recientes")
        else:
            content = (
                "El log MCP todavía está vacío.\n\n"
                "1. Pulsa “Conectar proyecto”.\n"
                "2. Envía una consulta que utilice una herramienta MCP.\n"
                "3. Vuelve a pulsar “Ver log”.\n\n"
                f"Archivo esperado: {logger.path.resolve()}"
            )
            self.status_text.set("Log MCP vacío")
        self._write_output(content, clear=True)
        self.notebook.select(self.demo_tab)

    def check_remote(self) -> None:
        settings = self._settings()

        def task() -> str:
            url = health_url(settings.remote_url)
            with urllib.request.urlopen(url, timeout=90) as response:
                body = response.read().decode("utf-8", errors="replace")
                return f"HTTP {response.status} · {url}\n{body}"

        def done(output: str) -> None:
            self.status_text.set("Render disponible")
            self._write_output(output, clear=True)

        self._run_async("Comprobando Render…", task, done)

    def _run_demo(self, label: str, module: str, *, require_remote: bool = False, timeout: int = 180) -> None:
        settings = self._settings()

        def task() -> str:
            settings.validate(require_llm=False, require_remote=require_remote)
            return run_module(module, settings, self.project_root, timeout=timeout)

        def done(output: str) -> None:
            self.status_text.set("Verificación completada")
            self._write_output(output, clear=True)

        self._run_async(label, task, done)

    def run_parity(self) -> None:
        self._run_demo("Comparando local y remoto…", "demos.local_remote_parity_demo", require_remote=True)

    def run_filesystem_git(self) -> None:
        self._run_demo("Ejecutando Filesystem + Git…", "demos.filesystem_git_demo", timeout=240)

    def run_tests(self) -> None:
        self._run_demo("Ejecutando pruebas…", "unittest", timeout=240)

    def _append_chat(self, tag: str, text: str) -> None:
        self.chat.configure(state="normal")
        self.chat.insert("end", text + "\n\n", tag)
        self.chat.configure(state="disabled")
        self.chat.see("end")

    def _write_output(self, text: str, *, clear: bool = False) -> None:
        token = self.remote_token.get().strip()
        key = self.api_key.get().strip()
        safe = text.replace(token, "[REDACTED]") if token else text
        safe = safe.replace(key, "[REDACTED]") if key else safe
        self.output.configure(state="normal")
        if clear:
            self.output.delete("1.0", "end")
        self.output.insert("end", safe + "\n")
        self.output.configure(state="disabled")
        self.output.see("end")

    def close(self) -> None:
        if self.session:
            self.session.close()
        self.root.destroy()


def launch() -> None:
    root = tk.Tk()
    ProjectApp(root)
    root.mainloop()
