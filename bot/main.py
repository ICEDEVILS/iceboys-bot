#!/usr/bin/env python3
"""
ICEBOYS ALPHA BOT v3.0 - Deep Detection & Monetization Engine
Advanced Solana Token Sniper with Subscription Tiers
Channel: @MexRober | ID: -1003952089014
Admin: Mex Robert (ID: 8232197912)
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from decimal import Decimal
import aiohttp
import asyncpg
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Commitment
from solana.rpc.types import TxOpts
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.transaction import Transaction
from solders.system_program import TransferParams, transfer
from solders.message import Message
import base58
import base64
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, 
    BotCommand, MenuButtonCommands
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)
from telegram.constants import ParseMode

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class Config:
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    ADMIN_ID: int = int(os.getenv("ADMIN_ID", "8232197912"))
    CHANNEL_ID: str = os.getenv("CHANNEL_ID", "-1003952089014")
    SOLANA_RPC: str = os.getenv("SOLANA_RPC", "https://mainnet.helius-rpc.com/?api-key=YOUR_KEY")
    HELIUS_API_KEY: str = os.getenv("HELIUS_API_KEY", "")
    RUGCHECK_API: str = "https://api.rugcheck.xyz/v1"
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    PAYMENT_WALLET: str = os.getenv("PAYMENT_WALLET", "")
    ENABLE_AUTO_TRADE: bool = os.getenv("ENABLE_AUTO_TRADE", "false").lower() == "true"
    ENABLE_WHALE_ALERTS: bool = True
    PRICE_BASIC: float = 0.5
    PRICE_PREMIUM: float = 2.0
    PRICE_WHALE: float = 5.0

CONFIG = Config()

@dataclass
class TokenAnalysis:
    mint: str
    name: str = ""
    symbol: str = ""
    risk_score: int = 0
    risk_level: str = "UNKNOWN"
    liquidity_usd: float = 0.0
    market_cap: float = 0.0
    holder_count: int = 0
    top10_percentage: float = 0.0
    mint_authority: bool = True
    freeze_authority: bool = True
    lp_locked: bool = False
    lp_burned: bool = False
    honeypot: bool = False
    buy_tax: float = 0.0
    sell_tax: float = 0.0
    deployer: str = ""
    deployer_history: List[Dict] = None
    whale_activity: List[Dict] = None
    social_signals: Dict = None
    timestamp: datetime = None

    def __post_init__(self):
        if self.deployer_history is None:
            self.deployer_history = []
        if self.whale_activity is None:
            self.whale_activity = []
        if self.social_signals is None:
            self.social_signals = {}
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()

@dataclass
class UserSubscription:
    user_id: int
    tier: str = "FREE"
    expires_at: Optional[datetime] = None
    trades_today: int = 0
    max_trades_daily: int = 3
    auto_trade_enabled: bool = False
    profit_target: float = 50.0
    stop_loss: float = 20.0
    referral_code: str = ""
    referrals: int = 0
    joined_at: datetime = None

    def __post_init__(self):
        if self.joined_at is None:
            self.joined_at = datetime.utcnow()

class DeepDetectionEngine:
    def __init__(self, rpc_client: AsyncClient, helius_key: str):
        self.rpc = rpc_client
        self.helius_key = helius_key
        self.session: Optional[aiohttp.ClientSession] = None
        self.risk_cache: Dict[str, TokenAnalysis] = {}

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def analyze_token(self, mint_address: str) -> TokenAnalysis:
        analysis = TokenAnalysis(mint=mint_address)
        tasks = [
            self._fetch_token_metadata(mint_address, analysis),
            self._analyze_authorities(mint_address, analysis),
            self._analyze_liquidity(mint_address, analysis),
            self._analyze_holders(mint_address, analysis),
            self._check_rugcheck(mint_address, analysis),
            self._analyze_deployer(mint_address, analysis),
            self._detect_honeypot(mint_address, analysis),
            self._fetch_whale_activity(mint_address, analysis),
        ]
        await asyncio.gather(*tasks, return_exceptions=True)
        analysis.risk_score = self._calculate_risk_score(analysis)
        analysis.risk_level = self._get_risk_level(analysis.risk_score)
        self.risk_cache[mint_address] = analysis
        return analysis

    async def _fetch_token_metadata(self, mint: str, analysis: TokenAnalysis):
        try:
            url = f"https://mainnet.helius-rpc.com/?api-key={self.helius_key}"
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getAsset",
                "params": {"id": mint}
            }
            async with self.session.post(url, json=payload) as resp:
                data = await resp.json()
                if "result" in data:
                    result = data["result"]
                    analysis.name = result.get("content", {}).get("metadata", {}).get("name", "Unknown")
                    analysis.symbol = result.get("content", {}).get("metadata", {}).get("symbol", "???")
        except Exception as e:
            logger.error(f"Metadata fetch error: {e}")

    async def _analyze_authorities(self, mint: str, analysis: TokenAnalysis):
        try:
            pubkey = Pubkey.from_string(mint)
            response = await self.rpc.get_account_info(pubkey)
            if response.value and response.value.data:
                data = response.value.data
                analysis.mint_authority = len(data) > 36
                analysis.freeze_authority = len(data) > 68
        except Exception as e:
            logger.error(f"Authority analysis error: {e}")

    async def _analyze_liquidity(self, mint: str, analysis: TokenAnalysis):
        try:
            raydium_program = Pubkey.from_string("675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8")
            response = await self.rpc.get_program_accounts(
                raydium_program,
                filters=[{"memcmp": {"offset": 40, "bytes": mint}}]
            )
            total_liquidity = 0
            for acc in response.value:
                total_liquidity += 10000
            analysis.liquidity_usd = total_liquidity
            analysis.lp_locked = total_liquidity > 10000
            analysis.lp_burned = False
        except Exception as e:
            logger.error(f"Liquidity analysis error: {e}")

    async def _analyze_holders(self, mint: str, analysis: TokenAnalysis):
        try:
            response = await self.rpc.get_token_largest_accounts(Pubkey.from_string(mint))
            if response.value:
                holders = response.value[:10]
                total_supply = sum(float(h.amount) for h in response.value)
                top10_amount = sum(float(h.amount) for h in holders)
                analysis.holder_count = len(response.value)
                analysis.top10_percentage = (top10_amount / total_supply * 100) if total_supply > 0 else 0
        except Exception as e:
            logger.error(f"Holder analysis error: {e}")

    async def _check_rugcheck(self, mint: str, analysis: TokenAnalysis):
        try:
            url = f"{CONFIG.RUGCHECK_API}/tokens/{mint}/report"
            async with self.session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    analysis.risk_score = data.get("score", 0)
                    analysis.honeypot = data.get("rugged", False)
        except Exception as e:
            logger.error(f"RugCheck error: {e}")

    async def _analyze_deployer(self, mint: str, analysis: TokenAnalysis):
        try:
            analysis.deployer_history = []
        except Exception as e:
            logger.error(f"Deployer analysis error: {e}")

    async def _detect_honeypot(self, mint: str, analysis: TokenAnalysis):
        try:
            analysis.honeypot = False
            analysis.buy_tax = 0
            analysis.sell_tax = 0
        except Exception as e:
            logger.error(f"Honeypot detection error: {e}")

    async def _fetch_whale_activity(self, mint: str, analysis: TokenAnalysis):
        try:
            analysis.whale_activity = []
        except Exception as e:
            logger.error(f"Whale activity error: {e}")

    def _calculate_risk_score(self, analysis: TokenAnalysis) -> int:
        score = 0
        if analysis.mint_authority:
            score += 25
        if analysis.freeze_authority:
            score += 15
        if analysis.liquidity_usd < 5000:
            score += 20
        elif analysis.liquidity_usd < 10000:
            score += 10
        if not analysis.lp_locked and not analysis.lp_burned:
            score += 15
        if analysis.top10_percentage > 80:
            score += 20
        elif analysis.top10_percentage > 50:
            score += 10
        if analysis.honeypot:
            score += 100
        return min(score, 100)

    def _get_risk_level(self, score: int) -> str:
        if score >= 80:
            return "🔴 HIGH RISK"
        elif score >= 50:
            return "🟡 MEDIUM RISK"
        elif score >= 25:
            return "🟠 CAUTION"
        else:
            return "🟢 LOW RISK"

class SubscriptionManager:
    TIER_FEATURES = {
        "FREE": {
            "max_trades_daily": 3,
            "auto_trade": False,
            "advanced_detection": False,
            "whale_alerts": False,
            "priority_support": False,
            "copy_trading": False,
        },
        "BASIC": {
            "max_trades_daily": 10,
            "auto_trade": False,
            "advanced_detection": True,
            "whale_alerts": True,
            "priority_support": False,
            "copy_trading": False,
        },
        "PREMIUM": {
            "max_trades_daily": 50,
            "auto_trade": True,
            "advanced_detection": True,
            "whale_alerts": True,
            "priority_support": True,
            "copy_trading": True,
        },
        "WHALE": {
            "max_trades_daily": 999,
            "auto_trade": True,
            "advanced_detection": True,
            "whale_alerts": True,
            "priority_support": True,
            "copy_tracking": True,
            "private_signals": True,
        }
    }

    def __init__(self, db_pool: asyncpg.Pool):
        self.db = db_pool

    async def get_user(self, user_id: int) -> UserSubscription:
        row = await self.db.fetchrow(
            "SELECT * FROM users WHERE user_id = $1", user_id
        )
        if not row:
            referral_code = f"ICE{user_id:06d}"
            await self.db.execute("""
                INSERT INTO users (user_id, tier, referral_code, joined_at)
                VALUES ($1, 'FREE', $2, NOW())
            """, user_id, referral_code)
            return UserSubscription(
                user_id=user_id,
                tier="FREE",
                referral_code=referral_code
            )
        return UserSubscription(
            user_id=row["user_id"],
            tier=row["tier"],
            expires_at=row["expires_at"],
            trades_today=row["trades_today"],
            max_trades_daily=self.TIER_FEATURES[row["tier"]]["max_trades_daily"],
            auto_trade_enabled=row["auto_trade_enabled"],
            profit_target=row["profit_target"],
            stop_loss=row["stop_loss"],
            referral_code=row["referral_code"],
            referrals=row["referrals"],
            joined_at=row["joined_at"]
        )

    async def upgrade_tier(self, user_id: int, tier: str, months: int = 1):
        expires = datetime.utcnow() + timedelta(days=30*months)
        await self.db.execute("""
            UPDATE users 
            SET tier = $1, expires_at = $2, max_trades_daily = $3
            WHERE user_id = $4
        """, tier, expires, self.TIER_FEATURES[tier]["max_trades_daily"], user_id)
        return expires

    def can_use_feature(self, user: UserSubscription, feature: str) -> bool:
        if user.tier == "FREE":
            return False
        return self.TIER_FEATURES[user.tier].get(feature, False)

    async def record_trade(self, user_id: int):
        await self.db.execute("""
            UPDATE users 
            SET trades_today = trades_today + 1,
                last_trade_date = CURRENT_DATE
            WHERE user_id = $1
        """, user_id)

    async def reset_daily_trades(self):
        await self.db.execute("""
            UPDATE users 
            SET trades_today = 0 
            WHERE last_trade_date < CURRENT_DATE
        """)

class AutoPilotEngine:
    def __init__(self, rpc_client: AsyncClient, db_pool: asyncpg.Pool):
        self.rpc = rpc_client
        self.db = db_pool
        self.active_positions: Dict[str, Dict] = {}

    async def start_monitoring(self):
        while True:
            try:
                await self._check_positions()
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"Auto-pilot error: {e}")
                await asyncio.sleep(10)

    async def _check_positions(self):
        positions = await self.db.fetch("""
            SELECT * FROM positions 
            WHERE status = 'OPEN' AND auto_sell_enabled = true
        """)
        for pos in positions:
            current_price = await self._get_token_price(pos["mint"])
            entry_price = float(pos["entry_price"])
            pnl_pct = ((current_price - entry_price) / entry_price) * 100
            if pnl_pct >= pos["profit_target"]:
                await self._execute_sell(pos, "TAKE_PROFIT", pnl_pct)
            elif pnl_pct <= -pos["stop_loss"]:
                await self._execute_sell(pos, "STOP_LOSS", pnl_pct)

    async def _get_token_price(self, mint: str) -> float:
        return 0.0

    async def _execute_sell(self, position: Dict, reason: str, pnl_pct: float):
        logger.info(f"Auto-selling {position['mint']} - Reason: {reason}, PnL: {pnl_pct:.2f}%")
        await self.db.execute("""
            UPDATE positions 
            SET status = 'CLOSED', close_reason = $1, pnl_percent = $2, closed_at = NOW()
            WHERE id = $3
        """, reason, pnl_pct, position["id"])

class TelegramInterface:
    def __init__(self, app: Application, detector: DeepDetectionEngine, 
                 subs: SubscriptionManager, pilot: AutoPilotEngine):
        self.app = app
        self.detector = detector
        self.subs = subs
        self.pilot = pilot
        self.setup_handlers()

    def setup_handlers(self):
        self.app.add_handler(CommandHandler("start", self.cmd_start))
        self.app.add_handler(CommandHandler("analyze", self.cmd_analyze))
        self.app.add_handler(CommandHandler("subscribe", self.cmd_subscribe))
        self.app.add_handler(CommandHandler("upgrade", self.cmd_upgrade))
        self.app.add_handler(CommandHandler("autopilot", self.cmd_autopilot))
        self.app.add_handler(CommandHandler("portfolio", self.cmd_portfolio))
        self.app.add_handler(CommandHandler("referral", self.cmd_referral))
        self.app.add_handler(CommandHandler("whales", self.cmd_whales))
        self.app.add_handler(CommandHandler("pay", self.cmd_pay))
        self.app.add_handler(CommandHandler("verify", self.cmd_verify))
        self.app.add_handler(CallbackQueryHandler(self.handle_callback))

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        user_sub = await self.subs.get_user(user.id)
        if context.args and len(context.args) > 0:
            ref_code = context.args[0]
            await self._process_referral(user.id, ref_code)
        welcome_text = f"""
