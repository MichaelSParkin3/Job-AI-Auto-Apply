import os
import sys
import threading
import time

import uvicorn

# Ensure repository root is on sys.path for module imports
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from apps.preview.main import create_app


def main() -> None:
    app = create_app()
    server_config = uvicorn.Config(app, host="127.0.0.1", port=8787, log_level="warning")
    server = uvicorn.Server(server_config)

    def run_server() -> None:
        server.run()

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()

    # Wait briefly for the server to start
    for _ in range(50):
        started = getattr(server, "started", None)
        if hasattr(started, "is_set") and started.is_set():
            break
        time.sleep(0.1)

    print("SERVER_STARTED", flush=True)

    try:
        time.sleep(8)
    finally:
        server.should_exit = True
        thread.join(timeout=3)
        print("SERVER_STOPPED", flush=True)


if __name__ == "__main__":
    main()
