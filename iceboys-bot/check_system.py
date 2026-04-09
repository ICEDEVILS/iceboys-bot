import os, sys
try:
    import telebot
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("❌ telebot is still missing. Run: pip install pyTelegramBotAPI")
    sys.exit(1)

token = os.getenv('TELEGRAM_BOT_TOKEN')
if token:
    try:
        bot = telebot.TeleBot(token)
        me = bot.get_me()
        print(f"✅ Bot Token is LIVE: @{me.username}")
        print("🚀 System ready for GitHub push. Web3 will work once on Render.")
    except Exception as e:
        print(f"❌ Token Error: {e}")
else:
    print("❌ No Token found in .env")
