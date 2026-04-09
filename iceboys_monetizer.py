import os
import sqlite3
import telebot
from telebot import types
from datetime import datetime

# --- CONFIG ---
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TREASURY = os.getenv('TREASURY_WALLET_ADDR')
bot = telebot.TeleBot(TOKEN)

# Pricing Tiers
TIERS = {
    "trial": {"days": 7, "price": 0.003, "label": "Trial (7 Days)"},
    "premium": {"days": 30, "price": 0.01, "label": "VIP (30 Days)"}
}

def init_db():
    conn = sqlite3.connect('subscriptions.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY, expiry_date TEXT, referrer_id INTEGER)''')
    conn.commit()
    conn.close()

@bot.message_handler(commands=['start'])
def start(message):
    init_db()
    user_id = message.from_user.id
    args = message.text.split()
    # Captures referral ID from link: t.me/bot?start=12345
    referrer = args[1] if len(args) > 1 and args[1].isdigit() else None

    with sqlite3.connect('subscriptions.db') as conn:
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO users (user_id, referrer_id) VALUES (?, ?)", (user_id, referrer))
        conn.commit()

    markup = types.InlineKeyboardMarkup(row_width=1)
    for key, val in TIERS.items():
        markup.add(types.InlineKeyboardButton(f"🚀 {val['label']} - {val['price']} ETH", callback_data=f"buy_{key}"))
    markup.add(types.InlineKeyboardButton("👥 My Referral Link", callback_data="my_ref"))

    welcome = (
        "🧊 *ICEBOYS ALPHA ACCESS*\n\n"
        "We track the whale moves so you don't have to. Choose a plan to unlock the private feed."
    )
    bot.send_message(message.chat.id, welcome, parse_mode='Markdown', reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('buy_'))
def handle_buy(call):
    tier_key = call.data.split('_')[1]
    tier = TIERS[tier_key]
    instructions = (
        f"✅ *Plan:* {tier['label']}\n"
        f"💰 *Send Exactly:* `{tier['price']} ETH`\n"
        f"📍 *Treasury:* `{TREASURY}`\n\n"
        "⚡ *Automatic Verification:* Our system monitors the blockchain. You will receive an invite link here once confirmed."
    )
    bot.edit_message_text(instructions, call.message.chat.id, call.message.message_id, parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: call.data == "my_ref")
def show_ref(call):
    link = f"https://t.me{bot.get_me().username}?start={call.from_user.id}"
    bot.send_message(call.message.chat.id, f"🔗 *Your Referral Link:*\n`{link}`\n\nInvite others. If they subscribe, you get *+2 bonus days*!")

bot.polling(none_stop=True)
