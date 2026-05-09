from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OUT_LOG = ROOT / "_local_server.out.log"
ERR_LOG = ROOT / "_local_server.err.log"


def main() -> int:
    out = OUT_LOG.open("ab", buffering=0)
    err = ERR_LOG.open("ab", buffering=0)
    creationflags = 0

    proc = subprocess.Popen(
        [sys.executable, "local_server.py"],
        cwd=ROOT,
        stdout=out,
        stderr=err,
        stdin=subprocess.DEVNULL,
        creationflags=creationflags,
    )
    print(proc.pid)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
