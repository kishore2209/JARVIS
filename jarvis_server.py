"""Canonical JARVIS backend launcher."""
import uvicorn

from api import create_app, runtime


def main() -> None:
    uvicorn.run(create_app(), host=runtime.config.host, port=runtime.config.port, log_level=runtime.config.log_level.lower())


if __name__ == "__main__":
    main()
