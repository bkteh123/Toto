"""Run the whole Royal Yellow Analyzer stack on this machine without Docker.

    python -I scripts/run_local.py [--no-browser] [--api-port 8000] [--web-port 5173]

Starts, in order: an embedded PostgreSQL 16, the Alembic migrations, the seed history
(idempotent), the FastAPI backend (uvicorn) and the Vite dev server. Ctrl+C (or closing the
window) stops everything. Database files and logs live in %LOCALAPPDATA%\\RoyalYellow, outside
OneDrive, so your data survives restarts. Use run.cmd / run.ps1 at the project root to also
create the virtualenv and install dependencies on first use.

PostgreSQL is driven with `pg_ctl` from the `pgserver` wheel rather than through pgserver's own
server manager: that manager writes the server log inside the data directory and gives
`pg_ctl` a 10 s timeout, so after a hard kill (crash recovery fsyncs the held log file, which
is a sharing violation on Windows) the next start failed and left an orphan server running.
"""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
SEED_CSV = ROOT / "seed" / "mega645.csv"
HOME = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "share") / "RoyalYellow"
PG_DIR = HOME / "pgdata"
LOG_DIR = HOME / "logs"
PG_PREFERRED_PORT = 54329


def say(msg: str) -> None:
    print(f"[royal-yellow] {msg}", flush=True)


def die(msg: str) -> None:
    print(f"[royal-yellow] ERROR: {msg}", file=sys.stderr, flush=True)
    raise SystemExit(1)


def port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def tail(path: Path, n: int = 25) -> str:
    try:
        return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-n:])
    except OSError:
        return ""


def wait_http(url: str, proc: subprocess.Popen, log: Path, timeout: float = 90) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            die(f"process exited with code {proc.returncode} before {url} came up. Log: {log}\n{tail(log)}")
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status < 500:
                    return
        except Exception:
            time.sleep(0.5)
    die(f"{url} did not respond within {timeout:.0f}s. Log: {log}\n{tail(log)}")


def run_step(label: str, cmd: list[str], env: dict[str, str], cwd: Path, log: Path, fatal: bool = True) -> bool:
    say(label)
    with log.open("ab") as f:
        rc = subprocess.run(cmd, cwd=cwd, env=env, stdout=f, stderr=subprocess.STDOUT).returncode
    if rc != 0:
        msg = f"'{label}' failed (exit {rc}). Log: {log}\n{tail(log)}"
        if fatal:
            die(msg)
        say("WARNING: " + msg)
    return rc == 0


def kill_tree(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    if os.name == "nt":  # npm.cmd spawns node; terminate the whole tree
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
    else:
        proc.terminate()


class Postgres:
    """A PostgreSQL server in a persistent data directory, managed with pg_ctl."""

    def __init__(self, data: Path, log: Path) -> None:
        import pgserver  # only for its bundled PostgreSQL binaries

        self.bin = Path(pgserver.__file__).resolve().parent / "pginstall" / "bin"
        self.data = data
        self.log = log
        self.ctl_log = log.with_name("pg_ctl.log")

    def _exe(self, name: str) -> str:
        return str(self.bin / (name + (".exe" if os.name == "nt" else "")))

    def _run(self, name: str, *args: str, timeout: float) -> int:
        with self.ctl_log.open("ab") as f:  # a file, not a pipe: the server inherits the handles
            return subprocess.run(
                [self._exe(name), *args], stdout=f, stderr=subprocess.STDOUT, timeout=timeout
            ).returncode

    def is_running(self) -> bool:
        return self._run("pg_ctl", "status", "-D", str(self.data), timeout=30) == 0

    def port(self) -> int:
        lines = (self.data / "postmaster.pid").read_text().splitlines()
        return int(lines[3])  # postmaster.pid: pid, datadir, start time, port, ...

    def start(self) -> int:
        if not (self.data / "PG_VERSION").exists():
            say("initialising a new database cluster")
            rc = self._run(
                "initdb", "--auth=trust", "--auth-local=trust", "--encoding=utf8",
                "-U", "postgres", "-D", str(self.data), timeout=300,
            )
            if rc != 0:
                die(f"initdb failed (exit {rc}). Log: {self.ctl_log}\n{tail(self.ctl_log)}")
        if self.is_running():
            say("PostgreSQL is already running from an earlier launch; reusing it")
            return self.port()
        port = PG_PREFERRED_PORT if port_free(PG_PREFERRED_PORT) else _ephemeral_port()
        # Crash recovery after a hard kill can take a while; the log lives outside PGDATA.
        rc = self._run(
            "pg_ctl", "start", "-D", str(self.data), "-w", "-t", "180",
            "-o", f"-h 127.0.0.1 -p {port}", "-l", str(self.log), timeout=240,
        )
        if rc != 0:
            die(f"PostgreSQL failed to start (exit {rc}). Log: {self.log}\n{tail(self.log)}")
        return port

    def stop(self) -> None:
        self._run("pg_ctl", "stop", "-D", str(self.data), "-m", "fast", "-w", "-t", "60", timeout=90)


def _ephemeral_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Cleanup:
    """Idempotent teardown, callable from `finally`, a signal handler or a console-close event."""

    def __init__(self) -> None:
        self.children: list[subprocess.Popen] = []
        self.pg: Postgres | None = None
        self._lock = threading.Lock()
        self._done = False

    def __call__(self) -> None:
        with self._lock:
            if self._done:
                return
            self._done = True
            for p in reversed(self.children):
                kill_tree(p)
            if self.pg is not None:
                try:
                    self.pg.stop()
                except Exception as exc:  # noqa: BLE001 - best effort on shutdown
                    say(f"note: PostgreSQL stop reported: {exc}")


def install_shutdown_hooks(cleanup: Cleanup) -> None:
    def to_keyboard_interrupt(*_: object) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, to_keyboard_interrupt)
    if os.name != "nt":
        return
    signal.signal(signal.SIGBREAK, to_keyboard_interrupt)
    # Closing the console window / logging off does not raise a Python signal; Windows gives
    # the process a few seconds to run this handler and then terminates it.
    import ctypes

    handler_type = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_uint)

    def on_console_event(event: int) -> int:
        if event in (2, 5, 6):  # CTRL_CLOSE_EVENT, CTRL_LOGOFF_EVENT, CTRL_SHUTDOWN_EVENT
            cleanup()
        return 0  # fall through to the default handling

    global _KEEP_ALIVE
    _KEEP_ALIVE = handler_type(on_console_event)  # must outlive the call
    ctypes.windll.kernel32.SetConsoleCtrlHandler(_KEEP_ALIVE, True)


