import os, telebot, threading, sqlite3
from flask import Flask
from telebot import types
from web3 import Web3

# --- CONFIG ---
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TREASURY = os.getenv('TREASURY_WALLET_ADDR')
ALCHEMY_URL = os.getenv('ALCHEMY_API_URL')
PORT = int(os.getenv('PORT', 5000))

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# --- UPTIME ROBOT HEALTH CHECK ---
@app.route('/health')
def health_check():
    return "ICEBOYS_ACTIVE", 200

def run_web_server():
    app.run(host='0.0.0.0', port=PORT)

# --- BOT LOGIC ---
@bot.message_handler(commands=['start'])
def start(message):
    # Verify Alchemy connection on first interaction
    w3 = Web3(Web3.HTTPProvider(ALCHEMY_URL))
    status = "✅ System Online" if w3.is_connected() else "⚠️ Node Error"
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("🚀 VIP Access - 0.01 ETH", callback_data="buy_premium"))
    
    bot.reply_to(message, f"🧊 *ICEBOYS ALPHA*\nStatus: {status}\n\nSelect a plan to begin.", parse_mode='Markdown', reply_markup=markup)

# --- STARTUP ---
if __name__ == "__main__":
    # Start the web server in a separate thread for UptimeRobot
    threading.Thread(target=run_web_server, daemon=True).start()
    print(f"Health check server started on port {PORT}")
    
    # Start the bot
    print("Bot is now polling...")
    bot.polling(none_stop=True)