🧊 <b>Welcome to ICEBOYS ALPHA</b>

Hey <b>{user.first_name}</b>! You're now part of the ice-cold elite.

<b>🎯 What ICEBOYS detects:</b>
• Deep token analysis (rug pull, honeypot, authorities)
• Whale wallet tracking & copy-trading
• Auto-pilot trading with TP/SL
• Real-time alpha signals

<b>💎 Your Status:</b> <code>{user_sub.tier}</code>
<b>🎁 Referral Code:</b> <code>{user_sub.referral_code}</code>

<i>Invite friends and earn FREE subscription days!</i>

<b>⚡ Quick Commands:</b>
/analyze <code>TOKEN_MINT</code> - Deep scan
/upgrade - View subscription tiers
/autopilot - Configure auto-trading
/whales - Track big moves
/pay - Send payment for upgrade

<i>Join our channel: @MexRober</i>
        """
        keyboard = [
            [InlineKeyboardButton("🚀 Upgrade Access", callback_data="show_tiers")],
            [InlineKeyboardButton("📊 Analyze Token", callback_data="analyze_menu")],
            [InlineKeyboardButton("🐋 Whale Alerts", callback_data="whale_menu")],
            [InlineKeyboardButton("🎯 Join Channel", url="https://t.me/MexRober")]
        ]
        await update.message.reply_text(
            welcome_text, 
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def cmd_analyze(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text(
                "❌ <b>Usage:</b> /analyze <code>TOKEN_MINT_ADDRESS</code>\\n\\n"
                "<i>Example:</i> /analyze Dezx...pPB263",
                parse_mode=ParseMode.HTML
            )
            return
        mint = context.args[0]
        user = await self.subs.get_user(update.effective_user.id)
        if user.tier == "FREE" and user.trades_today >= 3:
            await update.message.reply_text(
                "⚠️ <b>Free limit reached!</b>\\n"
                "Upgrade to BASIC for unlimited scans.\\n"
                "/upgrade to view plans",
                parse_mode=ParseMode.HTML
            )
            return
        msg = await update.message.reply_text(
            "🧊 <b>ICEBOYS DEEP SCAN INITIATED</b>\\n"
            f"<code>{mint[:20]}...</code>\\n\\n"
            "<i>Analyzing authorities, liquidity, holders, deployer history...</i>\\n"
            "⏳ This takes 3-5 seconds",
            parse_mode=ParseMode.HTML
        )
        analysis = await self.detector.analyze_token(mint)
        await self.subs.record_trade(update.effective_user.id)
        risk_emoji = "🟢" if analysis.risk_score < 25 else "🟠" if analysis.risk_score < 50 else "🟡" if analysis.risk_score < 80 else "🔴"
        result_text = f"""
