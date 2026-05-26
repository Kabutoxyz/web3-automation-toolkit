#!/usr/bin/env python3
"""
ERC-20 token balance checker using eth_call.

Queries on-chain balances for any ERC-20 token by calling the
``balanceOf(address)`` function selector via the public JSON-RPC endpoint.
No external API keys needed.
"""

import logging
from dataclasses import dataclass
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BALANCE_OF_SELECTOR = "0x70a08231"  # bytes4(keccak256("balanceOf(address)"))

EVM_RPCS: dict[str, str] = {
    "ethereum":  "https://ethereum-rpc.publicnode.com",
    "base":      "https://mainnet.base.org",
    "arbitrum":  "https://arb1.arbitrum.io/rpc",
    "optimism":  "https://mainnet.optimism.io",
    "polygon":   "https://polygon-bor-rpc.publicnode.com",
}

# Well-known token addresses for convenience / default behaviour
KNOWN_TOKENS: dict[str, dict[str, dict[str, str]]] = {
    "ethereum": {
        "USDT": {"address": "0xdAC17F958D2ee523a2206206994597C13D831ec7", "decimals": 6},
        "USDC": {"address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", "decimals": 6},
        "WETH": {"address": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", "decimals": 18},
        "DAI":  {"address": "0x6B175474E89094C44Da98b954EedeAC495271d0F", "decimals": 18},
        "WBTC": {"address": "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599", "decimals": 8},
    },
    "base": {
        "USDC": {"address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", "decimals": 6},
        "WETH": {"address": "0x4200000000000000000000000000000000000006", "decimals": 18},
    },
    "arbitrum": {
        "USDC": {"address": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831", "decimals": 6},
        "WETH": {"address": "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1", "decimals": 18},
        "USDT": {"address": "0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9", "decimals": 6},
    },
    "optimism": {
        "USDC": {"address": "0x0b2C639c533813f4Aa9D7837CAf62653d097Ff85", "decimals": 6},
        "WETH": {"address": "0x4200000000000000000000000000000000000006", "decimals": 18},
        "OP":   {"address": "0x4200000000000000000000000000000000000042", "decimals": 18},
    },
    "polygon": {
        "USDC": {"address": "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359", "decimals": 6},
        "WETH": {"address": "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619", "decimals": 18},
        "WMATIC": {"address": "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270", "decimals": 18},
    },
}

REQUEST_TIMEOUT = 15


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class TokenBalance:
    """Result container for a single ERC-20 balance query."""
    chain: str
    token_symbol: str
    token_address: str
    wallet_address: str
    balance_raw: int
    balance_formatted: float
    decimals: int
    success: bool = True
    error: Optional[str] = None

    def __str__(self) -> str:
        if self.success:
            return (
                f"{self.chain.title()} | {self.token_symbol}: "
                f"{self.balance_formatted:,.4f}"
            )
        return f"{self.chain.title()} | {self.token_symbol}: ERROR — {self.error}"


# ---------------------------------------------------------------------------
# RPC helpers
# ---------------------------------------------------------------------------

def _pad_address(address: str) -> str:
    """Left-pad an Ethereum address to 32 bytes (64 hex chars, no 0x prefix)."""
    return address.lower().replace("0x", "").zfill(64)


def _eth_call(rpc_url: str, to: str, data: str) -> str:
    """Execute an eth_call and return the hex result."""
    payload = {
        "jsonrpc": "2.0",
        "method": "eth_call",
        "params": [{"to": to, "data": data}, "latest"],
        "id": 1,
    }
    resp = requests.post(rpc_url, json=payload, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    body = resp.json()
    if "error" in body:
        raise RuntimeError(f"eth_call error: {body['error']}")
    return body["result"]


def _fetch_token_name(rpc_url: str, token_address: str) -> str:
    """Try to fetch the on-chain symbol(); fallback to shortened address."""
    selector = "0x95d89b41"  # symbol()
    try:
        raw = _eth_call(rpc_url, token_address, selector)
        # Result is ABI-encoded string — decode the length & data
        if raw and len(raw) > 130:
            length = int(raw[66:130], 16)
            hex_str = raw[130:130 + length * 2]
            return bytes.fromhex(hex_str).decode("utf-8", errors="replace")
        return f"{token_address[:10]}…"
    except Exception:
        return f"{token_address[:10]}…"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_token_balance(
    chain: str,
    wallet_address: str,
    token_address: str,
    token_symbol: str = "",
    decimals: int = 18,
) -> TokenBalance:
    """Fetch an ERC-20 token balance via eth_call.

    Parameters
    ----------
    chain : str
        EVM chain name.
    wallet_address : str
        Address whose balance to query.
    token_address : str
        ERC-20 contract address.
    token_symbol : str
        Human-readable symbol (used for display only).
    decimals : int
        Token decimals for formatting.

    Returns
    -------
    TokenBalance
    """
    chain = chain.lower().strip()
    if chain not in EVM_RPCS:
        raise ValueError(f"Unsupported chain: {chain!r}")
    rpc = EVM_RPCS[chain]
    try:
        data = BALANCE_OF_SELECTOR + _pad_address(wallet_address)
        raw_hex = _eth_call(rpc, token_address, data)
        raw_balance = int(raw_hex, 16)
        formatted = raw_balance / (10 ** decimals)
        if not token_symbol:
            token_symbol = _fetch_token_name(rpc, token_address)
        logger.info(
            "%s %s on %s: %.4f",
            token_symbol, token_address[:10], chain, formatted,
        )
        return TokenBalance(
            chain=chain,
            token_symbol=token_symbol,
            token_address=token_address,
            wallet_address=wallet_address,
            balance_raw=raw_balance,
            balance_formatted=formatted,
            decimals=decimals,
        )
    except Exception as exc:
        logger.error("Token balance fetch failed: %s", exc)
        return TokenBalance(
            chain=chain,
            token_symbol=token_symbol or "?",
            token_address=token_address,
            wallet_address=wallet_address,
            balance_raw=0,
            balance_formatted=0.0,
            decimals=decimals,
            success=False,
            error=str(exc),
        )


def get_known_token_balances(
    chain: str,
    wallet_address: str,
) -> list[TokenBalance]:
    """Fetch balances for all well-known tokens on *chain*.

    Returns
    -------
    list[TokenBalance]
    """
    chain = chain.lower().strip()
    if chain not in KNOWN_TOKENS:
        logger.warning("No known-token registry for %s; returning empty list.", chain)
        return []
    results: list[TokenBalance] = []
    for symbol, info in KNOWN_TOKENS[chain].items():
        results.append(
            get_token_balance(
                chain=chain,
                wallet_address=wallet_address,
                token_address=info["address"],
                token_symbol=symbol,
                decimals=info["decimals"],
            )
        )
    return results


def get_all_known_token_balances(
    wallet_address: str,
    chains: Optional[list[str]] = None,
) -> dict[str, list[TokenBalance]]:
    """Fetch known token balances across all (or selected) chains.

    Returns
    -------
    dict mapping chain name -> list of TokenBalance
    """
    if chains is None:
        chains = list(KNOWN_TOKENS.keys())
    out: dict[str, list[TokenBalance]] = {}
    for chain in chains:
        out[chain] = get_known_token_balances(chain, wallet_address)
    return out


def format_token_report(wallet_address: str, chains: Optional[list[str]] = None) -> str:
    """Produce a human-readable token balance report."""
    data = get_all_known_token_balances(wallet_address, chains)
    lines = [f"Token Balances for {wallet_address}", "=" * 60]
    for chain, balances in data.items():
        lines.append(f"\n  [{chain.upper()}]")
        if not balances:
            lines.append("    (no tracked tokens)")
            continue
        for tb in balances:
            lines.append(f"    {tb}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    if len(sys.argv) < 2:
        print("Usage: python -m src.tokens <wallet_address> [chain]")
        sys.exit(1)
    address = sys.argv[1]
    chain_arg = sys.argv[2] if len(sys.argv) > 2 else None
    chains = [chain_arg] if chain_arg else None
    print(format_token_report(address, chains))
