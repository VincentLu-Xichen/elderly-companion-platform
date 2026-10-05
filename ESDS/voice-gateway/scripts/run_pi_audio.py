#!/usr/bin/env python3
"""Start the native Raspberry Pi ALSA client."""

from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_PYTHON = PROJECT_ROOT / ".venv" / "bin" / "python"

if PROJECT_PYTHON.is_file() and Path(sys.executable).resolve() != PROJECT_PYTHON.resolve():
    os.execv(
        str(PROJECT_PYTHON),
        [str(PROJECT_PYTHON), str(Path(__file__).resolve()), *sys.argv[1:]],
    )

SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from esds_voice.pi_audio import main


if __name__ == "__main__":
    main()