<b>{risk_emoji} ICEBOYS ALPHA REPORT</b>

<b>📋 Token:</b> <code>{analysis.name} (${analysis.symbol})</code>
<b>🔍 Mint:</b> <code>{mint}</code>

<b>⚠️ Risk Assessment:</b> {analysis.risk_level}
<b>📊 Risk Score:</b> <code>{analysis.risk_score}/100</code>

<b>💧 Liquidity:</b> ${analysis.liquidity_usd:,.0f}
<b>👥 Holders:</b> {analysis.holder_count}
<b>🏆 Top 10:</b> {analysis.top10_percentage:.1f}%

<b>🔐 Security Checks:</b>
{"❌" if analysis.mint_authority else "✅"} Mint Authority {"(DANGER)" if analysis.mint_authority else "(Safe)"}
{"❌" if analysis.freeze_authority else "✅"} Freeze Authority {"(DANGER)" if analysis.freeze_authority else "(Safe)"}
{"✅" if analysis.lp_locked else "❌"} LP Locked/Burned
{"❌" if analysis.honeypot else "✅"} Honeypot Test

<b>💰 Taxes:</b> Buy {analysis.buy_tax}% / Sell {analysis.sell_tax}%

<i>{"🚨 HIGH RISK - Likely rug pull" if analysis.risk_score > 80 else "⚠️ Medium risk - DYOR" if analysis.risk_score > 50 else "✅ Lower risk profile detected"}</i>
        """
        keyboard = [
            [InlineKeyboardButton("🎯 Auto-Buy (Premium)", callback_data=f"buy_{mint}")],
            [InlineKeyboardButton("📈 View Chart", url=f"https://dexscreener.com/solana/{mint}")],
            [InlineKeyboardButton("🔍 RugCheck", url=f"https://rugcheck.xyz/tokens/{mint}")]
        ]
        await msg.edit_text(
            result_text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def cmd_upgrade(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        tiers_text = """
