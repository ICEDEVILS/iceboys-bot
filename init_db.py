#!/usr/bin/env python3
"""
ICEBOYS Database Initialization
Run this to set up all database tables
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def init_all():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("❌ DATABASE_URL not set in environment")
        return
    print("🧊 Initializing ICEBOYS Database...")
    pool = await asyncpg.create_pool(database_url)
    try:
        await pool.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                tier VARCHAR(20) DEFAULT 'FREE',
                expires_at TIMESTAMP,
                trades_today INTEGER DEFAULT 0,
                max_trades_daily INTEGER DEFAULT 3,
                auto_trade_enabled BOOLEAN DEFAULT FALSE,
                profit_target DECIMAL DEFAULT 50.0,
                stop_loss DECIMAL DEFAULT 20.0,
                referral_code VARCHAR(20) UNIQUE,
                referrals INTEGER DEFAULT 0,
                joined_at TIMESTAMP DEFAULT NOW(),
                last_trade_date DATE DEFAULT CURRENT_DATE,
                referred_by BIGINT
            )
        """)
        await pool.execute("""
            CREATE TABLE IF NOT EXISTS positions (
                id SERIAL PRIMARY KEY,
                user_id BIGINT REFERENCES users(user_id),
                mint VARCHAR(50) NOT NULL,
                entry_price DECIMAL NOT NULL,
                amount DECIMAL NOT NULL,
                status VARCHAR(20) DEFAULT 'OPEN',
                auto_sell_enabled BOOLEAN DEFAULT FALSE,
                profit_target DECIMAL DEFAULT 50.0,
                stop_loss DECIMAL DEFAULT 20.0,
                close_reason VARCHAR(50),
                pnl_percent DECIMAL,
                opened_at TIMESTAMP DEFAULT NOW(),
                closed_at TIMESTAMP
            )
        """)
        await pool.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id SERIAL PRIMARY KEY,
                user_id BIGINT REFERENCES users(user_id),
                tier VARCHAR(20) NOT NULL,
                amount_sol DECIMAL NOT NULL,
                tx_signature VARCHAR(100) UNIQUE,
                status VARCHAR(20) DEFAULT 'PENDING',
                created_at TIMESTAMP DEFAULT NOW(),
                verified_at TIMESTAMP
            )
        """)
        await pool.execute("""
            CREATE TABLE IF NOT EXISTS whale_moves (
                id SERIAL PRIMARY KEY,
                wallet VARCHAR(50),
                token_mint VARCHAR(50),
                token_symbol VARCHAR(20),
                is_buy BOOLEAN,
                amount_sol DECIMAL,
                usd_value DECIMAL,
                price_impact DECIMAL,
                tx_signature VARCHAR(100),
                detected_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await pool.execute("""
            CREATE TABLE IF NOT EXISTS tokens_found (
                id SERIAL PRIMARY KEY,
                mint VARCHAR(50) UNIQUE NOT NULL,
                name VARCHAR(100),
                symbol VARCHAR(20),
                platform VARCHAR(20) NOT NULL,
                liquidity_sol DECIMAL,
                liquidity_usd DECIMAL,
                deployer VARCHAR(50),
                tx_signature VARCHAR(100),
                bonding_curve_complete BOOLEAN DEFAULT FALSE,
                market_cap DECIMAL,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await pool.execute("""
            CREATE TABLE IF NOT EXISTS tracked_whales (
                id SERIAL PRIMARY KEY,
                wallet VARCHAR(50) UNIQUE NOT NULL,
                label VARCHAR(100),
                added_by BIGINT,
                added_at TIMESTAMP DEFAULT NOW(),
                active BOOLEAN DEFAULT true,
                success_rate DECIMAL DEFAULT 0,
                total_trades INTEGER DEFAULT 0
            )
        """)
        await pool.execute("""
            CREATE TABLE IF NOT EXISTS alpha_signals (
                id SERIAL PRIMARY KEY,
                mint VARCHAR(50) UNIQUE NOT NULL,
                name VARCHAR(100),
                symbol VARCHAR(20),
                platform VARCHAR(20),
                liquidity_sol DECIMAL,
                liquidity_usd DECIMAL,
                alpha_score DECIMAL,
                detected_at TIMESTAMP DEFAULT NOW(),
                posted_to_channel BOOLEAN DEFAULT false
            )
        """)
        await pool.execute("""
            CREATE TABLE IF NOT EXISTS referral_rewards (
                id SERIAL PRIMARY KEY,
                user_id BIGINT REFERENCES users(user_id),
                threshold INTEGER NOT NULL,
                tier VARCHAR(20) NOT NULL,
                days INTEGER NOT NULL,
                granted_at TIMESTAMP DEFAULT NOW()
            )
        """)
        print("✅ All tables initialized successfully!")
    except Exception as e:
        print(f"❌ Error initializing database: {e}")
        raise
    finally:
        await pool.close()

if __name__ == "__main__":
    asyncio.run(init_all())
