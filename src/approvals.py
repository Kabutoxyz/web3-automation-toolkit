#!/usr/bin/env python3
"""
Token approval scanner.

Checks whether an address has granted unlimited (or limited) ERC-20
token approvals to common DeFi spender contracts.  Works by calling
``allowance(owner, spender)`` via ``eth_call`` on public RPCs.

Only on-chain data — no external API keys required.
"""

import logging
from dataclasses import dataclass
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
ALLOWANCE_SELECTOR = "0xdd62ed3e"  # bytes4(keccak256("allowance(address,address)"))
MAX_UINT256 = 2**256 - 1

EVM_RPCS: dict[str, str] = {
    "ethereum":  "https://ethereum-rpc.publicnode.com",
    "base":      "https://mainnet.base.org",
    "arbitrum":  "https://arb1.arbitrum.io/rpc",
    "optimism":  "https://mainnet.optimism.io",
    "polygon":   "https://polygon-bor-rpc.publicnode.com",
}

# Well-known spender contracts that people commonly approve
KNOWN_SPENDERS: dict[str, list[dict[str, str]]] = {
    "ethereum": [
        {"name": "Uniswap V3 Router", "address": "0xE592427A0AEce92De3Edee1F18E0157C05861564"},
        {"name": "Uniswap Universal Router", "address": "0x3fC91A3afd70395Cd496C647d5a6CC9D4B2b7FAD"},
        {"name": "SushiSwap Router", "address": "0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F"},
        {"name": "1inch V5 Router", "address": "0x1111111254EEB25477B68fb85Ed929f73A960582"},
        {"name": "OpenSea Seaport", "address": "0x00000000000000ADc04C56Bf30aC9d3c0aAF14dC"},
        {"name": "Aave V3 Pool", "address": "0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2"},
        {"name": "Compound cDAI", "address": "0x5d3a536E4D6DbD6114cc1Ead35777bAB948E3643"},
    ],
    "base": [
        {"name": "Uniswap V3 Router (Base)", "address": "0x2626664c2603336E57B271c5C0b26F421741e481"},
        {"name": "BaseBridge", "address": "0x3154Cf16ccdb4C6d922629664174b904d80F2C35"},
    ],
    "arbitrum": [
        {"name": "Uniswap V3 Router (Arb)", "address": "0xE592427A0AEce92De3Edee1F18E0157C05861564"},
        {"name": "GMX Router", "address": "0xaBBc5F99639c9B6bCb58544ddf04EFA6802F4064"},
    ],
    "optimism": [
        {"name": "Uniswap V3 Router (OP)", "address": "0xE592427A0AEce92De3Edee1F18E0157C05861564"},
    ],
    "polygon": [
        {"name": "Uniswap V3 Router (Polygon)", "address": "0xE592427A0AEce92De3Edee1F18E0157C05861564"},
        {"name": "QuickSwap Router", "address": "0xa5E0829CaCEd8fFDD4De3c43696c57F7D7A678ff"},
    ],
}