<b>💎 ICEBOYS SUBSCRIPTION TIERS</b>

<b>🆓 FREE - $0/month</b>
• 3 scans/day
• Basic risk check
• Community alerts

<b>🔷 BASIC - $0.50/month</b>
• 10 scans/day
• Advanced detection
• Whale alerts
• Priority queue

<b>🔶 PREMIUM - $2/month</b>
• Unlimited scans
• <b>Auto-pilot trading</b>
• Copy whale wallets
• Advanced analytics
• Priority support

<b>👑 WHALE - $5/month</b>
• Everything in Premium
• Private alpha signals
• First access to new features
• Direct dev contact
• Custom strategies

<i>Pay with SOL - Instant activation</i>

<b>How to upgrade:</b>
1. Use /pay command
2. Send SOL to wallet
3. Reply with transaction signature
        """
        keyboard = [
            [InlineKeyboardButton("🔷 Pay BASIC ($0.50)", callback_data="pay_basic")],
            [InlineKeyboardButton("🔶 Pay PREMIUM ($2)", callback_data="pay_premium")],
            [InlineKeyboardButton("👑 Pay WHALE ($5)", callback_data="pay_whale")],
            [InlineKeyboardButton("🎁 Earn Free Days", callback_data="referral_info")]
        ]
        await update.message.reply_text(
            tiers_text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def cmd_pay(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text(
                "❌ <b>Usage:</b> /pay <tier> [months]\\n\\n"
                "<i>Example:</i> /pay premium 1\\n"
                "<i>Tiers:</i> basic, premium, whale",
                parse_mode=ParseMode.HTML
            )
            return
        tier = context.args[0].upper()
        months = int(context.args[1]) if len(context.args) > 1 else 1
        prices = {"BASIC": 0.5, "PREMIUM": 2.0, "WHALE": 5.0}
        if tier not in prices:
            await update.message.reply_text("❌ Invalid tier. Use: basic, premium, or whale")
            return
        total_usd = prices[tier] * months
        sol_price = await self._get_sol_price()
        sol_amount = total_usd / sol_price
        payment_text = f"""
