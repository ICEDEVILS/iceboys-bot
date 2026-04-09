#!/usr/bin/env python3
"""
ICEBOYS MONITOR v2.0
Real-time Solana token monitoring with Helius webhooks
Tracks: Pump.fun, Raydium, Meteora, Orca
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Callable
from dataclasses import dataclass
import aiohttp
import asyncpg
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Commitment
from solders.pubkey import Pubkey
import os
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

PUMPFUN_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
PUMPFUN_AMM = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
RAYDIUM_AMM_V4 = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"
RAYDIUM_CLMM = "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK"
METEORA_DLMM = "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPyo"
ORCA_WHIRLPOOL = "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc"

@dataclass
class TokenEvent:
    mint: str
    name: str
    symbol: str
    platform: str
    liquidity_sol: float
    liquidity_usd: float
    timestamp: datetime
    tx_signature: str
    deployer: str
    bonding_curve_complete: bool = False
    market_cap: float = 0.0

@dataclass
class WhaleMove:
    wallet: str
    token_mint: str
    token_symbol: str
    is_buy: bool
    amount_sol: float
    usd_value: float
    price_impact: float
    timestamp: datetime
    tx_signature: str
    platform: str

class HeliusWebhookHandler:
    def __init__(self, db_pool: asyncpg.Pool, helius_key: str, 
                 callback: Optional[Callable] = None):
        self.db = db_pool
        self.helius_key = helius_key
        self.callback = callback
        self.session: Optional[aiohttp.ClientSession] = None
        self.webhook_id: Optional[str] = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def create_webhook(self, webhook_url: str, 
                             transaction_types: List[str] = None,
                             account_addresses: List[str] = None):
        if transaction_types is None:
            transaction_types = ["TOKEN_MINT", "CREATE_POOL", "SWAP"]
        if account_addresses is None:
            account_addresses = [
                PUMPFUN_PROGRAM,
                RAYDIUM_AMM_V4,
                METEORA_DLMM,
                ORCA_WHIRLPOOL
            ]
        payload = {
            "webhookURL": webhook_url,
            "transactionTypes": transaction_types,
            "accountAddresses": account_addresses,
            "webhookType": "enhanced",
            "enhanced": True,
            "encoding": "jsonParsed"
        }
        url = f"https://api.helius.xyz/v0/webhooks/?api-key={self.helius_key}"
        try:
            async with self.session.post(url, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self.webhook_id = data.get("webhookID")
                    logger.info(f"Webhook created: {self.webhook_id}")
                    return self.webhook_id
                else:
                    logger.error(f"Webhook creation failed: {await resp.text()}")
                    return None
        except Exception as e:
            logger.error(f"Create webhook error: {e}")
            return None

    async def delete_webhook(self):
        if not self.webhook_id:
            return
        url = f"https://api.helius.xyz/v0/webhooks/{self.webhook_id}?api-key={self.helius_key}"
        try:
            async with self.session.delete(url) as resp:
                if resp.status == 200:
                    logger.info(f"Webhook {self.webhook_id} deleted")
        except Exception as e:
            logger.error(f"Delete webhook error: {e}")

    async def process_webhook_payload(self, payload: Dict):
        try:
            for tx in payload.get("data", []):
                await self._process_transaction(tx)
        except Exception as e:
            logger.error(f"Process payload error: {e}")

    async def _process_transaction(self, tx: Dict):
        tx_type = tx.get("type")
        signature = tx.get("signature")
        if tx_type == "TOKEN_MINT":
            await self._handle_token_mint(tx, signature)
        elif tx_type == "CREATE_POOL":
            await self._handle_pool_creation(tx, signature)
        elif tx_type == "SWAP":
            await self._handle_swap(tx, signature)

    async def _handle_token_mint(self, tx: Dict, signature: str):
        token_info = tx.get("token", {})
        mint = token_info.get("mint")
        if not mint:
            return
        is_pumpfun = any(
            acc.get("programId") == PUMPFUN_PROGRAM 
            for acc in tx.get("accountData", [])
        )
        platform = "pumpfun" if is_pumpfun else "unknown"
        event = TokenEvent(
            mint=mint,
            name=token_info.get("name", "Unknown"),
            symbol=token_info.get("symbol", "???"),
            platform=platform,
            liquidity_sol=0.0,
            liquidity_usd=0.0,
            timestamp=datetime.utcnow(),
            tx_signature=signature,
            deployer=tx.get("feePayer", ""),
            bonding_curve_complete=False
        )
        await self._store_token_event(event)
        if self.callback:
            await self.callback(event)

    async def _handle_pool_creation(self, tx: Dict, signature: str):
        program_id = None
        for acc in tx.get("accountData", []):
            pid = acc.get("programId")
            if pid in [RAYDIUM_AMM_V4, RAYDIUM_CLMM, METEORA_DLMM, ORCA_WHIRLPOOL]:
                program_id = pid
                break
        if not program_id:
            return
        platform_map = {
            RAYDIUM_AMM_V4: "raydium",
            RAYDIUM_CLMM: "raydium_clmm",
            METEORA_DLMM: "meteora",
            ORCA_WHIRLPOOL: "orca"
        }
        token_balances = tx.get("tokenBalanceChanges", [])
        if len(token_balances) < 2:
            return
        mint = None
        for bal in token_balances:
            if bal.get("mint") != "So11111111111111111111111111111111111111112":
                mint = bal.get("mint")
                break
        if not mint:
            return
        sol_changes = tx.get("nativeBalanceChanges", [])
        liquidity_sol = sum(
            abs(change.get("change", 0)) / 1e9 
            for change in sol_changes
        )
        event = TokenEvent(
            mint=mint,
            name="Unknown",
            symbol="???",
            platform=platform_map.get(program_id, "unknown"),
            liquidity_sol=liquidity_sol,
            liquidity_usd=0.0,
            timestamp=datetime.utcnow(),
            tx_signature=signature,
            deployer=tx.get("feePayer", ""),
            bonding_curve_complete=True
        )
        await self._store_token_event(event)
        if self.callback:
            await self.callback(event)

    async def _handle_swap(self, tx: Dict, signature: str):
        token_changes = tx.get("tokenBalanceChanges", [])
        native_changes = tx.get("nativeBalanceChanges", [])
        total_sol = sum(
            abs(change.get("change", 0)) / 1e9 
            for change in native_changes
        )
        if total_sol < 10:
            return
        token_mint = None
        token_amount = 0
        for change in token_changes:
            if change.get("mint") != "So11111111111111111111111111111111111111112":
                token_mint = change.get("mint")
                token_amount = abs(change.get("change", 0))
                break
        if not token_mint:
            return
        is_buy = any(change.get("change", 0) > 0 for change in token_changes)
        whale_move = WhaleMove(
            wallet=tx.get("feePayer", ""),
            token_mint=token_mint,
            token_symbol="???",
            is_buy=is_buy,
            amount_sol=total_sol,
            usd_value=total_sol * 150,
            price_impact=0.0,
            timestamp=datetime.utcnow(),
            tx_signature=signature,
            platform="unknown"
        )
        await self._store_whale_move(whale_move)
        if self.callback:
            await self.callback(whale_move)

    async def _store_token_event(self, event: TokenEvent):
        await self.db.execute("""
            INSERT INTO tokens_found (mint, name, symbol, platform, 
                                     liquidity_sol, liquidity_usd, deployer, 
                                     tx_signature, bonding_curve_complete, 
                                     market_cap, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            ON CONFLICT (mint) DO UPDATE SET
                liquidity_sol = EXCLUDED.liquidity_sol,
                liquidity_usd = EXCLUDED.liquidity_usd,
                market_cap = EXCLUDED.market_cap
        """, event.mint, event.name, event.symbol, event.platform,
             event.liquidity_sol, event.liquidity_usd, event.deployer,
             event.tx_signature, event.bonding_curve_complete,
             event.market_cap, event.timestamp)

    async def _store_whale_move(self, move: WhaleMove):
        await self.db.execute("""
            INSERT INTO whale_moves (wallet, token_mint, token_symbol, is_buy,
                                   amount_sol, usd_value, price_impact, 
                                   tx_signature, platform, detected_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        """, move.wallet, move.token_mint, move.token_symbol, move.is_buy,
             move.amount_sol, move.usd_value, move.price_impact,
             move.tx_signature, move.platform, move.timestamp)

class TokenMonitor:
    def __init__(self, rpc_client: AsyncClient, db_pool: asyncpg.Pool, 
                 helius_key: str, callback: Optional[Callable] = None):
        self.rpc = rpc_client
        self.db = db_pool
        self.helius_key = helius_key
        self.callback = callback
        self.session: Optional[aiohttp.ClientSession] = None
        self.seen_tokens: Set[str] = set()
        self.running = False

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.running = False
        if self.session:
            await self.session.close()

    async def start(self):
        self.running = True
        rows = await self.db.fetch(
            "SELECT DISTINCT mint FROM tokens_found WHERE created_at > NOW() - INTERVAL '24 hours'"
        )
        self.seen_tokens = {row["mint"] for row in rows}
        async with HeliusWebhookHandler(self.db, self.helius_key, self.callback) as handler:
            await self._poll_helius_api()

    async def _poll_helius_api(self):
        while self.running:
            try:
                await self._check_pumpfun_mints()
                await self._check_raydium_pools()
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"Poll error: {e}")
                await asyncio.sleep(10)

    async def _check_pumpfun_mints(self):
        try:
            url = f"https://api.helius.xyz/v0/addresses/?api-key={self.helius_key}"
            pass
        except Exception as e:
            logger.error(f"Pump.fun check error: {e}")

    async def _check_raydium_pools(self):
        try:
            pass
        except Exception as e:
            logger.error(f"Raydium check error: {e}")

class WhaleTracker:
    def __init__(self, db_pool: asyncpg.Pool, helius_key: str,
                 callback: Optional[Callable] = None):
        self.db = db_pool
        self.helius_key = helius_key
        self.callback = callback
        self.session: Optional[aiohttp.ClientSession] = None
        self.tracked_wallets: Set[str] = set()
        self.running = False

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.running = False
        if self.session:
            await self.session.close()

    async def start(self):
        self.running = True
        rows = await self.db.fetch("SELECT wallet FROM tracked_whales WHERE active = true")
        self.tracked_wallets = {row["wallet"] for row in rows}
        while self.running:
            try:
                for wallet in list(self.tracked_wallets)[:20]:
                    await self._check_wallet(wallet)
                await asyncio.sleep(3)
            except Exception as e:
                logger.error(f"Whale tracking error: {e}")
                await asyncio.sleep(10)

    async def add_whale(self, wallet: str, label: str = "", added_by: int = None):
        await self.db.execute("""
            INSERT INTO tracked_whales (wallet, label, added_by, added_at, active)
            VALUES ($1, $2, $3, NOW(), true)
            ON CONFLICT (wallet) DO UPDATE SET active = true
        """, wallet, label, added_by)
        self.tracked_wallets.add(wallet)
        logger.info(f"Added whale: {wallet} ({label})")

    async def _check_wallet(self, wallet: str):
        try:
            url = f"https://api.helius.xyz/v0/addresses/{wallet}/transactions?api-key={self.helius_key}"
            async with self.session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for tx in data.get("transactions", [])[:5]:
                        await self._process_whale_tx(wallet, tx)
        except Exception as e:
            logger.error(f"Check wallet error: {e}")

    async def _process_whale_tx(self, wallet: str, tx: Dict):
        if tx.get("type") not in ["SWAP", "JUPITER_SWAP"]:
            return
        token_changes = tx.get("tokenBalanceChanges", [])
        native_changes = tx.get("nativeBalanceChanges", [])
        if not token_changes or not native_changes:
            return
        sol_change = sum(change.get("change", 0) for change in native_changes) / 1e9
        if abs(sol_change) < 5:
            return
        token_mint = None
        token_amount = 0
        for change in token_changes:
            if change.get("mint") != "So11111111111111111111111111111111111111112":
                token_mint = change.get("mint")
                token_amount = abs(change.get("change", 0))
                break
        if not token_mint:
            return
        is_buy = sol_change < 0
        move = WhaleMove(
            wallet=wallet,
            token_mint=token_mint,
            token_symbol="???",
            is_buy=is_buy,
            amount_sol=abs(sol_change),
            usd_value=abs(sol_change) * 150,
            price_impact=0.0,
            timestamp=datetime.utcnow(),
            tx_signature=tx.get("signature", ""),
            platform=tx.get("source", "unknown")
        )
        await self.db.execute("""
            INSERT INTO whale_moves (wallet, token_mint, token_symbol, is_buy,
                                   amount_sol, usd_value, price_impact, 
                                   tx_signature, platform, detected_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        """, move.wallet, move.token_mint, move.token_symbol, move.is_buy,
             move.amount_sol, move.usd_value, move.price_impact,
             move.tx_signature, move.platform, move.timestamp)
        if self.callback:
            await self.callback(move)

class AlphaDetector:
    def __init__(self, db_pool: asyncpg.Pool, callback: Optional[Callable] = None):
        self.db = db_pool
        self.callback = callback

    async def analyze_opportunity(self, token_event: TokenEvent):
        is_alpha = (
            token_event.liquidity_sol >= 5 and
            token_event.liquidity_sol <= 100 and
            not token_event.bonding_curve_complete
        )
        if is_alpha:
            alpha_score = self._calculate_alpha_score(token_event)
            await self.db.execute("""
                INSERT INTO alpha_signals (mint, name, symbol, platform, 
                                         liquidity_sol, liquidity_usd, 
                                         alpha_score, detected_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (mint) DO UPDATE SET 
                    alpha_score = EXCLUDED.alpha_score,
                    detected_at = EXCLUDED.detected_at
            """, token_event.mint, token_event.name, token_event.symbol, 
                 token_event.platform, token_event.liquidity_sol,
                 token_event.liquidity_usd, alpha_score, datetime.utcnow())
            if self.callback:
                await self.callback({
                    "event": token_event,
                    "alpha_score": alpha_score
                })

    def _calculate_alpha_score(self, event: TokenEvent) -> float:
        score = 50
        if 10 <= event.liquidity_sol <= 50:
            score += 20
        elif 5 <= event.liquidity_sol < 10:
            score += 10
        if event.platform == "pumpfun":
            score += 15
        return min(score, 100)

MONITOR_SCHEMA = """
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
);

CREATE TABLE IF NOT EXISTS tracked_whales (
    id SERIAL PRIMARY KEY,
    wallet VARCHAR(50) UNIQUE NOT NULL,
    label VARCHAR(100),
    added_by BIGINT,
    added_at TIMESTAMP DEFAULT NOW(),
    active BOOLEAN DEFAULT true,
    success_rate DECIMAL DEFAULT 0,
    total_trades INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS whale_moves (
    id SERIAL PRIMARY KEY,
    wallet VARCHAR(50) REFERENCES tracked_whales(wallet),
    token_mint VARCHAR(50),
    token_symbol VARCHAR(20),
    is_buy BOOLEAN,
    amount_sol DECIMAL,
    usd_value DECIMAL,
    price_impact DECIMAL,
    tx_signature VARCHAR(100),
    platform VARCHAR(20),
    detected_at TIMESTAMP DEFAULT NOW()
);

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
);

CREATE INDEX IF NOT EXISTS idx_tokens_platform ON tokens_found(platform);
CREATE INDEX IF NOT EXISTS idx_tokens_created ON tokens_found(created_at);
CREATE INDEX IF NOT EXISTS idx_whale_moves_wallet ON whale_moves(wallet);
CREATE INDEX IF NOT EXISTS idx_whale_moves_detected ON whale_moves(detected_at);
CREATE INDEX IF NOT EXISTS idx_alpha_score ON alpha_signals(alpha_score DESC);
"""

async def init_monitor_db(db: asyncpg.Pool):
    async with db.acquire() as conn:
        await conn.execute(MONITOR_SCHEMA)
    logger.info("Monitor database initialized")

async def main():
    import os
    db = await asyncpg.create_pool(os.getenv("DATABASE_URL"))
    rpc = AsyncClient(os.getenv("SOLANA_RPC"))
    helius_key = os.getenv("HELIUS_API_KEY")
    await init_monitor_db(db)
    async with TokenMonitor(rpc, db, helius_key) as monitor:
        await monitor.start()

if __name__ == "__main__":
    asyncio.run(main())
