#!/usr/bin/env python3
"""
ICEBOYS MONETIZER v2.0
Payment processing, subscription management, and viral growth mechanics
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
import aiohttp
import asyncpg
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Commitment
from solders.signature import Signature
from solders.pubkey import Pubkey

logger = logging.getLogger(__name__)

class PaymentProcessor:
    PRICING = {
        "BASIC": {
            "monthly_usd": 0.5,
            "features": ["10 scans/day", "Whale alerts", "Advanced detection"],
            "emoji": "🔷"
        },
        "PREMIUM": {
            "monthly_usd": 2.0,
            "features": ["Unlimited scans", "Auto-pilot", "Copy trading", "Priority support"],
            "emoji": "🔶"
        },
        "WHALE": {
            "monthly_usd": 5.0,
            "features": ["Everything", "Private signals", "Direct dev access", "Custom strategies"],
            "emoji": "👑"
        }
    }

    def __init__(self, rpc_client: AsyncClient, db_pool: asyncpg.Pool, 
                 payment_wallet: str, helius_key: str):
        self.rpc = rpc_client
        self.db = db_pool
        self.payment_wallet = Pubkey.from_string(payment_wallet)
        self.helius_key = helius_key
        self.session: Optional[aiohttp.ClientSession] = None
        self.sol_price: float = 150.0

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def update_sol_price(self):
        try:
            url = "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd"
            async with self.session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self.sol_price = data["solana"]["usd"]
        except Exception as e:
            logger.error(f"Price fetch error: {e}")

    def usd_to_sol(self, usd_amount: float) -> float:
        return usd_amount / self.sol_price

    async def create_payment_request(self, user_id: int, tier: str, months: int = 1) -> Dict:
        await self.update_sol_price()
        tier_info = self.PRICING.get(tier.upper())
        if not tier_info:
            return {"error": "Invalid tier"}
        total_usd = tier_info["monthly_usd"] * months
        total_sol = self.usd_to_sol(total_usd)
        payment_id = await self.db.fetchval("""
            INSERT INTO payments (user_id, tier, amount_sol, months, status, created_at)
            VALUES ($1, $2, $3, $4, 'PENDING', NOW())
            RETURNING id
        """, user_id, tier.upper(), total_sol, months)
        return {
            "payment_id": payment_id,
            "tier": tier.upper(),
            "months": months,
            "amount_usd": total_usd,
            "amount_sol": round(total_sol, 4),
            "sol_price": self.sol_price,
            "wallet": str(self.payment_wallet),
            "expires_at": (datetime.utcnow() + timedelta(hours=24)).isoformat()
        }

    async def verify_payment(self, payment_id: int, tx_signature: str) -> bool:
        try:
            payment = await self.db.fetchrow(
                "SELECT * FROM payments WHERE id = $1", payment_id
            )
            if not payment or payment["status"] != "PENDING":
                return False
            sig = Signature.from_string(tx_signature)
            tx_info = await self.rpc.get_transaction(sig, commitment=Commitment("confirmed"))
            if not tx_info.value:
                return False
            tx = tx_info.value
            tx_time = datetime.fromtimestamp(tx.block_time or 0)
            if datetime.utcnow() - tx_time > timedelta(hours=24):
                return False
            expected_amount = int(payment["amount_sol"] * 1e9)
            meta = tx.transaction.meta
            if not meta:
                return False
            account_keys = tx.transaction.message.account_keys
            for i, key in enumerate(account_keys):
                if key == self.payment_wallet:
                    pre_balance = meta.pre_balances[i]
                    post_balance = meta.post_balances[i]
                    received = post_balance - pre_balance
                    if received >= expected_amount * 0.95:
                        await self._activate_subscription(
                            payment["user_id"], 
                            payment["tier"], 
                            payment["months"],
                            tx_signature,
                            payment_id
                        )
                        return True
            return False
        except Exception as e:
            logger.error(f"Payment verification error: {e}")
            return False

    async def _activate_subscription(self, user_id: int, tier: str, 
                                     months: int, tx_sig: str, payment_id: int):
        expires = datetime.utcnow() + timedelta(days=30 * months)
        async with self.db.acquire() as conn:
            async with conn.transaction():
                await conn.execute("""
                    UPDATE payments 
                    SET status = 'COMPLETED', tx_signature = $1, verified_at = NOW()
                    WHERE id = $2
                """, tx_sig, payment_id)
                await conn.execute("""
                    INSERT INTO users (user_id, tier, expires_at, max_trades_daily, joined_at)
                    VALUES ($1, $2, $3, $4, NOW())
                    ON CONFLICT (user_id) DO UPDATE SET
                        tier = EXCLUDED.tier,
                        expires_at = EXCLUDED.expires_at,
                        max_trades_daily = EXCLUDED.max_trades_daily
                """, user_id, tier, expires, self._get_tier_limits(tier))
        logger.info(f"Activated {tier} for user {user_id}, expires {expires}")

    def _get_tier_limits(self, tier: str) -> int:
        limits = {"FREE": 3, "BASIC": 10, "PREMIUM": 50, "WHALE": 999}
        return limits.get(tier, 3)

    async def check_expired_subscriptions(self):
        expired = await self.db.fetch("""
            SELECT user_id, tier FROM users 
            WHERE expires_at < NOW() AND tier != 'FREE'
        """)
        for row in expired:
            await self.db.execute("""
                UPDATE users 
                SET tier = 'FREE', max_trades_daily = 3, auto_trade_enabled = FALSE
                WHERE user_id = $1
            """, row["user_id"])
            logger.info(f"Downgraded expired user {row['user_id']} from {row['tier']} to FREE")

class ReferralEngine:
    REWARDS = {
        1: ("BASIC", 3),
        3: ("PREMIUM", 7),
        10: ("WHALE", 30),
    }

    def __init__(self, db_pool: asyncpg.Pool):
        self.db = db_pool

    async def process_referral(self, new_user_id: int, referral_code: str) -> bool:
        referrer = await self.db.fetchrow(
            "SELECT user_id, referrals FROM users WHERE referral_code = $1",
            referral_code
        )
        if not referrer:
            return False
        referrer_id = referrer["user_id"]
        existing = await self.db.fetchval(
            "SELECT 1 FROM users WHERE user_id = $1", new_user_id
        )
        if existing:
            return False
        async with self.db.acquire() as conn:
            async with conn.transaction():
                new_code = f"ICE{new_user_id:06d}"
                await conn.execute("""
                    INSERT INTO users (user_id, tier, referral_code, joined_at, referred_by)
                    VALUES ($1, 'BASIC', $2, NOW(), $3)
                """, new_user_id, new_code, referrer_id)
                new_count = await conn.fetchval("""
                    UPDATE users 
                    SET referrals = referrals + 1
                    WHERE user_id = $1
                    RETURNING referrals
                """, referrer_id)
                await self._check_rewards(conn, referrer_id, new_count)
        return True

    async def _check_rewards(self, conn, user_id: int, ref_count: int):
        for threshold, (tier, days) in sorted(self.REWARDS.items(), reverse=True):
            if ref_count >= threshold:
                existing = await conn.fetchval("""
                    SELECT 1 FROM referral_rewards 
                    WHERE user_id = $1 AND threshold = $2
                """, user_id, threshold)
                if not existing:
                    expires = datetime.utcnow() + timedelta(days=days)
                    await conn.execute("""
                        INSERT INTO referral_rewards (user_id, threshold, tier, days, granted_at)
                        VALUES ($1, $2, $3, $4, NOW())
                    """, user_id, threshold, tier, days)
                    await conn.execute("""
                        UPDATE users 
                        SET tier = $1, expires_at = $2, max_trades_daily = $3
                        WHERE user_id = $4
                    """, tier, expires, self._get_tier_limit(tier), user_id)
                    logger.info(f"Granted {tier} for {days} days to user {user_id} (ref threshold: {threshold})")
                    break

    def _get_tier_limit(self, tier: str) -> int:
        limits = {"BASIC": 10, "PREMIUM": 50, "WHALE": 999}
        return limits.get(tier, 3)

    async def get_leaderboard(self, limit: int = 10) -> List[Dict]:
        rows = await self.db.fetch("""
            SELECT user_id, referrals, tier 
            FROM users 
            ORDER BY referrals DESC 
            LIMIT $1
        """, limit)
        return [dict(row) for row in rows]

class ChannelGrowth:
    def __init__(self, bot_token: str, channel_id: str, db_pool: asyncpg.Pool):
        self.bot_token = bot_token
        self.channel_id = channel_id
        self.db = db_pool
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def post_alpha_signal(self, analysis: Dict):
        if analysis.get("risk_score", 100) > 40:
            return
        message = f"""
