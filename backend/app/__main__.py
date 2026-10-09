"""`python -m app` — start the server (without access logging, see app.main)."""

import argparse

import uvicorn

from app.config import BACKEND_ROOT


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the personal medical records server")
    parser.add_argument("--host", default="127.0.0.1", help="interface to listen on (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="port (default: 8000)")
    parser.add_argument("--reload", action="store_true", help="restart on code changes (development)")
    args = parser.parse_args()
    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        reload_dirs=[str(BACKEND_ROOT / "app")] if args.reload else None,
        access_log=False,
        proxy_headers=True,
    )


if __name__ == "__main__":
    main()
