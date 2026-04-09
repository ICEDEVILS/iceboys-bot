#!/usr/bin/env python3
"""
ICEBOYS SIMPLE CHECKER - Run this before deploying
Verifies .env and file structure without heavy dependencies
"""

import os
import sys

def check_env():
    print("="*60)
    print("🧊 ICEBOYS ENVIRONMENT CHECK")
    print("="*60)
    
    if not os.path.exists('.env'):
        print("❌ .env file not found!")
        return False
    
    env_vars = {}
    with open('.env', 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                env_vars[key] = value
    
    print("\n📋 CHECKING REQUIRED VARIABLES:")
    
    required = {
        'BOT_TOKEN': 'Telegram Bot Token',
        'ADMIN_ID': 'Admin ID',
        'CHANNEL_ID': 'Channel ID',
        'SOLANA_RPC': 'Solana RPC URL',
        'HELIUS_API_KEY': 'Helius API Key',
        'DATABASE_URL': 'Database URL',
        'PAYMENT_WALLET': 'Payment Wallet Address'
    }
    
    all_good = True
    for key, desc in required.items():
        if key in env_vars and env_vars[key]:
            value = env_vars[key]
            if 'TOKEN' in key or 'KEY' in key:
                display = value[:10] + "..." if len(value) > 10 else value
            else:
                display = value
            print(f"✅ {key}: {display}")
        else:
            print(f"❌ {key}: MISSING - {desc}")
            all_good = False
    
    print("\n📋 CHECKING FILE STRUCTURE:")
    required_files = [
        'bot/main.py', 'bot/__init__.py', 'bot/trading.py',
        'monitor.py', 'iceboys_monetizer.py', 'init_db.py',
        'requirements.txt', 'render.yaml', 'Dockerfile', '.env'
    ]
    
    for file in required_files:
        if os.path.exists(file):
            size = os.path.getsize(file)
            print(f"✅ {file} ({size} bytes)")
        else:
            print(f"❌ {file} MISSING")
            all_good = False
    
    print("\n📋 CHECKING TELEGRAM CONFIG:")
    if env_vars.get('ADMIN_ID') == '8232197912':
        print("✅ Admin ID correct (Mex Robert)")
    if env_vars.get('CHANNEL_ID') == '-1003952089014':
        print("✅ Channel ID correct (@MexRober)")
    
    print("\n📋 CHECKING MONETIZATION:")
    print(f"💰 Basic: ${env_vars.get('SUBSCRIPTION_BASIC_PRICE', 'NOT SET')}/month")
    print(f"💰 Premium: ${env_vars.get('SUBSCRIPTION_PREMIUM_PRICE', 'NOT SET')}/month")
    print(f"💰 Whale: ${env_vars.get('SUBSCRIPTION_WHALE_PRICE', 'NOT SET')}/month")
    
    whales = env_vars.get('TRACKED_WHALES', '')
    if whales:
        whale_list = [w.strip() for w in whales.split(',') if w.strip()]
        print(f"\n🐋 Tracking {len(whale_list)} whale wallet(s)")
    
    print("\n" + "="*60)
    if all_good:
        print("🚀 ALL CHECKS PASSED! READY TO DEPLOY!")
        print("\n📋 RENDER START COMMANDS:")
        print("   Web Service:    python -m bot.main")
        print("   Monitor Worker: python monitor.py")  
        print("   Trading Worker: python -m bot.trading")
        print("\n📋 DEPLOY NOW:")
        print("1. git add . && git commit -m 'Production ready'")
        print("2. git push origin main")
        print("3. Go to https://dashboard.render.com/blueprints")
        print("4. Connect GitHub repo and deploy!")
        return True
    else:
        print("❌ FIX ERRORS BEFORE DEPLOYING")
        return False

if __name__ == "__main__":
    success = check_env()
    sys.exit(0 if success else 1)