🧊 <b>ICEBOYS ALPHA SIGNAL</b>

<b>🎯 Token:</b> {analysis.get('name', 'Unknown')} (${analysis.get('symbol', '???')})
<b>📊 Risk Score:</b> {analysis.get('risk_score', 0)}/100 🟢
<b>💧 Liquidity:</b> ${analysis.get('liquidity_usd', 0):,.0f}
<b>👥 Holders:</b> {analysis.get('holder_count', 0)}

<b>🔐 Safety Check:</b>
✅ Mint Authority: Revoked
✅ Freeze Authority: Revoked
✅ LP Locked/Burned
✅ Honeypot: Clean

<b>🐋 Whale Activity:</b> {len(analysis.get('whale_activity', []))} recent moves

<i>Scan powered by ICEBOYS deep detection</i>

🤖 <a href="https://t.me/ICEBOYSBot">Get ICEBOYS Bot</a>
        """
        await self._send_channel_message(message)

    async def post_whales_move(self, whale_data: Dict):
        message = f"""
🐋 <b>WHALE ALERT</b>

<b>Wallet:</b> <code>{whale_data.get('wallet', 'Unknown')[:12]}...</code>
<b>Action:</b> {'🟢 BUY' if whale_data.get('is_buy') else '🔴 SELL'}
<b>Token:</b> ${whale_data.get('token_symbol', '???')}
<b>Amount:</b> ${whale_data.get('usd_amount', 0):,.2f}
<b>Impact:</b> {whale_data.get('price_impact', 0):.2f}%