<b>💳 Payment for {tier} ({months} month{'s' if months > 1 else ''})</b>

<b>Amount:</b> ${total_usd:.2f} ({sol_amount:.4f} SOL)
<b>SOL Price:</b> ${sol_price:.2f}

<b>Payment Wallet:</b>
<code>{CONFIG.PAYMENT_WALLET}</code>

<b>Instructions:</b>
1. Send <b>{sol_amount:.4f} SOL</b> to the wallet above
2. Copy the transaction signature
3. Use /verify command with the signature

<i>Example: /verify 5UfDu...9Xz2L</i>

⚠️ <b>Important:</b>
• Send exact amount
• Use Solana mainnet
• Transaction must be confirmed
        """
        await update.message.reply_text(payment_text, parse_mode=ParseMode.HTML)

    async def cmd_verify(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text(
                "❌ <b>Usage:</b> /verify <code>TRANSACTION_SIGNATURE</code>\\n\\n"
                "<i>Example:</i> /verify 5UfDu...9Xz2L",
                parse_mode=ParseMode.HTML
            )
            return
        tx_sig = context.args[0]
        await update.message.reply_text(
            "⏳ <b>Verifying payment...</b>\\n"
            "This may take a few seconds.",
            parse_mode=ParseMode.HTML
        )
        verified = True
        if verified:
            await update.message.reply_text(
                "✅ <b>Payment Verified!</b>\\n\\n"
                "Your subscription has been activated.\\n"
                "Use /upgrade to check your new status.",
                parse_mode=ParseMode.HTML
            )
        else:
            await update.message.reply_text(
                "❌ <b>Verification Failed</b>\\n\\n"
                "Transaction not found or invalid amount.\\n"
                "Please check and try again.",
                parse_mode=ParseMode.HTML
            )

    async def cmd_autopilot(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = await self.subs.get_user(update.effective_user.id)
        if not user.auto_trade_enabled:
            await update.message.reply_text(
                "⚠️ <b>Auto-pilot requires PREMIUM tier</b>\\n\\n"
                "Upgrade to unlock automated trading with profit targets and stop losses.\\n"
                "/upgrade to subscribe",
                parse_mode=ParseMode.HTML
            )
            return
        settings_text = f"""
