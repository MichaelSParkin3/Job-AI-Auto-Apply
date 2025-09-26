import os
from apps.cli.main import app

if __name__ == "__main__":
    # Respect optional base dir for runtime artifacts (useful for tests)
    base_dir = os.environ.get("JAA_BASE_DIR")
    if base_dir and not os.path.isdir(base_dir):
        os.makedirs(base_dir, exist_ok=True)
    app()

