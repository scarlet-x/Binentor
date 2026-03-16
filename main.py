# main.py

import sys
from pathlib import Path

# Ensure project root is importable
sys.path.append(str(Path(__file__).resolve().parent))

from scripts.run_bot import main

if __name__ == "__main__":
    main()
