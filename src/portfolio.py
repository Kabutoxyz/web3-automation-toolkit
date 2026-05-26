#!/usr/bin/env python3
"""
Portfolio report generator.

Combines wallet balances, token holdings, gas estimates, and approval
status into a single comprehensive report for a given address.
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from src.wallet import get_all_balances, WalletBalances, ChainBalance
from src.tokens import get_all_known_token_balances, TokenBalance
from src.gas import get_all_gas_prices, GasPrice, estimate_transfer_cost, TransferEstimate
from src.approvals import scan_all_chains, ApprovalInfo

logger = logging.getLogger(__name__)

ALL_CHAINS = ["ethereum", "base", "arbitrum", "optimism", "polygon"]


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ChainPortfolio:
    """Aggregated portfolio data for one chain."""
    chain: str
    native: Optional[ChainBalance] = None
    tokens: list[TokenBalance] = field(default_factory=list)
    gas: Optional[GasPrice] = None
    transfer_estimate: Optional[TransferEstimate] = None
    approvals: list[ApprovalInfo] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        if self.native and not self.native.success:
            return True
        if any(not t.success for t in self.tokens):
            return True
        if self.gas and not self.gas.success:
            return True
        return False


@dataclass
class PortfolioReport:
    """Full multi-chain portfolio report."""
    address: str
    generated_at: str
    chains: list[ChainPortfolio] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------

def build_portfolio(
    address: str,
    chains: Optional[list[str]] = None,
    include_tokens: bool = True,
    include_gas: bool = True,
    include_approvals: bool = True,
) -> PortfolioReport:
    """Build a full portfolio report for *address*.

    Parameters
    ----------
    address : str
        Wallet address.
    chains : list[str] | None
        Subset of chains. Defaults to all EVM chains.
    include_tokens : bool
        Whether to fetch ERC-20 balances.
    include_gas : bool
        Whether to include gas info and cost estimates.
    include_approvals : bool
        Whether to scan token approvals.

    Returns
    -------
    PortfolioReport
    """
    if chains is None:
        chains = ALL_CHAINS

    report = PortfolioReport(
        address=address,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )

    # --- Native balances -------------------------------------------------
    logger.info("Fetching native balances …")
    wallet_balances = get_all_balances(address, chains)
    native_map: dict[str, ChainBalance] = {b.chain: b for b in wallet_balances.balances}

    # --- Token balances --------------------------------------------------
    token_map: dict[str, list[TokenBalance]] = {}
    if include_tokens:
        logger.info("Fetching token balances …")
        token_map = get_all_known_token_balances(address, chains)

    # --- Gas prices ------------------------------------------------------
    gas_map: dict[str, GasPrice] = {}
    estimate_map: dict[str, TransferEstimate] = {}
    if include_gas:
        logger.info("Fetching gas prices …")
        gas_list = get_all_gas_prices(chains)
        gas_map = {g.chain: g for g in gas_list}
        for chain in chains:
            try:
                estimate_map[chain] = estimate_transfer_cost(chain, "eth_transfer")
            except Exception as exc:
                logger.warning("Gas estimate failed for %s: %s", chain, exc)

    # --- Approvals -------------------------------------------------------
    approval_map: dict[str, list[ApprovalInfo]] = {}
    if include_approvals:
        logger.info("Scanning approvals …")
        approval_map = scan_all_chains(address, chains)

    # --- Assemble per-chain data ----------------------------------------
    for chain in chains:
        cp = ChainPortfolio(chain=chain)
        cp.native = native_map.get(chain)
        cp.tokens = token_map.get(chain, [])
        cp.gas = gas_map.get(chain)
        cp.transfer_estimate = estimate_map.get(chain)
        cp.approvals = approval_map.get(chain, [])

        # Collect warnings
        if cp.native and not cp.native.success:
            report.warnings.append(f"Failed to fetch native balance on {chain}: {cp.native.error}")
        if cp.gas and not cp.gas.success:
            report.warnings.append(f"Failed to fetch gas on {chain}: {cp.gas.error}")

        report.chains.append(cp)

    return report


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def format_portfolio(report: PortfolioReport) -> str:
    """Render the portfolio report as a human-readable string."""
    lines = [
        "╔══════════════════════════════════════════════════════════════╗",
        "║               WEB3 PORTFOLIO REPORT                        ║",
        "╚══════════════════════════════════════════════════════════════╝",
        "",
        f"  Address : {report.address}",
        f"  Generated: {report.generated_at}",
        "",
    ]

    for cp in report.chains:
        lines.append(f"{'─' * 60}")
        lines.append(f"  🔗  {cp.chain.upper()}")
        lines.append(f"{'─' * 60}")

        # Native balance
        if cp.native:
            if cp.native.success:
                lines.append(f"  Native : {cp.native.balance_formatted:.6f} {cp.native.symbol}")
            else:
                lines.append(f"  Native : ❌ Error — {cp.native.error}")

        # Token balances
        if cp.tokens:
            lines.append("  Tokens :")
            for tb in cp.tokens:
                if tb.success and tb.balance_formatted > 0:
                    lines.append(f"    • {tb.token_symbol}: {tb.balance_formatted:,.4f}")
                elif tb.success:
                    lines.append(f"    • {tb.token_symbol}: 0")
                else:
                    lines.append(f"    • {tb.token_symbol}: ❌ {tb.error}")

        # Gas
        if cp.gas:
            if cp.gas.success:
                lines.append(f"  Gas    : base {cp.gas.base_fee_gwei:.2f} gwei, max {cp.gas.max_fee_gwei:.2f} gwei")
            else:
                lines.append(f"  Gas    : ❌ Error — {cp.gas.error}")

        # Transfer estimate
        if cp.transfer_estimate and cp.transfer_estimate.success:
            lines.append(
                f"  Transfer: ~{cp.transfer_estimate.cost_native:.8f} {cp.transfer_estimate.symbol}"
            )

        # Approvals
        active_approvals = [
            a for a in cp.approvals if a.success and a.allowance_raw > 0
        ]
        if active_approvals:
            lines.append(f"  Approvals ({len(active_approvals)} active):")
            for a in active_approvals:
                tag = "⚠️ UNLIMITED" if a.is_unlimited else "🔔 limited"
                lines.append(f"    • {a.token_symbol} → {a.spender_name} [{tag}]")
        else:
            lines.append("  Approvals: ✅ None")

        lines.append("")

    # Warnings
    if report.warnings:
        lines.append("⚠️  WARNINGS:")
        for w in report.warnings:
            lines.append(f"  - {w}")
        lines.append("")

    lines.append("─" * 60)
    lines.append("Generated by web3-automation-toolkit")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    if len(sys.argv) < 2:
        print("Usage: python -m src.portfolio <address> [chain1,chain2,…]")
        sys.exit(1)
    addr = sys.argv[1]
    ch = None
    if len(sys.argv) > 2:
        ch = [c.strip() for c in sys.argv[2].split(",")]
    rpt = build_portfolio(addr, ch)
    print(format_portfolio(rpt))
