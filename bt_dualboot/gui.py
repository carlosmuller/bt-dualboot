import io
import os
import queue
import re
import threading
import traceback
from contextlib import redirect_stderr, redirect_stdout

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
    from tkinter.scrolledtext import ScrolledText
except ImportError as err:  # pragma: no cover - depends on system Python build
    tk = None
    filedialog = None
    messagebox = None
    ttk = None
    ScrolledText = None
    TK_IMPORT_ERROR = err
else:
    TK_IMPORT_ERROR = None

from bt_dualboot.__meta__ import APP_NAME, __version__
from bt_dualboot.cli.app import DEFAULT_BACKUP_PATH, run_args


OPERATION_LIST_DEVICES = "List Bluetooth devices"
OPERATION_LIST_WINDOWS = "List Windows mount points"
OPERATION_SYNC_DEVICES = "Sync selected devices"
OPERATION_SYNC_ALL = "Sync all devices"

BACKUP_DEFAULT = "Backup to default path"
BACKUP_CUSTOM = "Backup to custom path"
BACKUP_NONE = "No backup"

MAC_PATTERN = re.compile(r"^[A-F0-9:]+$")
DEFAULT_WINDOWS_MOUNT = "/mnt/win"


class GuiValidationError(Exception):
    pass


def _split_macs(value):
    return [item.strip().upper() for item in re.split(r"[\s,]+", value) if item.strip()]


def default_windows_mount():
    if os.path.isdir(DEFAULT_WINDOWS_MOUNT):
        return DEFAULT_WINDOWS_MOUNT
    return ""


def validate_settings(settings):
    operation = settings["operation"]

    if settings["windows_mount"]:
        if not os.path.isdir(settings["windows_mount"]):
            raise GuiValidationError("Windows mount point does not exist or is not a directory.")

    if operation == OPERATION_SYNC_DEVICES:
        macs = _split_macs(settings["macs"])
        if not macs:
            raise GuiValidationError("Enter at least one device MAC address to sync.")

        invalid_macs = [mac for mac in macs if MAC_PATTERN.match(mac) is None]
        if invalid_macs:
            raise GuiValidationError(
                "Invalid MAC address: {}. Use A-F, 0-9 and colon only.".format(invalid_macs[0])
            )

    if operation in (OPERATION_SYNC_DEVICES, OPERATION_SYNC_ALL):
        if settings["backup_mode"] == BACKUP_CUSTOM:
            if not settings["backup_path"]:
                raise GuiValidationError("Choose a backup directory or use the default backup path.")
            parent = os.path.dirname(os.path.abspath(settings["backup_path"]))
            if parent and not os.path.isdir(parent):
                raise GuiValidationError("Backup parent directory does not exist.")


def build_cli_args(settings):
    args = []

    if settings["windows_mount"]:
        args.extend(["--win", settings["windows_mount"]])

    if settings["bot"]:
        args.append("--bot")

    operation = settings["operation"]
    if operation == OPERATION_LIST_DEVICES:
        args.append("--list")
    elif operation == OPERATION_LIST_WINDOWS:
        args.append("--list-win-mounts")
    elif operation == OPERATION_SYNC_DEVICES:
        if settings["dry_run"]:
            args.append("--dry-run")
        args.extend(["--sync"] + _split_macs(settings["macs"]))
    elif operation == OPERATION_SYNC_ALL:
        if settings["dry_run"]:
            args.append("--dry-run")
        args.append("--sync-all")
    else:
        raise GuiValidationError("Choose an operation to run.")

    if operation in (OPERATION_SYNC_DEVICES, OPERATION_SYNC_ALL):
        backup_mode = settings["backup_mode"]
        if backup_mode == BACKUP_NONE:
            args.append("--no-backup")
        elif backup_mode == BACKUP_CUSTOM:
            args.extend(["--backup", settings["backup_path"]])
        else:
            args.append("--backup")

    return args


def execute_cli_args(args):
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    exit_code = 0

    try:
        with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
            run_args(args)
    except SystemExit as err:
        if isinstance(err.code, int):
            exit_code = err.code
        elif err.code is None:
            exit_code = 0
        else:
            exit_code = 1
            print(err.code, file=stderr_buffer)
    except Exception as err:  # pragma: no cover - defensive GUI boundary
        exit_code = 1
        print("Unexpected error: {}".format(err), file=stderr_buffer)
        print(traceback.format_exc(), file=stderr_buffer)

    return exit_code, stdout_buffer.getvalue(), stderr_buffer.getvalue()


