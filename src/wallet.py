#!/usr/bin/env python3
"""
Multi-chain wallet balance checker.
Supports: Ethereum, Base, Arbitrum, Optimism, Polygon, Solana.
Uses public RPC endpoints — no API keys required.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public RPC endpoints (free, no key)
# ---------------------------------------------------------------------------
RPC_ENDPOINTS: dict[str, str] = {
    "ethereum":  "https://ethereum-rpc.publicnode.com",
    "base":      "https://mainnet.base.org",
    "arbitrum":  "https://arb1.arbitrum.io/rpc",
    "optimism":  "https://mainnet.optimism.io",
    "polygon":   "https://polygon-bor-rpc.publicnode.com",
    "solana":    "https://api.mainnet-beta.solana.com",
}

CHAIN_NATIVE_SYMBOL: dict[str, str] = {
    "ethereum":  "ETH",
    "base":      "ETH",
    "arbitrum":  "ETH",
    "optimism":  "ETH",
    "polygon":   "MATIC",
    "solana":    "SOL",
}

CHAIN_DECIMALS: dict[str, int] = {
    "ethereum":  18,
    "base":      18,
    "arbitrum":  18,
    "optimism":  18,
    "polygon":   18,
    "solana":    9,
}

REQUEST_TIMEOUT = 15  # seconds


@dataclass
class ChainBalance:
    """Result container for a single chain balance check."""
    chain: str
    address: str
    balance_raw: int
    balance_formatted: float
    symbol: str
    success: bool = True
    error: Optional[str] = None

    def __str__(self) -> str:
        if self.success:
            return f"{self.chain.title()}: {self.balance_formatted:.6f} {self.symbol}"
        return f"{self.chain.title()}: ERROR — {self.error}"


@dataclass
class WalletBalances:
    """Aggregate results for all chains."""
    address: str
    balances: list[ChainBalance] = field(default_factory=list)

    def summary(self) -> str:
        lines = [f"Wallet: {self.address}", "=" * 60]
        for b in self.balances:
            lines.append(f"  {b}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# EVM helpers
# ---------------------------------------------------------------------------

def _eth_get_balance(rpc_url: str, address: str) -> int:
    """Call eth_getBalance via JSON-RPC and return the integer wei value."""
    payload = {
        "jsonrpc": "2.0",
        "method": "eth_getBalance",
        "params": [address, "latest"],
        "id": 1,
    }
    resp = requests.post(rpc_url, json=payload, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"RPC error: {data['error']}")
    return int(data["result"], 16)


def _check_evm_balance(chain: str, address: str) -> ChainBalance:
    """Return a ChainBalance for any EVM-compatible chain."""
    rpc_url = RPC_ENDPOINTS[chain]
    symbol = CHAIN_NATIVE_SYMBOL[chain]
    decimals = CHAIN_DECIMALS[chain]
    try:
        raw = _eth_get_balance(rpc_url, address)
        formatted = raw / (10 ** decimals)
        logger.info("Balance on %s: %.6f %s", chain, formatted, symbol)
        return ChainBalance(
            chain=chain,
            address=address,
            balance_raw=raw,
            balance_formatted=formatted,
            symbol=symbol,
        )
    except Exception as exc:
        logger.error("Failed to get balance on %s: %s", chain, exc)
        return ChainBalance(
            chain=chain,
            address=address,
            balance_raw=0,
            balance_formatted=0.0,
            symbol=symbol,
            success=False,
            error=str(exc),
        )


# ---------------------------------------------------------------------------
# Solana helper
# ---------------------------------------------------------------------------

def _check_solana_balance(address: str) -> ChainBalance:
    """Return a ChainBalance for Solana."""
    rpc_url = RPC_ENDPOINTS["solana"]
    payload = {
        "jsonrpc": "2.0",
        "method": "getBalance",
        "params": [address],
        "id": 1,
    }
    try:
        resp = requests.post(rpc_url, json=payload, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            raise RuntimeError(f"Solana RPC error: {data['error']}")
        raw = data["result"]["value"]  # lamports
        formatted = raw / (10 ** CHAIN_DECIMALS["solana"])
        logger.info("Balance on solana: %.6f SOL", formatted)
        return ChainBalance(
            chain="solana",
            address=address,
            balance_raw=raw,
            balance_formatted=formatted,
            symbol="SOL",
        )
    except Exception as exc:
        logger.error("Failed to get Solana balance: %s", exc)
        return ChainBalance(
            chain="solana",
            address=address,
            balance_raw=0,
            balance_formatted=0.0,
            symbol="SOL",
            success=False,
            error=str(exc),
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_balance(chain: str, address: str) -> ChainBalance:
    """Get native-token balance on a single chain.

    Parameters
    ----------
    chain : str
        One of: ethereum, base, arbitrum, optimism, polygon, solana.
    address : str
        Wallet address (hex for EVM, base58 for Solana).

    Returns
    -------
    ChainBalance
    """
    chain = chain.lower().strip()
    if chain not in RPC_ENDPOINTS:
        raise ValueError(f"Unsupported chain: {chain!r}. Choose from {list(RPC_ENDPOINTS)}")
    if chain == "solana":
        return _check_solana_balance(address)
    return _check_evm_balance(chain, address)


def get_all_balances(address: str, chains: Optional[list[str]] = None) -> WalletBalances:
    """Check native-token balances across multiple chains.

    Parameters
    ----------
    address : str
        Wallet address.
    chains : list[str] | None
        Subset of chains to check.  Defaults to all supported chains.

    Returns
    -------
    WalletBalances
    """
    if chains is None:
        chains = list(RPC_ENDPOINTS.keys())
    result = WalletBalances(address=address)
    for chain in chains:
        logger.info("Querying %s …", chain)
        result.balances.append(get_balance(chain, address))
        time.sleep(0.15)  # gentle rate-limit
    return result


def get_chain_info(chain: str) -> dict:
    """Return basic metadata about a supported chain.

    Returns a dict with keys: name, symbol, decimals, rpc_url.
    """
    chain = chain.lower().strip()
    if chain not in RPC_ENDPOINTS:
        raise ValueError(f"Unsupported chain: {chain!r}")
    return {
        "name": chain,
        "symbol": CHAIN_NATIVE_SYMBOL[chain],
        "decimals": CHAIN_DECIMALS[chain],
        "rpc_url": RPC_ENDPOINTS[chain],
    }


# ---------------------------------------------------------------------------
# Direct CLI usage
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    if len(sys.argv) < 2:
        print("Usage: python -m src.wallet <address> [chain]")
        sys.exit(1)
    addr = sys.argv[1]
    if len(sys.argv) >= 3:
        bal = get_balance(sys.argv[2], addr)
        print(bal)
    else:
        wallet = get_all_balances(addr)
        print(wallet.summary())
