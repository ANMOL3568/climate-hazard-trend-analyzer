"""Start the API using the project's isolated Python environment."""
import os
from pathlib import Path
import subprocess
import sys


def main():
    backend = Path(__file__).resolve().parent
    environment = backend.parent / '.venv'
    python = environment / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if not python.is_file():
        print('Project environment is missing. From the project root, run:')
        print('  python -m venv .venv')
        print('  .venv\\Scripts\\python.exe -m pip install -r Backend/requirements.txt')
        return 1
    command = [str(python), '-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', '8000', *sys.argv[1:]]
    try:
        return subprocess.call(command, cwd=backend)
    except KeyboardInterrupt:
        return 0


if __name__ == '__main__':
    sys.exit(main())