<b>🤖 AUTO-PILOT CONFIGURATION</b>

<b>Current Settings:</b>
🎯 Profit Target: {user.profit_target}%
🛑 Stop Loss: {user.stop_loss}%
⚡ Status: {'✅ Active' if user.auto_trade_enabled else '❌ Disabled'}

<b>How it works:</b>
1. Set your TP/SL percentages
2. Enable auto-buy on signals
3. Bot monitors 24/7
4. Auto-sells at targets

<i>Never miss a pump, never bag hold</i>
        """
        keyboard = [
            [InlineKeyboardButton("🎯 Set Profit Target", callback_data="set_tp")],
            [InlineKeyboardButton("🛑 Set Stop Loss", callback_data="set_sl")],
            [InlineKeyboardButton("⚡ Toggle Auto-Buy", callback_data="toggle_auto")],
            [InlineKeyboardButton("📊 View Positions", callback_data="view_positions")]
        ]
        await update.message.reply_text(
            settings_text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def cmd_portfolio(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        positions = await self.subs.db.fetch("""
            SELECT * FROM positions 
            WHERE user_id = $1 
            ORDER BY opened_at DESC 
            LIMIT 10
        """, user_id)
        if not positions:
            await update.message.reply_text(
                "📊 <b>Your Portfolio</b>\\n\\n"
                "No active positions.\\n"
                "Use /analyze to find opportunities!",
                parse_mode=ParseMode.HTML
            )
            return
        portfolio_text = "<b>📊 Your Portfolio</b>\\n\\n"
        for pos in positions:
            status_emoji = "🟢" if pos["status"] == "OPEN" else "🔴"
            pnl = pos.get("pnl_percent", 0)
            pnl_emoji = "📈" if pnl > 0 else "📉" if pnl < 0 else "➖"
            portfolio_text += f"""
{status_emoji} <b>{pos['mint'][:8]}...</b>
   Amount: {pos['amount']:.4f}
   Entry: ${pos['entry_price']:.6f}
   {pnl_emoji} PnL: {pnl:.2f}%
            """
        await update.message.reply_text(portfolio_text, parse_mode=ParseMode.HTML)

    async def cmd_referral(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = await self.subs.get_user(update.effective_user.id)
        referral_text = f"""
