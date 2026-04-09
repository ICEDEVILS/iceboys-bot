#!/usr/bin/env python3
"""
ICEBOYS TRADING ENGINE v2.0
Execute swaps via Jupiter API with auto-pilot functionality
"""

import asyncio
import base64
import json
import logging
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
import aiohttp
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Commitment
from solana.rpc.types import TxOpts
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.transaction import VersionedTransaction
from solders.message import MessageV0
import asyncpg

logger = logging.getLogger(__name__)

SOL_MINT = "So11111111111111111111111111111111111111112"
JUPITER_QUOTE_API = "https://quote-api.jup.ag/v6"
JUPITER_SWAP_API = "https://api.jup.ag/swap/v1"

class TradingEngine:
    def __init__(self, rpc_client: AsyncClient, db_pool: asyncpg.Pool, 
                 wallet_keypair: Keypair, jupiter_api_key: Optional[str] = None):
        self.rpc = rpc_client
        self.db = db_pool
        self.wallet = wallet_keypair
        self.jupiter_key = jupiter_api_key
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def get_quote(self, input_mint: str, output_mint: str, 
                        amount: int, slippage_bps: int = 50) -> Optional[Dict]:
        try:
            params = {
                "inputMint": input_mint,
                "outputMint": output_mint,
                "amount": str(amount),
                "slippageBps": str(slippage_bps),
                "onlyDirectRoutes": "false",
                "asLegacyTransaction": "false"
            }
            url = f"{JUPITER_QUOTE_API}/quote"
            async with self.session.get(url, params=params) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    logger.error(f"Quote error: {resp.status}")
                    return None
        except Exception as e:
            logger.error(f"Get quote error: {e}")
            return None

    async def execute_swap(self, quote: Dict, wrap_unwrap_sol: bool = True) -> Optional[str]:
        try:
            payload = {
                "quoteResponse": quote,
                "userPublicKey": str(self.wallet.pubkey()),
                "wrapAndUnwrapSol": wrap_unwrap_sol,
                "dynamicComputeUnitLimit": True,
                "prioritizationFeeLamports": "auto"
            }
            url = f"{JUPITER_SWAP_API}/swap"
            async with self.session.post(url, json=payload) as resp:
                if resp.status != 200:
                    logger.error(f"Swap error: {await resp.text()}")
                    return None
                swap_data = await resp.json()
            tx_bytes = base64.b64decode(swap_data["swapTransaction"])
            tx = VersionedTransaction.from_bytes(tx_bytes)
            tx.sign([self.wallet])
            raw_tx = tx.serialize()
            sig = await self.rpc.send_raw_transaction(
                raw_tx,
                TxOpts(skip_preflight=False, max_retries=3)
            )
            await self.rpc.confirm_transaction(sig, commitment=Commitment("confirmed"))
            logger.info(f"Swap executed: {sig.value}")
            return str(sig.value)
        except Exception as e:
            logger.error(f"Execute swap error: {e}")
            return None

    async def buy_token(self, token_mint: str, sol_amount: float, 
                        slippage: int = 50, user_id: Optional[int] = None) -> Optional[Dict]:
        amount_lamports = int(sol_amount * 1e9)
        quote = await self.get_quote(SOL_MINT, token_mint, amount_lamports, slippage)
        if not quote:
            return None
        tx_sig = await self.execute_swap(quote)
        if tx_sig and user_id:
            await self._record_position(user_id, token_mint, sol_amount, 
                                       quote.get("outAmount", 0), tx_sig, "BUY")
        return {
            "signature": tx_sig,
            "input_amount": sol_amount,
            "expected_output": quote.get("outAmount"),
            "price_impact": quote.get("priceImpactPct"),
            "route": quote.get("routePlan", [])
        }

    async def sell_token(self, token_mint: str, token_amount: int,
                         slippage: int = 50, user_id: Optional[int] = None) -> Optional[Dict]:
        quote = await self.get_quote(token_mint, SOL_MINT, token_amount, slippage)
        if not quote:
            return None
        tx_sig = await self.execute_swap(quote)
        if tx_sig and user_id:
            await self._close_position(user_id, token_mint, 
                                      quote.get("outAmount", 0), tx_sig)
        return {
            "signature": tx_sig,
            "input_amount": token_amount,
            "expected_output": quote.get("outAmount"),
            "price_impact": quote.get("priceImpactPct")
        }

    async def get_token_price(self, token_mint: str) -> Optional[float]:
        try:
            quote = await self.get_quote(SOL_MINT, token_mint, int(1e9), slippage_bps=100)
            if quote and "outAmount" in quote:
                sol_price_usd = await self._get_sol_price()
                token_amount = int(quote["outAmount"])
                decimals = await self._get_token_decimals(token_mint)
                price = (1.0 * sol_price_usd) / (token_amount / (10 ** decimals))
                return price
        except Exception as e:
            logger.error(f"Price fetch error: {e}")
        return None

    async def _get_sol_price(self) -> float:
        try:
            url = "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd"
            async with self.session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data["solana"]["usd"]
        except:
            pass
        return 150.0

    async def _get_token_decimals(self, mint: str) -> int:
        try:
            resp = await self.rpc.get_account_info(Pubkey.from_string(mint))
            if resp.value and resp.value.data:
                return resp.value.data[44]
        except:
            pass
        return 6

    async def _record_position(self, user_id: int, mint: str, 
                               entry_sol: float, token_amount: int,
                               tx_sig: str, side: str):
        price = entry_sol / (token_amount / 1e6)
        await self.db.execute("""
            INSERT INTO positions (user_id, mint, entry_price, amount, 
                                 status, tx_signature, opened_at)
            VALUES ($1, $2, $3, $4, 'OPEN', $5, NOW())
        """, user_id, mint, price, token_amount, tx_sig)

    async def _close_position(self, user_id: int, mint: str,
                             exit_sol: int, tx_sig: str):
        pos = await self.db.fetchrow("""
            SELECT * FROM positions 
            WHERE user_id = $1 AND mint = $2 AND status = 'OPEN'
            ORDER BY opened_at DESC LIMIT 1
        """, user_id, mint)
        if pos:
            entry_value = pos["entry_price"] * pos["amount"]
            exit_value = exit_sol / 1e9
            pnl_pct = ((exit_value - entry_value) / entry_value) * 100
            await self.db.execute("""
                UPDATE positions 
                SET status = 'CLOSED', exit_price = $1, pnl_percent = $2,
                    close_tx = $3, closed_at = NOW()
                WHERE id = $4
            """, exit_sol / pos["amount"], pnl_pct, tx_sig, pos["id"])

