import sqlite3

def init():
    conn = sqlite3.connect('iceboys.db')
    c = conn.cursor()
    # Users table: tracks status and referrals
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (user_id INTEGER PRIMARY KEY, 
                  expiry_date TEXT, 
                  referrer_id INTEGER)''')
    # Payments table: prevents duplicate processing of the same transaction
    c.execute('''CREATE TABLE IF NOT EXISTS payments 
                 (tx_hash TEXT PRIMARY KEY, 
                  user_id INTEGER, 
                  amount REAL)''')
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init()
    print("Database 'iceboys.db' initialized.")