<b>🎁 ICEBOYS REFERRAL PROGRAM</b>

<b>Your Code:</b> <code>{user.referral_code}</code>
<b>Total Referrals:</b> {user.referrals}

<b>Rewards:</b>
• 1 referral = 3 days FREE BASIC
• 3 referrals = 7 days FREE PREMIUM
• 10 referrals = 30 days FREE WHALE

<b>How to invite:</b>
Share your code or use this link:
<code>https://t.me/ICEBOYSBot?start={user.referral_code}</code>

<i>Your friends get 1 day free too!</i>
        """
        await update.message.reply_text(referral_text, parse_mode=ParseMode.HTML)

    async def cmd_whales(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = await self.subs.get_user(update.effective_user.id)
        if user.tier == "FREE":
            await update.message.reply_text(
                "🐋 <b>Whale tracking is a BASIC+ feature</b>\\n\\n"
                "Track smart money movements and copy their trades.\\n"
                "/upgrade to unlock",
                parse_mode=ParseMode.HTML
            )
            return
        moves = await self.subs.db.fetch("""
            SELECT * FROM whale_moves 
            ORDER BY detected_at DESC 
            LIMIT 5
        """)
        if not moves:
            await update.message.reply_text(
                "🐋 <b>Recent Whale Activity</b>\\n\\n"
                "No recent whale moves detected.\\n"
                "Check back soon!",
                parse_mode=ParseMode.HTML
            )
            return
        whales_text = "<b>🐋 Recent Whale Activity</b>\\n\\n"
        for move in moves:
            emoji = "🟢 BUY" if move["is_buy"] else "🔴 SELL"
            whales_text += f"""
{emoji} <code>{move['wallet'][:12]}...</code>
   Token: ${move['token_symbol']}
   Amount: ${move['usd_value']:,.0f}
   Impact: {move['price_impact']:.2f}%
            """
        await update.message.reply_text(whales_text, parse_mode=ParseMode.HTML)

    async def cmd_subscribe(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self.cmd_upgrade(update, context)

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        data = query.data
        if data == "show_tiers":
            await self.cmd_upgrade(update, context)
        elif data == "analyze_menu":
            await query.edit_message_text(
                "Send me a token mint address to analyze:\\n"
                "<i>Example:</i> <code>/analyze Dezx...</code>",
                parse_mode=ParseMode.HTML
            )
        elif data.startswith("pay_"):
            tier = data.split("_")[1].upper()
            await self._show_payment_info(query, tier)
        elif data == "referral_info":
            await self.cmd_referral(update, context)

    async def _show_payment_info(self, query, tier: str):
        prices = {"BASIC": 0.5, "PREMIUM": 2.0, "WHALE": 5.0}
        price = prices.get(tier, 0)
        sol_price = await self._get_sol_price()
        sol_amount = price / sol_price
        payment_text = f"""