def extract_syncable_macs_from_list_output(output):
    macs = []
    in_needs_sync_section = False

    for line in output.splitlines():
        stripped = line.strip()

        bot_match = re.match(r"^needs_sync\s+([A-F0-9:]+)(?:\s|$)", stripped)
        if bot_match is not None:
            mac = bot_match.group(1)
            if mac != "NONE":
                macs.append(mac)
            continue

        if stripped == "Needs sync":
            in_needs_sync_section = True
            continue

        if stripped == "Have to be paired in Windows":
            in_needs_sync_section = False
            continue

        if in_needs_sync_section:
            match = re.match(r"^\[([A-F0-9:]+)\]\s+", stripped)
            if match is not None:
                macs.append(match.group(1))

    return macs


TkBase = tk.Tk if tk is not None else object


class BtDualbootGui(TkBase):
    def __init__(self):
        if TK_IMPORT_ERROR is not None:
            raise SystemExit("Tkinter is required to run the GUI: {}".format(TK_IMPORT_ERROR))

        tk.Tk.__init__(self)
        self.title("{} GUI".format(APP_NAME))
        self.minsize(760, 560)

        self._events = queue.Queue()
        self._worker = None

        self.operation_var = tk.StringVar(value=OPERATION_LIST_DEVICES)
        self.windows_mount_var = tk.StringVar(value=default_windows_mount())
        self.macs_var = tk.StringVar()
        self.bot_var = tk.BooleanVar(value=False)
        self.dry_run_var = tk.BooleanVar(value=True)
        self.backup_mode_var = tk.StringVar(value=BACKUP_DEFAULT)
        self.backup_path_var = tk.StringVar(value=DEFAULT_BACKUP_PATH)
        self.status_var = tk.StringVar(value="Idle")

        self._build_widgets()
        self._sync_form_state()
        self.after(100, self._poll_events)

    def _build_widgets(self):
        container = ttk.Frame(self, padding=12)
        container.grid(row=0, column=0, sticky="nsew")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        form = ttk.LabelFrame(container, text="Inputs", padding=10)
        form.grid(row=0, column=0, sticky="ew")
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text="Operation").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        operation = ttk.Combobox(
            form,
            textvariable=self.operation_var,
            values=(
                OPERATION_LIST_DEVICES,
                OPERATION_LIST_WINDOWS,
                OPERATION_SYNC_DEVICES,
                OPERATION_SYNC_ALL,
            ),
            state="readonly",
        )
        operation.grid(row=0, column=1, columnspan=2, sticky="ew", pady=4)
        operation.bind("<<ComboboxSelected>>", lambda _event: self._sync_form_state())

        ttk.Label(form, text="Windows mount").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(form, textvariable=self.windows_mount_var).grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Button(form, text="Browse", command=self._choose_windows_mount).grid(
            row=1, column=2, sticky="ew", padx=(8, 0), pady=4
        )

        ttk.Label(form, text="Device MACs").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=4)
        self.macs_entry = ttk.Entry(form, textvariable=self.macs_var)
        self.macs_entry.grid(row=2, column=1, columnspan=2, sticky="ew", pady=4)

        self.dry_run_check = ttk.Checkbutton(form, text="Dry run", variable=self.dry_run_var)
        self.dry_run_check.grid(row=3, column=1, sticky="w", pady=4)

        ttk.Checkbutton(form, text="Robot-friendly list output", variable=self.bot_var).grid(
            row=3, column=2, sticky="w", pady=4
        )

        ttk.Label(form, text="Backup").grid(row=4, column=0, sticky="w", padx=(0, 8), pady=4)
        self.backup_combo = ttk.Combobox(
            form,
            textvariable=self.backup_mode_var,
            values=(BACKUP_DEFAULT, BACKUP_CUSTOM, BACKUP_NONE),
            state="readonly",
        )
        self.backup_combo.grid(row=4, column=1, columnspan=2, sticky="ew", pady=4)
        self.backup_combo.bind("<<ComboboxSelected>>", lambda _event: self._sync_form_state())

        ttk.Label(form, text="Backup path").grid(row=5, column=0, sticky="w", padx=(0, 8), pady=4)
        self.backup_path_entry = ttk.Entry(form, textvariable=self.backup_path_var)
        self.backup_path_entry.grid(row=5, column=1, sticky="ew", pady=4)
        self.backup_browse_button = ttk.Button(form, text="Browse", command=self._choose_backup_path)
        self.backup_browse_button.grid(row=5, column=2, sticky="ew", padx=(8, 0), pady=4)

        actions = ttk.Frame(container)
        actions.grid(row=1, column=0, sticky="ew", pady=(10, 10))
        actions.columnconfigure(3, weight=1)

        self.run_button = ttk.Button(actions, text="Run", command=self._run)
        self.run_button.grid(row=0, column=0, padx=(0, 8))
        ttk.Button(actions, text="Clear Output", command=self._clear_output).grid(row=0, column=1, padx=(0, 8))
        self.progress = ttk.Progressbar(actions, mode="indeterminate", length=160)
        self.progress.grid(row=0, column=2, padx=(0, 12))
        ttk.Label(actions, textvariable=self.status_var).grid(row=0, column=3, sticky="w")

        output_frame = ttk.LabelFrame(container, text="Output", padding=10)
        output_frame.grid(row=2, column=0, sticky="nsew")
        output_frame.rowconfigure(0, weight=1)
        output_frame.columnconfigure(0, weight=1)
        container.rowconfigure(2, weight=1)

        self.output = ScrolledText(output_frame, height=18, wrap="word")
        self.output.grid(row=0, column=0, sticky="nsew")
        self.output.insert("end", "{} {}\nStatus: Idle\n".format(APP_NAME, __version__))
        self.output.configure(state="disabled")

    def _settings(self):
        return {
            "operation": self.operation_var.get(),
            "windows_mount": self.windows_mount_var.get().strip(),
            "macs": self.macs_var.get().strip(),
            "bot": self.bot_var.get(),
            "dry_run": self.dry_run_var.get(),
            "backup_mode": self.backup_mode_var.get(),
            "backup_path": self.backup_path_var.get().strip(),
        }

    def _choose_windows_mount(self):
        path = filedialog.askdirectory(title="Choose Windows mount point")
        if path:
            self.windows_mount_var.set(path)

    def _choose_backup_path(self):
        path = filedialog.askdirectory(title="Choose backup directory")
        if path:
            self.backup_path_var.set(path)

    def _sync_form_state(self):
        operation = self.operation_var.get()
        is_sync = operation in (OPERATION_SYNC_DEVICES, OPERATION_SYNC_ALL)
        is_sync_selected = operation == OPERATION_SYNC_DEVICES
        is_custom_backup = self.backup_mode_var.get() == BACKUP_CUSTOM

        self.macs_entry.configure(state="normal" if is_sync_selected else "disabled")
        self.dry_run_check.configure(state="normal" if is_sync else "disabled")
        self.backup_combo.configure(state="readonly" if is_sync else "disabled")
        self.backup_path_entry.configure(state="normal" if is_sync and is_custom_backup else "disabled")
        self.backup_browse_button.configure(state="normal" if is_sync and is_custom_backup else "disabled")

    def _append_output(self, text):
        if not text:
            return
        self.output.configure(state="normal")
        self.output.insert("end", text)
        if not text.endswith("\n"):
            self.output.insert("end", "\n")
        self.output.see("end")
        self.output.configure(state="disabled")

    def _clear_output(self):
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.configure(state="disabled")

    def _run(self):
        if self._worker is not None and self._worker.is_alive():
            return

        settings = self._settings()
        try:
            validate_settings(settings)
            args = build_cli_args(settings)
        except GuiValidationError as err:
            self.status_var.set("Error")
            messagebox.showerror("Invalid input", str(err))
            return

        self.status_var.set("Running")
        self.run_button.configure(state="disabled")
        self.progress.start(10)
        self._append_output("\n$ {} {}\n".format(APP_NAME, " ".join(args)))

        self._worker = threading.Thread(target=self._run_worker, args=(args, settings))
        self._worker.daemon = True
        self._worker.start()

    def _run_worker(self, args, settings):
        self._events.put(("complete", (settings, execute_cli_args(args))))

    def _poll_events(self):
        try:
            while True:
                event, payload = self._events.get_nowait()
                if event == "complete":
                    self._handle_complete(payload)
        except queue.Empty:
            pass

        self.after(100, self._poll_events)

    def _handle_complete(self, payload):
        settings, result = payload
        exit_code, stdout, stderr = result
        self.progress.stop()
        self.run_button.configure(state="normal")

        if stdout:
            self._append_output(stdout)
        if stderr:
            self._append_output(stderr)

        if exit_code == 0:
            self.status_var.set("Success")
            self._populate_macs_from_list(settings, stdout)
        else:
            self.status_var.set("Error")
            messagebox.showerror("Execution failed", "The command failed. See the output panel for details.")

    def _populate_macs_from_list(self, settings, stdout):
        if settings["operation"] != OPERATION_LIST_DEVICES:
            return

        macs = extract_syncable_macs_from_list_output(stdout)
        if not macs:
            return

        self.macs_var.set(" ".join(macs))
        self._append_output("Device MACs updated from syncable listed devices.\n")


def main():
    app = BtDualbootGui()
    app.mainloop()


if __name__ == "__main__":
    main()
