"""Hackatime for Python IDLE.

Tracks coding time in IDLE editor windows and sends WakaTime-compatible
heartbeats to Hackatime through wakatime-cli.

Install with the Python that runs IDLE:

    python3 IdleHackatime.py install

Remove with:

    python3 IdleHackatime.py uninstall
"""

import configparser
import json
import logging
import os
import platform
import shutil
import site
import subprocess
import sys
import sysconfig
import tempfile
import threading
import time
import urllib.request
import webbrowser
import zipfile

__version__ = "1.0.0"

EXTENSION_NAME = "IdleHackatime"
DEFAULT_API_URL = "https://hackatime.hackclub.com/api/hackatime/v1"
HEARTBEAT_INTERVAL_SECONDS = 120
STATUS_REFRESH_MS = 2000
TODAY_REFRESH_SECONDS = 60
CLI_TIMEOUT_SECONDS = 60
CLI_DOWNLOAD_URL = (
    "https://github.com/wakatime/wakatime-cli/releases/latest/download/"
    "wakatime-cli-{os}-{arch}.zip"
)

HOME_FOLDER = os.path.realpath(
    os.environ.get("WAKATIME_HOME") or os.path.expanduser("~")
)
RESOURCES_FOLDER = os.path.join(HOME_FOLDER, ".wakatime")
CONFIG_FILE = os.path.join(HOME_FOLDER, ".wakatime.cfg")
LOG_FILE = os.path.join(RESOURCES_FOLDER, "idle-hackatime.log")
IDLE_CONFIG_FILE = os.path.join(
    os.path.expanduser("~"), ".idlerc", "config-extensions.cfg"
)

PYTHON_EXTENSIONS = (".py", ".pyw", ".pyi")

log = logging.getLogger("idle-hackatime")


def read_config():
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read(CONFIG_FILE, encoding="utf-8")
    except configparser.Error as err:
        log.warning("Could not parse %s: %s", CONFIG_FILE, err)
    return parser


def get_setting(name, default=None):
    parser = read_config()
    if parser.has_option("settings", name):
        value = parser.get("settings", name).strip()
        if value:
            return value
    return default


def write_settings(**values):
    parser = read_config()
    if not parser.has_section("settings"):
        parser.add_section("settings")
    for name, value in values.items():
        parser.set("settings", name, value)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        parser.write(f)


def api_key():
    return get_setting("api_key")


def api_url():
    return get_setting("api_url", DEFAULT_API_URL)


def dashboard_url():
    url = api_url()
    marker = url.find("/api/")
    return url[:marker] if marker != -1 else url


def is_debug():
    return (get_setting("debug", "false") or "").lower() == "true"


def configure_logging():
    if log.handlers:
        return
    try:
        os.makedirs(RESOURCES_FOLDER, exist_ok=True)
        handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    except OSError:
        handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    )
    log.addHandler(handler)
    log.setLevel(logging.DEBUG if is_debug() else logging.INFO)
    log.propagate = False


def cli_os():
    return platform.system().lower()


def cli_arch():
    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        return "amd64"
    if machine in ("arm64", "aarch64"):
        return "arm64"
    if machine.startswith("armv7") or machine == "arm":
        return "arm"
    if machine in ("i386", "i686", "x86"):
        return "386"
    return machine


def cli_binary_path():
    return os.path.join(
        RESOURCES_FOLDER, "wakatime-cli-{}-{}".format(cli_os(), cli_arch())
    )


def find_cli():
    candidates = [
        os.path.join(RESOURCES_FOLDER, "wakatime-cli"),
        cli_binary_path(),
        shutil.which("wakatime-cli"),
        shutil.which("wakatime"),
    ]
    for path in candidates:
        if path and os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None


def download(url, destination):
    """Download url to destination, falling back to curl.

    python.org builds on macOS ship without CA certificates until the user runs
    "Install Certificates.command", so urllib can fail where curl succeeds.
    """
    try:
        with urllib.request.urlopen(url, timeout=CLI_TIMEOUT_SECONDS) as resp:
            with open(destination, "wb") as f:
                shutil.copyfileobj(resp, f)
        return
    except Exception as err:
        log.info("urllib download failed (%s), trying curl", err)
    curl = shutil.which("curl")
    if not curl:
        raise RuntimeError("Could not download {} and curl is missing".format(url))
    subprocess.run(
        [curl, "-fsSL", "-o", destination, url],
        check=True,
        timeout=CLI_TIMEOUT_SECONDS * 5,
    )