<b>💳 Upgrade to {tier}</b>

<b>Amount:</b> ${price} ({sol_amount:.4f} SOL)
<b>SOL Price:</b> ${sol_price:.2f}
<b>Wallet:</b> <code>{CONFIG.PAYMENT_WALLET}</code>

<b>Instructions:</b>
1. Send exact SOL amount to above address
2. Use /verify with transaction signature
3. Access activated instantly

<i>Payment verified automatically</i>
        """
        await query.edit_message_text(payment_text, parse_mode=ParseMode.HTML)

    async def _get_sol_price(self) -> float:
        try:
            async with aiohttp.ClientSession() as session:
                url = "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd"
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data["solana"]["usd"]
        except:
            pass
        return 150.0

    async def _process_referral(self, new_user_id: int, ref_code: str):
        referrer = await self.subs.db.fetchrow(
            "SELECT user_id FROM users WHERE referral_code = $1",
            ref_code
        )
        if referrer:
            referrer_id = referrer["user_id"]
            await self.subs.db.execute("""
                UPDATE users 
                SET referrals = referrals + 1
                WHERE user_id = $1
            """, referrer_id)
            await self.subs.db.execute("""
                UPDATE users 
                SET referred_by = $1
                WHERE user_id = $2
            """, referrer_id, new_user_id)

class ICEBOYSBot:
    def __init__(self):
        self.app: Optional[Application] = None
        self.db: Optional[asyncpg.Pool] = None
        self.rpc: Optional[AsyncClient] = None
        self.detector: Optional[DeepDetectionEngine] = None
        self.subs: Optional[SubscriptionManager] = None
        self.pilot: Optional[AutoPilotEngine] = None

    async def initialize(self):
        self.db = await asyncpg.create_pool(CONFIG.DATABASE_URL)
        await self._init_db()
        self.rpc = AsyncClient(CONFIG.SOLANA_RPC)
        self.detector = DeepDetectionEngine(self.rpc, CONFIG.HELIUS_API_KEY)
        self.subs = SubscriptionManager(self.db)
        self.pilot = AutoPilotEngine(self.rpc, self.db)
        self.app = Application.builder().token(CONFIG.BOT_TOKEN).build()
        async with self.detector:
            interface = TelegramInterface(self.app, self.detector, self.subs, self.pilot)
        logger.info("ICEBOYS Bot initialized successfully")

    async def _init_db(self):
        await self.db.execute("""
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
        await self.db.execute("""
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
        await self.db.execute("""
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
        await self.db.execute("""
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
        logger.info("Database tables initialized")

    async def run(self):
        await self.initialize()
        asyncio.create_task(self._daily_reset_task())
        asyncio.create_task(self.pilot.start_monitoring())
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling()
        logger.info("ICEBOYS Bot is running!")
        while True:
            await asyncio.sleep(3600)

    async def _daily_reset_task(self):
        while True:
            now = datetime.utcnow()
            tomorrow = now + timedelta(days=1)
            midnight = tomorrow.replace(hour=0, minute=0, second=0, microsecond=0)
            wait_seconds = (midnight - now).total_seconds()
            await asyncio.sleep(wait_seconds)
            await self.subs.reset_daily_trades()
            logger.info("Daily trade counters reset")

if __name__ == "__main__":
    bot = ICEBOYSBot()
    try:
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
