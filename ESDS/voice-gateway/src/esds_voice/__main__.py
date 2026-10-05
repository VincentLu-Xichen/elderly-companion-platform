from __future__ import annotations

import argparse
import asyncio
import logging

from .config import Settings
from .server import serve_forever


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the ESDS voice gateway")
    parser.parse_args()
    settings = Settings.from_env()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        asyncio.run(serve_forever(settings))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