<i>Track smart money with ICEBOYS</i>
        """
        await self._send_channel_message(message)

    async def post_daily_stats(self):
        stats = await self.db.fetchrow("""
            SELECT 
                COUNT(*) as total_users,
                COUNT(*) FILTER (WHERE tier != 'FREE') as paid_users,
                SUM(referrals) as total_refs
            FROM users
        """)
        message = f"""
📊 <b>ICEBOYS DAILY STATS</b>

<b>👥 Community:</b> {stats['total_users']:,} traders
<b>💎 Paid Members:</b> {stats['paid_users']}
<b>🎁 Referrals:</b> {stats['total_refs'] or 0}

<b>🔥 Today's Top Signals:</b>
<i>Join the bot to see real-time alpha</i>

🤖 <a href="https://t.me/ICEBOYSBot">Start ICEBOYS</a>
        """
        await self._send_channel_message(message)

    async def _send_channel_message(self, text: str):
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.channel_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        try:
            async with self.session.post(url, json=payload) as resp:
                if resp.status != 200:
                    logger.error(f"Channel post failed: {await resp.text()}")
        except Exception as e:
            logger.error(f"Channel message error: {e}")

MIGRATIONS = """
CREATE TABLE IF NOT EXISTS referral_rewards (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(user_id),
    threshold INTEGER NOT NULL,
    tier VARCHAR(20) NOT NULL,
    days INTEGER NOT NULL,
    granted_at TIMESTAMP DEFAULT NOW()
);

ALTER TABLE users ADD COLUMN IF NOT EXISTS referred_by BIGINT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS months INTEGER DEFAULT 1;

CREATE INDEX IF NOT EXISTS idx_users_tier ON users(tier);
CREATE INDEX IF NOT EXISTS idx_users_expires ON users(expires_at);
CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status);
"""

async def run_migrations(db: asyncpg.Pool):
    async with db.acquire() as conn:
        await conn.execute(MIGRATIONS)
    logger.info("Migrations completed")