_KEEP_ALIVE = None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--api-port", type=int, default=8000)
    ap.add_argument("--web-port", type=int, default=5173)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    if args.api_port != 8000:
        die("the Vite dev proxy in frontend/vite.config.ts points at port 8000; keep --api-port 8000")
    for port in (args.api_port, args.web_port):
        if not port_free(port):
            die(f"port {port} is already in use. Close the program using it (or an earlier run) and retry.")

    try:
        import pgserver  # noqa: F401
    except ImportError:
        die("pgserver is not installed in this Python. Run run.cmd (it sets up the virtualenv) "
            "or: pip install -r backend/requirements-dev.txt")
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if not npm:
        die("npm was not found on PATH. Install Node.js 20+ (winget install OpenJS.NodeJS.LTS) and reopen the terminal.")
    if not (FRONTEND / "node_modules").is_dir():
        die("frontend/node_modules is missing. Run run.cmd, or: npm ci --prefix frontend")

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    PG_DIR.parent.mkdir(parents=True, exist_ok=True)
    for old in LOG_DIR.glob("*.log"):
        try:
            old.unlink()
        except OSError:  # held open by a server left over from an earlier launch
            pass

    cleanup = Cleanup()
    install_shutdown_hooks(cleanup)
    try:
        say(f"starting PostgreSQL (data: {PG_DIR})")
        pg = Postgres(PG_DIR, LOG_DIR / "postgres.log")
        cleanup.pg = pg
        pg_port = pg.start()
        db_url = f"postgresql+psycopg://postgres@127.0.0.1:{pg_port}/postgres"

        env = os.environ.copy()
        env.update(
            DATABASE_URL=db_url,
            COLLECTOR_CACHE_DIR=str(HOME / "collector_cache"),
            PYTHONDONTWRITEBYTECODE="1",
            PYTHONIOENCODING="utf-8",
            # The backend commands run without -I (isolated mode ignores PYTHONPATH); backend/
            # is their working directory and is also put on PYTHONPATH so `app` always imports.
            PYTHONPATH=str(BACKEND),
        )
        py = sys.executable

        run_step("applying database migrations", [py, "-m", "alembic", "upgrade", "head"], env, BACKEND,
                 LOG_DIR / "migrate.log")
        if SEED_CSV.is_file():
            run_step(
                "loading seed history (idempotent)",
                [py, "-m", "app.seed", "--csv", str(SEED_CSV), "--game", "vn_mega_645", "--first-draw-no", "1453"],
                env, BACKEND, LOG_DIR / "seed.log", fatal=False,
            )

        api_log = LOG_DIR / "backend.log"
        say(f"starting backend on http://127.0.0.1:{args.api_port}")
        with api_log.open("ab") as f:
            api = subprocess.Popen(
                [py, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(args.api_port)],
                cwd=BACKEND, env=env, stdout=f, stderr=subprocess.STDOUT,
            )
        cleanup.children.append(api)
        wait_http(f"http://127.0.0.1:{args.api_port}/health", api, api_log)

        web_log = LOG_DIR / "frontend.log"
        say(f"starting frontend on http://127.0.0.1:{args.web_port}")
        with web_log.open("ab") as f:
            web = subprocess.Popen(
                [npm, "run", "dev", "--", "--host", "127.0.0.1", "--port", str(args.web_port), "--strictPort"],
                cwd=FRONTEND, env=env, stdout=f, stderr=subprocess.STDOUT,
            )
        cleanup.children.append(web)
        url = f"http://127.0.0.1:{args.web_port}"
        wait_http(url, web, web_log)

        say("")
        say(f"Royal Yellow Analyzer is running:  {url}")
        say(f"API docs:                          http://127.0.0.1:{args.api_port}/docs")
        say(f"Database:                          {db_url}")
        say(f"Logs:                              {LOG_DIR}")
        say("Press Ctrl+C to stop.")
        if not args.no_browser:
            webbrowser.open(url)

        while True:
            for p, name in ((api, "backend"), (web, "frontend")):
                if p.poll() is not None:
                    die(f"the {name} stopped unexpectedly (exit {p.returncode}). See {LOG_DIR}")
            time.sleep(1)
    except KeyboardInterrupt:
        say("stopping...")
        return 0
    finally:
        cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
