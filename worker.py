"""
Run the Django Q worker with proper shutdown on all platforms.

Usage:
    python worker.py

Ctrl+C will:
  1. Kill the qcluster process tree
  2. Mark any interrupted runs as FAILED
"""
import os
import signal
import subprocess
import sys
from pathlib import Path

MANAGE = Path(__file__).parent / 'webserver' / 'manage.py'


def main():
    # On Windows, isolate qcluster in its own process group so Ctrl+C
    # only reaches this script — not qcluster's children.
    kwargs = {}
    if sys.platform == 'win32':
        kwargs['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP

    proc = subprocess.Popen([sys.executable, str(MANAGE), 'qcluster'], **kwargs)

    def shutdown(signum, frame):
        print('\n[worker] shutting down...', flush=True)
        if sys.platform == 'win32':
            subprocess.run(
                ['taskkill', '/F', '/T', '/PID', str(proc.pid)],
                capture_output=True,
            )
        else:
            proc.terminate()
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()

        subprocess.run([sys.executable, str(MANAGE), 'reset_stuck_runs'])
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    if hasattr(signal, 'SIGTERM'):
        signal.signal(signal.SIGTERM, shutdown)

    proc.wait()


if __name__ == '__main__':
    main()
