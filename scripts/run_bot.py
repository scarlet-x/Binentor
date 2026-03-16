import sys
from pathlib import Path

# Allow imports from project root
sys.path.append(str(Path(__file__).resolve().parents[1]))

from binentor.bot.bot import start_bot


def main():
    print("Starting Binentor...")
    start_bot()


if __name__ == "__main__":
    main()
