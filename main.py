import sys
import os
import logging
from pathlib import Path

# --- 1. DYNAMIC PATHING ---
# Ensures that even if you run this from a different folder, the bot knows where it is.
BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))

# --- 2. PRE-FLIGHT CHECKLIST ---
def check_environment():
    """Validates that the bot has all required API tokens to function."""
    # Note: ENCRYPTION_KEY removed as we are using plain-text storage
    required_vars = ["TELEGRAM_TOKEN", "GOOGLE_API_KEY"]
    missing = [var for var in required_vars if not os.getenv(var)]
    
    if missing:
        print("❌ CRITICAL ERROR: Missing Environment Variables!")
        print(f"Please define the following in your .env or hosting provider: {', '.join(missing)}")
        sys.exit(1)

# --- 3. THE LAUNCHER ---
def start_engine():
    # Setup basic logging for the entry point
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("ClawLauncher")
    
    logger.info("⚡ Initializing Binentor Engine (Standard Edition)...")
    
    check_environment()
    
    try:
        # We import here to ensure the environment is checked BEFORE loading heavy libraries
        from scripts.run_bot import main
        logger.info("🚀 All systems nominal. Launching Telegram Polling...")
        main()
    except ImportError as e:
        logger.error(f"Failed to import 'main' from 'scripts.run_bot'. Check your file structure: {e}")
    except KeyboardInterrupt:
        logger.info("👋 Systems powered down gracefully. Happy trading.")
    except Exception as e:
        logger.critical(f"A catastrophic failure occurred: {e}")

if __name__ == "__main__":
    start_engine()
