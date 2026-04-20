from __future__ import annotations

import runpy
import sys
from pathlib import Path


TARGET = Path(__file__).resolve().parent / "history" / "tooling" / "campaigns" / "run_t25_2_installation_recovery.py"


def main() -> int:
    print(
        f"[historical-tooling] Redirecting to {TARGET.relative_to(Path(__file__).resolve().parent)}",
        file=sys.stderr,
    )
    runpy.run_path(str(TARGET), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
