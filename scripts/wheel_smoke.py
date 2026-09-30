"""Verify a wheel contains every application module without importing from the checkout."""

import json
import os
import site
import subprocess
import sys
import tempfile
import venv
from pathlib import Path


def main():
    wheel = Path(sys.argv[1]).resolve()
    # Reuse already-installed third-party dependencies; app itself must come from the wheel.
    workspace = Path("reports").resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="wheel-", dir=workspace) as temporary:
        root = Path(temporary)
        venv.EnvBuilder(with_pip=True).create(root / "venv")
        python = root / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        subprocess.run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--no-cache-dir",
                "--no-index",
                "--no-deps",
                str(wheel),
            ],
            check=True,
            cwd=root,
        )
        probe = """
from pathlib import Path
import inspect
import json
import sys
# Append dependency directories without executing the checkout's editable .pth hooks.
sys.path.extend(json.loads(sys.argv[1]))
from app.main import app
from app.algorithms.distance import haversine_km
from app.routes.dispatch import match_order
import app as package
assert Path(package.__file__).is_relative_to(Path(sys.prefix)), package.__file__
for target in (haversine_km, match_order):
    assert Path(inspect.getfile(target)).is_relative_to(Path(sys.prefix)), inspect.getfile(target)
assert '/dispatch/match' in app.openapi()['paths']
assert haversine_km(0,0,0,0) == 0
print('Wheel import smoke passed:', package.__file__)
"""
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        subprocess.run(
            [str(python), "-I", "-c", probe, json.dumps(site.getsitepackages())],
            check=True,
            cwd=root,
            env=environment,
        )


if __name__ == "__main__":
    main()