def install_cli():
    os.makedirs(RESOURCES_FOLDER, exist_ok=True)
    url = CLI_DOWNLOAD_URL.format(os=cli_os(), arch=cli_arch())
    binary = cli_binary_path()
    log.info("Downloading wakatime-cli from %s", url)
    with tempfile.TemporaryDirectory() as tmp:
        archive = os.path.join(tmp, "wakatime-cli.zip")
        download(url, archive)
        with zipfile.ZipFile(archive) as zf:
            member = os.path.basename(binary)
            with zf.open(member) as src, open(binary + ".tmp", "wb") as dst:
                shutil.copyfileobj(src, dst)
    os.chmod(binary + ".tmp", 0o755)
    os.replace(binary + ".tmp", binary)

    link = os.path.join(RESOURCES_FOLDER, "wakatime-cli")
    try:
        if os.path.lexists(link):
            os.remove(link)
        os.symlink(binary, link)
    except OSError:
        shutil.copy2(binary, link)
        os.chmod(link, 0o755)
    log.info("Installed wakatime-cli at %s", binary)
    return binary


def ensure_cli():
    return find_cli() or install_cli()


def cli_supports(cli, flag):
    try:
        result = subprocess.run(
            [cli, "--help"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=CLI_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return flag.encode() in result.stdout


def user_agent():
    return "idle/{} idle-hackatime/{}".format(platform.python_version(), __version__)


def heartbeat_args(heartbeat, supports_line_changes):
    entity = heartbeat["entity"]
    args = [
        "--entity", entity,
        "--entity-type", "file",
        "--category", "coding",
        "--plugin", user_agent(),
        "--time", "{:.6f}".format(heartbeat["time"]),
        "--lineno", str(heartbeat["lineno"]),
        "--cursorpos", str(heartbeat["cursorpos"]),
        "--lines-in-file", str(heartbeat["lines"]),
        "--alternate-project", os.path.basename(os.path.dirname(entity)),
        # Explicit true/false so wakatime-cli always includes is_write.
        "--write={}".format("true" if heartbeat["is_write"] else "false"),
    ]
    if entity.lower().endswith(PYTHON_EXTENSIONS):
        args += ["--alternate-language", "Python"]
    if supports_line_changes:
        # "=" form so negative values aren't read as flags.
        args.append("--human-line-changes={}".format(heartbeat["human_line_changes"]))
    return args


class HeartbeatSender:
    """Runs wakatime-cli off the Tk thread, one heartbeat at a time."""

    def __init__(self):
        self._lock = threading.Lock()
        self._wakeup = threading.Condition(self._lock)
        self._queue = []
        self._cli = None
        self._supports_line_changes = False
        self._last_today_fetch = 0.0
        self.today_text = ""
        self._thread = threading.Thread(
            target=self._run, name="idle-hackatime", daemon=True
        )
        self._thread.start()

    def send(self, heartbeat):
        with self._lock:
            self._queue.append(heartbeat)
            self._wakeup.notify()

    def _run(self):
        try:
            self._cli = ensure_cli()
            self._supports_line_changes = cli_supports(
                self._cli, "--human-line-changes"
            )
            log.info(
                "Using %s (human line changes: %s)",
                self._cli,
                self._supports_line_changes,
            )
        except Exception:
            log.exception("Could not set up wakatime-cli")
            self.today_text = "Hackatime: wakatime-cli unavailable"
            return
        self._refresh_today()
        while True:
            with self._lock:
                while not self._queue:
                    if not self._wakeup.wait(timeout=TODAY_REFRESH_SECONDS):
                        break
                pending, self._queue = self._queue, []
            for heartbeat in pending:
                self._send_one(heartbeat)
            if pending or time.time() - self._last_today_fetch > TODAY_REFRESH_SECONDS:
                self._refresh_today()

    def _send_one(self, heartbeat):
        if not api_key():
            log.warning("No api_key in %s; heartbeat skipped", CONFIG_FILE)
            return
        cmd = [self._cli] + heartbeat_args(heartbeat, self._supports_line_changes)
        log.info("Sending heartbeat %s", json.dumps(heartbeat, sort_keys=True))
        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=CLI_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.SubprocessError) as err:
            log.error("wakatime-cli failed to run: %s", err)
            return
        output = result.stdout.decode("utf-8", "replace").strip()
        if result.returncode == 0:
            log.info("Heartbeat sent for %s", heartbeat["entity"])
        else:
            # Non-zero exits queue the heartbeat offline inside wakatime-cli.
            log.error("wakatime-cli exited %s: %s", result.returncode, output)

    def _refresh_today(self):
        self._last_today_fetch = time.time()
        if not api_key():
            self.today_text = "Hackatime: set API key in Options"
            return
        try:
            result = subprocess.run(
                [self._cli, "--today", "--plugin", user_agent()],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=CLI_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.SubprocessError):
            return
        text = result.stdout.decode("utf-8", "replace").strip()
        if result.returncode == 0 and text:
            self.today_text = "Hackatime: " + text


class ActivityTracker:
    def __init__(self, sender):
        self.sender = sender
        self.last_entity = None
        self.last_time = 0.0
        self.line_changes = {}

    def record_line_changes(self, entity, delta):
        self.line_changes[entity] = self.line_changes.get(entity, 0) + delta

    def handle(self, entity, lineno, cursorpos, lines, is_write):
        now = time.time()
        due = (
            is_write
            or entity != self.last_entity
            or now - self.last_time >= HEARTBEAT_INTERVAL_SECONDS
        )
        if not due or not api_key():
            return
        self.last_entity = entity
        self.last_time = now
        self.sender.send(
            {
                "entity": entity,
                "time": now,
                "is_write": is_write,
                "lineno": lineno,
                "cursorpos": cursorpos,
                "lines": lines,
                "human_line_changes": self.line_changes.pop(entity, 0),
            }
        )


_tracker = None


def tracker():
    global _tracker
    if _tracker is None:
        configure_logging()
        _tracker = ActivityTracker(HeartbeatSender())
    return _tracker


try:
    from idlelib.delegator import Delegator
except ImportError:  # Running the installer without idlelib.
    Delegator = object


class _ChangeFilter(Delegator):
    """Percolator filter that observes every insert and delete in the text."""

    def __init__(self, extension):
        Delegator.__init__(self)
        self.extension = extension

    def insert(self, index, chars, tags=None):
        self.delegate.insert(index, chars, tags)
        self.extension.on_text_change(chars.count("\n"))

    def delete(self, index1, index2=None):
        text = self.extension.text
        end = index2 if index2 is not None else index1 + "+1c"
        removed = text.get(index1, end).count("\n")
        self.delegate.delete(index1, index2)
        self.extension.on_text_change(-removed)


class IdleHackatime:
    """IDLE extension entry point, created once per editor window."""

    menudefs = [
        (
            "options",
            [
                None,
                ("Hackatime API _Key...", "<<hackatime-api-key>>"),
                ("Hackatime _Dashboard", "<<hackatime-dashboard>>"),
            ],
        )
    ]

    def __init__(self, editwin):
        self.editwin = editwin
        self.text = editwin.text
        self.tracker = tracker()
        self._activity_job = None
        self._status_job = None

        self.filter = _ChangeFilter(self)
        editwin.per.insertfilter(self.filter)

        io = editwin.io
        original_writefile = io.writefile

        def writefile(filename):
            # Read the cursor first: IDLE may append a final newline while
            # writing, which moves the insert mark to a new empty line.
            lineno, cursorpos = self.cursor()
            ok = original_writefile(filename)
            if ok:
                self.on_write(filename, lineno, cursorpos)
            return ok

        io.writefile = writefile

        self.text.bind("<<hackatime-api-key>>", self.api_key_event)
        self.text.bind("<<hackatime-dashboard>>", self.dashboard_event)
        for sequence in ("<KeyRelease>", "<ButtonRelease>", "<FocusIn>"):
            self.text.bind(sequence, self.on_activity, add="+")

        self._refresh_status()
        if not api_key():
            self.text.after(500, self._prompt_for_missing_key)

    def filename(self):
        name = self.editwin.io.filename if self.editwin.io else None
        return os.path.realpath(name) if name else None

    def cursor(self):
        line, column = self.text.index("insert").split(".")
        return int(line), int(column) + 1

    def line_count(self):
        return int(self.text.index("end-1c").split(".")[0])

    def _heartbeat(self, entity, is_write, lineno=None, cursorpos=None):
        if lineno is None:
            lineno, cursorpos = self.cursor()
        self.tracker.handle(entity, lineno, cursorpos, self.line_count(), is_write)

    def on_text_change(self, line_delta):
        entity = self.filename()
        if not entity:
            return
        if line_delta:
            self.tracker.record_line_changes(entity, line_delta)
        self._schedule_activity()

    def on_activity(self, event=None):
        self._schedule_activity()

    def _schedule_activity(self):
        # Coalesce bursts of events and read the cursor once Tk has settled.
        if self._activity_job is None:
            self._activity_job = self.text.after_idle(self._flush_activity)

    def _flush_activity(self):
        self._activity_job = None
        entity = self.filename()
        if entity:
            self._heartbeat(entity, is_write=False)

    def on_write(self, filename, lineno, cursorpos):
        self._heartbeat(os.path.realpath(filename), True, lineno, cursorpos)

    def api_key_event(self, event=None):
        from tkinter import simpledialog

        key = simpledialog.askstring(
            "Hackatime API Key",
            "Paste your Hackatime API key.\n"
            "Find it at {}/my/settings".format(dashboard_url()),
            initialvalue=api_key() or "",
            parent=self.editwin.top,
        )
        if key and key.strip():
            write_settings(api_key=key.strip(), api_url=api_url())
            self.tracker.sender._last_today_fetch = 0.0
        return "break"

    def dashboard_event(self, event=None):
        webbrowser.open(dashboard_url())
        return "break"

    def _prompt_for_missing_key(self):
        global _prompted_for_key
        if _prompted_for_key or api_key():
            return
        _prompted_for_key = True
        self.api_key_event()

    def _refresh_status(self):
        status_bar = getattr(self.editwin, "status_bar", None)
        if status_bar is not None and self.tracker.sender.today_text:
            status_bar.set_label("hackatime", self.tracker.sender.today_text)
        self._status_job = self.text.after(STATUS_REFRESH_MS, self._refresh_status)

    def close(self):
        # IDLE calls this before destroying the window, so the jobs can still be cancelled.
        for job in (self._activity_job, self._status_job):
            if job is not None:
                self.text.after_cancel(job)
        if self.editwin.per is not None:
            self.editwin.per.removefilter(self.filter)


_prompted_for_key = False


def install_dir():
    if site.ENABLE_USER_SITE:
        return site.getusersitepackages()
    return sysconfig.get_paths()["purelib"]


def read_idle_config():
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    parser.read(IDLE_CONFIG_FILE, encoding="utf-8")
    return parser


def write_idle_config(parser):
    os.makedirs(os.path.dirname(IDLE_CONFIG_FILE), exist_ok=True)
    with open(IDLE_CONFIG_FILE, "w", encoding="utf-8") as f:
        parser.write(f)


def install(argv):
    source = os.path.abspath(__file__)
    target_dir = install_dir()
    os.makedirs(target_dir, exist_ok=True)
    target = os.path.join(target_dir, os.path.basename(source))
    if os.path.abspath(target) != source:
        shutil.copyfile(source, target)
    print("Installed {} to {}".format(EXTENSION_NAME, target))

    parser = read_idle_config()
    if not parser.has_section(EXTENSION_NAME):
        parser.add_section(EXTENSION_NAME)
    parser.set(EXTENSION_NAME, "enable", "True")
    parser.set(EXTENSION_NAME, "enable_editor", "True")
    parser.set(EXTENSION_NAME, "enable_shell", "False")
    write_idle_config(parser)
    print("Enabled the extension in {}".format(IDLE_CONFIG_FILE))

    configure_logging()
    print("wakatime-cli: {}".format(ensure_cli()))

    key = os.environ.get("HACKATIME_API_KEY") or api_key()
    if not key and sys.stdin.isatty():
        key = input("Hackatime API key (from {}/my/settings): ".format(
            dashboard_url())).strip()
    if key:
        write_settings(api_key=key, api_url=api_url())
        print("Saved API key to {}".format(CONFIG_FILE))
    else:
        print("No API key yet. IDLE will ask for it on start.")

    print("Done. Restart IDLE with: {} -m idlelib".format(sys.executable))


def uninstall(argv):
    target = os.path.join(install_dir(), "IdleHackatime.py")
    if os.path.exists(target):
        os.remove(target)
        print("Removed {}".format(target))
    parser = read_idle_config()
    if parser.remove_section(EXTENSION_NAME):
        write_idle_config(parser)
        print("Disabled the extension in {}".format(IDLE_CONFIG_FILE))


def main(argv):
    commands = {"install": install, "uninstall": uninstall}
    if len(argv) < 2 or argv[1] not in commands:
        print("usage: {} {{install,uninstall}}".format(os.path.basename(argv[0])))
        return 2
    commands[argv[1]](argv)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
