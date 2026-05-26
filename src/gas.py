#!/usr/bin/env python3
"""
Gas price tracker and transfer cost estimator.

Queries on-chain gas prices via eth_gasPrice / eth_feeHistory on public RPCs
and computes estimated costs for simple ETH transfers and ERC-20 transfers.
"""

import logging
import time
from dataclasses import dataclass
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
GAS_LIMIT_SIMPLE_TRANSFER = 21_000
GAS_LIMIT_ERC20_TRANSFER = 65_000
GAS_LIMIT_SWAP = 180_000

EVM_RPCS: dict[str, str] = {
    "ethereum":  "https://ethereum-rpc.publicnode.com",
    "base":      "https://mainnet.base.org",
    "arbitrum":  "https://arb1.arbitrum.io/rpc",
    "optimism":  "https://mainnet.optimism.io",
    "polygon":   "https://polygon-bor-rpc.publicnode.com",
}

NATIVE_DECIMALS: dict[str, int] = {
    "ethereum": 18,
    "base": 18,
    "arbitrum": 18,
    "optimism": 18,
    "polygon": 18,
}

NATIVE_SYMBOL: dict[str, str] = {
    "ethereum": "ETH",
    "base": "ETH",
    "arbitrum": "ETH",
    "optimism": "ETH",
    "polygon": "MATIC",
}

REQUEST_TIMEOUT = 15


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class GasPrice:
    """Gas price information from a chain."""
    chain: str
    base_fee_gwei: float
    max_fee_gwei: float
    priority_fee_gwei: float
    success: bool = True
    error: Optional[str] = None

    def __str__(self) -> str:
        if self.success:
            return (
                f"{self.chain.title()}: base={self.base_fee_gwei:.2f} gwei, "
                f"max={self.max_fee_gwei:.2f} gwei, "
                f"priority={self.priority_fee_gwei:.2f} gwei"
            )
        return f"{self.chain.title()}: ERROR — {self.error}"


@dataclass
class TransferEstimate:
    """Estimated cost of a transaction type on a chain."""
    chain: str
    tx_type: str
    gas_limit: int
    gas_price_gwei: float
    cost_native: float
    symbol: str
    success: bool = True
    error: Optional[str] = None

    def __str__(self) -> str:
        if self.success:
            return (
                f"{self.chain.title()} — {self.tx_type}: "
                f"{self.cost_native:.8f} {self.symbol} "
                f"(gas_limit={self.gas_limit}, gas_price={self.gas_price_gwei:.2f} gwei)"
            )
        return f"{self.chain.title()} — {self.tx_type}: ERROR — {self.error}"


# ---------------------------------------------------------------------------
# RPC helpers
# ---------------------------------------------------------------------------

def _rpc_call(rpc_url: str, method: str, params: list) -> dict:
    """Execute a JSON-RPC call and return the result field."""
    payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
    resp = requests.post(rpc_url, json=payload, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"RPC error ({method}): {data['error']}")
    return data["result"]


def _get_gas_price_raw(rpc_url: str) -> int:
    """Return the current gas price in wei."""
    result = _rpc_call(rpc_url, "eth_gasPrice", [])
    return int(result, 16)


def _get_block_base_fee(rpc_url: str) -> int:
    """Return the base fee of the latest block in wei."""
    block = _rpc_call(rpc_url, "eth_getBlockByNumber", ["latest", False])
    base_fee_hex = block.get("baseFeePerGas", "0x0")
    return int(base_fee_hex, 16)


