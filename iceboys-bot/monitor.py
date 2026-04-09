import os, time, sqlite3
from web3 import Web3

W3 = Web3(Web3.HTTPProvider(os.getenv('ALCHEMY_API_URL')))
TREASURY = os.getenv('TREASURY_WALLET_ADDR')

def check_blockchain():
    # Logic to scan latest block for transactions to TREASURY
    # If tx['value'] matches a TIER price:
    # 1. Update 'users' table (expiry_date = today + tier_days)
    # 2. If referrer_id exists, add +2 days to them
    # 3. bot.send_message(user_id, "Access Granted!")
    pass

while True:
    try:
        check_blockchain()
    except Exception as e:
        print(f"Error: {e}")
    time.sleep(30)