class AutoPilot:
    def __init__(self, trading_engine: TradingEngine, db_pool: asyncpg.Pool):
        self.trading = trading_engine
        self.db = db_pool
        self.running = False
        self.monitored_positions: Dict[int, Dict] = {}

    async def start(self):
        self.running = True
        while self.running:
            try:
                positions = await self.db.fetch("""
                    SELECT * FROM positions 
                    WHERE status = 'OPEN' AND auto_sell_enabled = true
                """)
                for pos in positions:
                    await self._check_position(pos)
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"Auto-pilot error: {e}")
                await asyncio.sleep(10)

    async def _check_position(self, position: Dict):
        mint = position["mint"]
        current_price = await self.trading.get_token_price(mint)
        if not current_price:
            return
        entry_price = float(position["entry_price"])
        pnl_pct = ((current_price - entry_price) / entry_price) * 100
        tp_target = float(position["profit_target"])
        sl_limit = -float(position["stop_loss"])
        if pnl_pct >= tp_target:
            logger.info(f"TP hit for {mint}: {pnl_pct:.2f}%")
            await self._execute_sell(position, current_price, "TAKE_PROFIT", pnl_pct)
        elif pnl_pct <= sl_limit:
            logger.info(f"SL hit for {mint}: {pnl_pct:.2f}%")
            await self._execute_sell(position, current_price, "STOP_LOSS", pnl_pct)

    async def _execute_sell(self, position: Dict, price: float, 
                           reason: str, pnl_pct: float):
        try:
            result = await self.trading.sell_token(
                position["mint"],
                int(position["amount"]),
                slippage=100,
                user_id=position["user_id"]
            )
            if result:
                await self.db.execute("""
                    UPDATE positions 
                    SET status = 'CLOSED', close_reason = $1, 
                        exit_price = $2, pnl_percent = $3, closed_at = NOW()
                    WHERE id = $4
                """, reason, price, pnl_pct, position["id"])
                logger.info(f"Auto-sold {position['mint']} for {pnl_pct:.2f}% {reason}")
        except Exception as e:
            logger.error(f"Auto-sell error: {e}")

    async def enable_auto_pilot(self, user_id: int, mint: str,
                                tp_pct: float, sl_pct: float):
        await self.db.execute("""
            UPDATE positions 
            SET auto_sell_enabled = true, 
                profit_target = $1, 
                stop_loss = $2
            WHERE user_id = $3 AND mint = $4 AND status = 'OPEN'
        """, tp_pct, sl_pct, user_id, mint)
        logger.info(f"Auto-pilot enabled for user {user_id}, token {mint}")

if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    load_dotenv()
    async def main():
        db = await asyncpg.create_pool(os.getenv("DATABASE_URL"))
        rpc = AsyncClient(os.getenv("SOLANA_RPC"))
        wallet_key = os.getenv("WALLET_PRIVATE_KEY")
        if wallet_key:
            wallet = Keypair.from_base58_string(wallet_key)
        else:
            logger.error("No wallet configured")
            return
        trading = TradingEngine(rpc, db, wallet)
        autopilot = AutoPilot(trading, db)
        async with trading:
            await autopilot.start()
    asyncio.run(main())