def _get_fee_history(rpc_url: str, block_count: int = 4) -> dict:
    """Return fee history for the last N blocks."""
    result = _rpc_call(
        rpc_url,
        "eth_feeHistory",
        [hex(block_count), "latest", [25, 75]],
    )
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_gas_price(chain: str) -> GasPrice:
    """Fetch current gas price info for an EVM chain.

    Parameters
    ----------
    chain : str
        One of: ethereum, base, arbitrum, optimism, polygon.

    Returns
    -------
    GasPrice
    """
    chain = chain.lower().strip()
    if chain not in EVM_RPCS:
        raise ValueError(f"Unsupported chain: {chain!r}. Choose from {list(EVM_RPCS)}")
    rpc = EVM_RPCS[chain]
    try:
        raw_gas = _get_gas_price_raw(rpc)
        gas_gwei = raw_gas / 1e9

        # Try to get base fee from latest block
        try:
            base_fee_raw = _get_block_base_fee(rpc)
            base_fee_gwei = base_fee_raw / 1e9
        except Exception:
            base_fee_gwei = gas_gwei * 0.8  # fallback estimate

        # Try fee history for priority fee estimation
        try:
            history = _get_fee_history(rpc)
            rewards = history.get("reward", [])
            if rewards:
                avg_priority = sum(int(r[1], 16) for r in rewards) / len(rewards) / 1e9
            else:
                avg_priority = max(gas_gwei - base_fee_gwei, 0.0)
        except Exception:
            avg_priority = max(gas_gwei - base_fee_gwei, 1.0)

        max_fee = base_fee_gwei * 2 + avg_priority

        logger.info("Gas on %s: base=%.2f gwei, max=%.2f gwei", chain, base_fee_gwei, max_fee)
        return GasPrice(
            chain=chain,
            base_fee_gwei=base_fee_gwei,
            max_fee_gwei=max_fee,
            priority_fee_gwei=avg_priority,
        )
    except Exception as exc:
        logger.error("Failed to get gas price on %s: %s", chain, exc)
        return GasPrice(
            chain=chain,
            base_fee_gwei=0.0,
            max_fee_gwei=0.0,
            priority_fee_gwei=0.0,
            success=False,
            error=str(exc),
        )


def get_all_gas_prices(chains: Optional[list[str]] = None) -> list[GasPrice]:
    """Fetch gas prices for multiple chains."""
    if chains is None:
        chains = list(EVM_RPCS.keys())
    results: list[GasPrice] = []
    for chain in chains:
        results.append(get_gas_price(chain))
        time.sleep(0.15)
    return results


def estimate_transfer_cost(
    chain: str,
    tx_type: str = "eth_transfer",
) -> TransferEstimate:
    """Estimate the cost of a transfer on a given chain.

    Parameters
    ----------
    chain : str
        EVM chain name.
    tx_type : str
        One of: eth_transfer, erc20_transfer, swap.

    Returns
    -------
    TransferEstimate
    """
    gas_limits = {
        "eth_transfer": GAS_LIMIT_SIMPLE_TRANSFER,
        "erc20_transfer": GAS_LIMIT_ERC20_TRANSFER,
        "swap": GAS_LIMIT_SWAP,
    }
    if tx_type not in gas_limits:
        raise ValueError(f"Unknown tx_type: {tx_type!r}. Choose from {list(gas_limits)}")

    chain = chain.lower().strip()
    gas_info = get_gas_price(chain)
    if not gas_info.success:
        return TransferEstimate(
            chain=chain,
            tx_type=tx_type,
            gas_limit=gas_limits[tx_type],
            gas_price_gwei=0.0,
            cost_native=0.0,
            symbol=NATIVE_SYMBOL.get(chain, "???"),
            success=False,
            error=gas_info.error,
        )

    gas_limit = gas_limits[tx_type]
    # Use max_fee to give a conservative upper bound
    cost_wei = gas_limit * int(gas_info.max_fee_gwei * 1e9)
    cost_native = cost_wei / 1e18
    symbol = NATIVE_SYMBOL.get(chain, "???")

    return TransferEstimate(
        chain=chain,
        tx_type=tx_type,
        gas_limit=gas_limit,
        gas_price_gwei=gas_info.max_fee_gwei,
        cost_native=cost_native,
        symbol=symbol,
    )


def estimate_all_costs(chains: Optional[list[str]] = None) -> list[list[TransferEstimate]]:
    """Estimate eth_transfer, erc20_transfer, and swap costs on multiple chains.

    Returns a list of lists: one inner list per chain with three estimates.
    """
    if chains is None:
        chains = list(EVM_RPCS.keys())
    all_estimates: list[list[TransferEstimate]] = []
    for chain in chains:
        chain_estimates: list[TransferEstimate] = []
        for tx_type in ("eth_transfer", "erc20_transfer", "swap"):
            chain_estimates.append(estimate_transfer_cost(chain, tx_type))
            time.sleep(0.1)
        all_estimates.append(chain_estimates)
    return all_estimates


def format_gas_report(chains: Optional[list[str]] = None) -> str:
    """Build a human-readable gas report for the given chains."""
    prices = get_all_gas_prices(chains)
    lines = ["Gas Price Report", "=" * 60]
    for gp in prices:
        lines.append(f"  {gp}")
    lines.append("")
    lines.append("Transfer Cost Estimates")
    lines.append("-" * 60)
    for estimates in estimate_all_costs(chains):
        for est in estimates:
            lines.append(f"  {est}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Direct CLI usage
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    chain_filter = sys.argv[1:] if len(sys.argv) > 1 else None
    print(format_gas_report(chain_filter))