# Known tokens (subset for approval scanning)
KNOWN_TOKENS: dict[str, list[dict[str, object]]] = {
    "ethereum": [
        {"symbol": "USDT", "address": "0xdAC17F958D2ee523a2206206994597C13D831ec7", "decimals": 6},
        {"symbol": "USDC", "address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", "decimals": 6},
        {"symbol": "WETH", "address": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", "decimals": 18},
        {"symbol": "DAI",  "address": "0x6B175474E89094C44Da98b954EedeAC495271d0F", "decimals": 18},
        {"symbol": "WBTC", "address": "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599", "decimals": 8},
    ],
    "base": [
        {"symbol": "USDC", "address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", "decimals": 6},
        {"symbol": "WETH", "address": "0x4200000000000000000000000000000000000006", "decimals": 18},
    ],
    "arbitrum": [
        {"symbol": "USDC", "address": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831", "decimals": 6},
        {"symbol": "WETH", "address": "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1", "decimals": 18},
    ],
    "optimism": [
        {"symbol": "USDC", "address": "0x0b2C639c533813f4Aa9D7837CAf62653d097Ff85", "decimals": 6},
        {"symbol": "WETH", "address": "0x4200000000000000000000000000000000000006", "decimals": 18},
    ],
    "polygon": [
        {"symbol": "USDC", "address": "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359", "decimals": 6},
        {"symbol": "WMATIC", "address": "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270", "decimals": 18},
    ],
}

REQUEST_TIMEOUT = 15


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ApprovalInfo:
    """Result of an allowance check for a token-spender pair."""
    chain: str
    token_symbol: str
    token_address: str
    spender_name: str
    spender_address: str
    owner_address: str
    allowance_raw: int
    is_unlimited: bool
    success: bool = True
    error: Optional[str] = None

    def __str__(self) -> str:
        if not self.success:
            return (
                f"{self.token_symbol} → {self.spender_name}: ERROR — {self.error}"
            )
        if self.is_unlimited:
            status = "⚠️  UNLIMITED"
        elif self.allowance_raw == 0:
            status = "✅ None"
        else:
            status = f"🔔 Limited ({self.allowance_raw})"
        return f"{self.token_symbol} → {self.spender_name}: {status}"


# ---------------------------------------------------------------------------
# RPC helpers
# ---------------------------------------------------------------------------

def _pad_address(address: str) -> str:
    return address.lower().replace("0x", "").zfill(64)


def _eth_call(rpc_url: str, to: str, data: str) -> str:
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


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def check_allowance(
    chain: str,
    owner: str,
    spender: str,
    token_address: str,
    token_symbol: str = "",
) -> ApprovalInfo:
    """Check the allowance that *owner* has granted to *spender* for a token.

    Parameters
    ----------
    chain : str
        EVM chain name.
    owner : str
        Address that approved the token.
    spender : str
        Address of the spender contract.
    token_address : str
        ERC-20 contract address.
    token_symbol : str
        Human-readable label (optional).

    Returns
    -------
    ApprovalInfo
    """
    chain = chain.lower().strip()
    if chain not in EVM_RPCS:
        raise ValueError(f"Unsupported chain: {chain!r}")
    rpc = EVM_RPCS[chain]
    try:
        calldata = ALLOWANCE_SELECTOR + _pad_address(owner) + _pad_address(spender)
        raw_hex = _eth_call(rpc, token_address, calldata)
        allowance = int(raw_hex, 16)
        is_unlimited = allowance >= MAX_UINT256 // 2  # treat near-max as unlimited
        return ApprovalInfo(
            chain=chain,
            token_symbol=token_symbol or f"{token_address[:10]}…",
            token_address=token_address,
            spender_name=spender[:10] + "…",
            spender_address=spender,
            owner_address=owner,
            allowance_raw=allowance,
            is_unlimited=is_unlimited,
        )
    except Exception as exc:
        logger.error("Allowance check failed: %s", exc)
        return ApprovalInfo(
            chain=chain,
            token_symbol=token_symbol or "?",
            token_address=token_address,
            spender_name=spender[:10] + "…",
            spender_address=spender,
            owner_address=owner,
            allowance_raw=0,
            is_unlimited=False,
            success=False,
            error=str(exc),
        )


def scan_approvals(
    chain: str,
    owner: str,
    tokens: Optional[list[dict]] = None,
    spenders: Optional[list[dict]] = None,
) -> list[ApprovalInfo]:
    """Scan a set of token-spender pairs for approvals on a chain.

    If *tokens* or *spenders* are ``None``, the built-in known lists are used.

    Returns
    -------
    list[ApprovalInfo]
    """
    chain = chain.lower().strip()
    if tokens is None:
        tokens = KNOWN_TOKENS.get(chain, [])
    if spenders is None:
        spenders = KNOWN_SPENDERS.get(chain, [])

    results: list[ApprovalInfo] = []
    for token in tokens:
        for spender in spenders:
            info = check_allowance(
                chain=chain,
                owner=owner,
                spender=spender["address"],
                token_address=token["address"],
                token_symbol=token["symbol"],
            )
            # Attach human-readable spender name
            info.spender_name = spender["name"]
            results.append(info)
    return results


def scan_all_chains(
    owner: str,
    chains: Optional[list[str]] = None,
) -> dict[str, list[ApprovalInfo]]:
    """Scan approvals across multiple chains.

    Returns
    -------
    dict mapping chain name → list of ApprovalInfo
    """
    if chains is None:
        chains = list(EVM_RPCS.keys())
    out: dict[str, list[ApprovalInfo]] = {}
    for chain in chains:
        logger.info("Scanning approvals on %s …", chain)
        out[chain] = scan_approvals(chain, owner)
    return out


def format_approval_report(owner: str, chains: Optional[list[str]] = None) -> str:
    """Build a human-readable approval report."""
    data = scan_all_chains(owner, chains)
    lines = [f"Approval Scan for {owner}", "=" * 70]
    for chain, approvals in data.items():
        lines.append(f"\n  [{chain.upper()}]")
        active = [a for a in approvals if a.success and a.allowance_raw > 0]
        if not active:
            lines.append("    ✅ No active approvals found for tracked tokens.")
        else:
            for a in active:
                lines.append(f"    {a}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    if len(sys.argv) < 2:
        print("Usage: python -m src.approvals <owner_address> [chain]")
        sys.exit(1)
    owner_addr = sys.argv[1]
    chain_filter = sys.argv[2] if len(sys.argv) > 2 else None
    chains = [chain_filter] if chain_filter else None
    print(format_approval_report(owner_addr, chains))
