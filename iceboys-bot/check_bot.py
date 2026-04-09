#!/usr/bin/env python3
import os
import sys
import importlib.util

# ==============================
# CONFIG: Required files & modules
# ==============================
required_files = [
    ".env",
    "main.py",
    "iceboys_monetizer.py",
    "requirements.txt",
    "render.yaml",
    "Dockerfile",
    "bot",
    "contracts",
    "scripts",
]

# Optional: modules from requirements.txt
required_modules = [
    "sqlalchemy",
    "psycopg2",
    "requests",
    "telegram",
    "web3",
    "apscheduler",
    "aiohttp",
    "python_dotenv",
]

# ==============================
# FUNCTIONS
# ==============================
def check_files():
    print("\n🔹 Checking project files...")
    missing_files = []
    for f in required_files:
        if not os.path.exists(f):
            missing_files.append(f)
    if missing_files:
        print("❌ Missing files/directories:", ", ".join(missing_files))
    else:
        print("✅ All required files/directories exist.")

def check_env():
    print("\n🔹 Checking .env file...")
    if os.path.exists(".env"):
        print("✅ .env file found.")
    else:
        print("❌ .env file missing! Make sure to create it with all required keys.")

def check_modules():
    print("\n🔹 Checking Python modules...")
    missing_modules = []
    for module in required_modules:
        if importlib.util.find_spec(module) is None:
            missing_modules.append(module)
    if missing_modules:
        print("❌ Missing Python modules:", ", ".join(missing_modules))
        print("💡 Run: pip install -r requirements.txt")
    else:
        print("✅ All required Python modules are installed.")

# ==============================
# MAIN
# ==============================
if __name__ == "__main__":
    print("\n=== ICEBOYS-bot Environment Check ===")
    check_files()
    check_env()
    check_modules()
    print("\n✅ Check complete!\n")
