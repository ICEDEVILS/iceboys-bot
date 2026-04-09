#!/usr/bin/env python3
"""
ICEBOYS SYSTEM VERIFICATION SCRIPT
Checks all configurations before deployment to Render
Run this before deploying: python verify.py
"""

import os
import sys
import asyncio
import asyncpg
from solana.rpc.async_api import AsyncClient
from solders.pubkey import Pubkey
from dotenv import load_dotenv

load_dotenv()

class ICEBOYSVerifier:
    def __init__(self):
        self.checks_passed = 0
        self.checks_failed = 0
        self.warnings = []
        
    def check(self, name: str, condition: bool, message: str = ""):
        if condition:
            print(f"✅ {name}")
            self.checks_passed += 1
            return True
        else:
            print(f"❌ {name}")
            if message:
                print(f"   ⚠️  {message}")
            self.checks_failed += 1
            return False
    
    def warn(self, message: str):
        print(f"⚠️  WARNING: {message}")
        self.warnings.append(message)
    
    async def run_all_checks(self):
        print("\n" + "="*60)
        print("🧊 ICEBOYS SYSTEM VERIFICATION")
        print("="*60 + "\n")
        
        # 1. Environment Variables
        print("📋 CHECKING ENVIRONMENT VARIABLES...")
        self.check("BOT_TOKEN set", bool(os.getenv("BOT_TOKEN")))
        self.check("ADMIN_ID set", bool(os.getenv("ADMIN_ID")))
        self.check("CHANNEL_ID set", bool(os.getenv("CHANNEL_ID")))
        self.check("SOLANA_RPC set", bool(os.getenv("SOLANA_RPC")))
        self.check("HELIUS_API_KEY set", bool(os.getenv("HELIUS_API_KEY")))
        self.check("DATABASE_URL set", bool(os.getenv("DATABASE_URL")))
        self.check("PAYMENT_WALLET set", bool(os.getenv("PAYMENT_WALLET")))
        
        # Validate Solana addresses
        payment_wallet = os.getenv("PAYMENT_WALLET", "")
        if payment_wallet:
            try:
                Pubkey.from_string(payment_wallet)
                self.check("PAYMENT_WALLET valid", True)
            except:
                self.check("PAYMENT_WALLET valid", False, "Invalid Solana address format")
        
        print("\n📋 CHECKING TELEGRAM CONFIG...")
        self.check("Admin is Mex Robert (8232197912)", 
                   os.getenv("ADMIN_ID") == "8232197912")
        self.check("Channel is @MexRober (-1003952089014)",
                   os.getenv("CHANNEL_ID") == "-1003952089014")
        
        print("\n📋 CHECKING SOLANA RPC...")
        rpc_url = os.getenv("SOLANA_RPC", "")
        if "helius" in rpc_url.lower():
            self.check("Using Helius RPC", True)
        else:
            self.warn("Not using Helius RPC - some features may not work")
        
        print("\n📋 CHECKING DATABASE...")
        db_url = os.getenv("DATABASE_URL", "")
        if db_url.startswith("postgresql"):
            self.check("Using PostgreSQL", True)
        elif db_url.startswith("sqlite"):
            self.check("Using SQLite", True)
            self.warn("SQLite is for local testing only - use PostgreSQL for Render")
        else:
            self.check("Database URL format", False, "Unknown database type")
        
        # Test database connection
        if db_url:
            try:
                pool = await asyncpg.create_pool(db_url, min_size=1, max_size=2)
                async with pool.acquire() as conn:
                    result = await conn.fetchval("SELECT 1")
                    self.check("Database connection", result == 1)
                await pool.close()
            except Exception as e:
                self.check("Database connection", False, str(e))
        
        print("\n📋 CHECKING FILE STRUCTURE...")
        required_files = [
            "bot/main.py",
            "bot/__init__.py", 
            "bot/trading.py",
            "monitor.py",
            "iceboys_monetizer.py",
            "init_db.py",
            "requirements.txt",
            "render.yaml",
            "Dockerfile"
        ]
        for file in required_files:
            self.check(f"File exists: {file}", os.path.exists(file))
        
        print("\n📋 CHECKING RENDER CONFIG...")
        if os.path.exists("render.yaml"):
            with open("render.yaml", "r") as f:
                content = f.read()
                self.check("Render web service defined", "type: web" in content)
                self.check("Render workers defined", "type: worker" in content)
                self.check("Database defined", "databases:" in content)
        
        print("\n📋 CHECKING WHALE TRACKING CONFIG...")
        tracked_whales = os.getenv("TRACKED_WHALES", "")
        if tracked_whales:
            whale_list = [w.strip() for w in tracked_whales.split(",") if w.strip()]
            self.check(f"Tracking {len(whale_list)} whales", len(whale_list) > 0)
        else:
            self.warn("No whales configured - add TRACKED_WHALES to .env")
        
        print("\n📋 CHECKING MONETIZATION...")
        self.check("Basic price set", bool(os.getenv("SUBSCRIPTION_BASIC_PRICE")))
        self.check("Premium price set", bool(os.getenv("SUBSCRIPTION_PREMIUM_PRICE")))
        self.check("Whale price set", bool(os.getenv("SUBSCRIPTION_WHALE_PRICE")))
        
        # Summary
        print("\n" + "="*60)
        print("📊 VERIFICATION SUMMARY")
        print("="*60)
        print(f"✅ Passed: {self.checks_passed}")
        print(f"❌ Failed: {self.checks_failed}")
        print(f"⚠️  Warnings: {len(self.warnings)}")
        
        if self.checks_failed == 0:
            print("\n🚀 SYSTEM READY FOR RENDER DEPLOYMENT!")
            print("\n📋 RENDER START COMMANDS:")
            print("   Web Service:    python -m bot.main")
            print("   Monitor Worker: python monitor.py")
            print("   Trading Worker: python -m bot.trading")
            print("\n📋 NEXT STEPS:")
            print("1. git add . && git commit -m 'Ready for deployment'")
            print("2. git push origin main")
            print("3. Go to Render Dashboard → New → Blueprint")
            print("4. Connect your GitHub repo")
            print("5. Set environment variables in Render dashboard")
            print("6. Deploy!")
            return True
        else:
            print(f"\n⚠️  FIX {self.checks_failed} ISSUES BEFORE DEPLOYING")
            return False

if __name__ == "__main__":
    verifier = ICEBOYSVerifier()
    result = asyncio.run(verifier.run_all_checks())
    sys.exit(0 if result else 1)
