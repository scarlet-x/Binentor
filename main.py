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
    """Validates that the 'Binentor' has all the required tools to function."""
    required_vars = ["TELEGRAM_TOKEN", "GOOGLE_API_KEY", "ENCRYPTION_KEY"]
    missing = [var for var in required_vars if not os.getenv(var)]
    
    if missing:
        print("❌ CRITICAL ERROR: Missing Environment Variables!")
        print(f"Please define the following in your .env or hosting provider: {', '.join(missing)}")
        sys.exit(1)
    
    # Ensure the encryption key is the correct length for Fernet (32 url-safe base64-encoded bytes)
    # This prevents the bot from crashing mid-execution during the first user signup.
    try:
        from cryptography.fernet import Fernet
        Fernet(os.getenv("ENCRYPTION_KEY").encode())
    except Exception:
        print("❌ CRITICAL ERROR: ENCRYPTION_KEY is invalid. Generate a new one using Fernet.generate_key().")
        sys.exit(1)

# --- 3. THE LAUNCHER ---
def start_engine():
    # Setup basic logging for the entry point
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("ClawLauncher")
    
    logger.info("⚡ Initializing Claw-Mentor Multi-User SaaS Engine...")
    
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
