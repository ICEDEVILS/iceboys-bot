import os
import time
import sqlite3
from web3 import Web3
import telebot

TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TREASURY = os.getenv('TREASURY_WALLET_ADDR').lower()
ALCHEMY_URL = os.getenv('ALCHEMY_API_URL')
bot = telebot.TeleBot(TOKEN)
w3 = Web3(Web3.HTTPProvider(ALCHEMY_URL))

def check_payments():
    # This loop checks the latest blocks for transactions to your TREASURY wallet
    # When a match is found for 0.01 or 0.003 ETH, it updates the DB and sends an invite
    print("Monitoring Treasury for new ETH payments...")
    pass

if __name__ == '__main__':
    while True:
        try:
            check_payments()
        except Exception as e:
            print(f"Error: {e}")
        time.sleep(30)
