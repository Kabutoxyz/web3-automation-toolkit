#!/usr/bin/env python3
"""
web3-automation-toolkit CLI entry point.

Provides subcommands:
  balance    — Check native-token balances across chains
  gas        — View gas prices and transfer-cost estimates
  tokens     — Check ERC-20 token balances
  approvals  — Scan for token approvals
  portfolio  — Full portfolio report (all of the above)

Usage:
  python cli.py balance 0xABC...
  python cli.py gas ethereum base
  python cli.py tokens 0xABC... --chain ethereum
  python cli.py approvals 0xABC...
  python cli.py portfolio 0xABC... --chains ethereum,base
"""

import argparse
import logging
import sys

# ---------------------------------------------------------------------------
# Argument parsers
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="web3-toolkit",
        description="Multi-chain Web3 automation toolkit — balances, gas, tokens, approvals.",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable debug-level logging.",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # ---- balance --------------------------------------------------------
    p_bal = subparsers.add_parser(
        "balance",
        help="Check native-token balances on one or more chains.",
    )
    p_bal.add_argument("address", help="Wallet address to query.")
    p_bal.add_argument(
        "--chains",
        default=None,
        help="Comma-separated chain list (default: all supported).",
    )

    # ---- gas ------------------------------------------------------------
    p_gas = subparsers.add_parser(
        "gas",
        help="Show gas prices and transfer cost estimates.",
    )
    p_gas.add_argument(
        "chains",
        nargs="*",
        default=None,
        help="Chain names to query (default: all).",
    )

    # ---- tokens ---------------------------------------------------------
    p_tok = subparsers.add_parser(
        "tokens",
        help="Check ERC-20 token balances.",
    )
    p_tok.add_argument("address", help="Wallet address to query.")
    p_tok.add_argument(
        "--chain",
        default=None,
        help="Single chain to query (default: all).",
    )

    # ---- approvals ------------------------------------------------------
    p_appr = subparsers.add_parser(
        "approvals",
        help="Scan for active token approvals.",
    )
    p_appr.add_argument("address", help="Wallet address (owner) to scan.")
    p_appr.add_argument(
        "--chains",
        default=None,
        help="Comma-separated chain list (default: all).",
    )

    # ---- portfolio ------------------------------------------------------
    p_port = subparsers.add_parser(
        "portfolio",
        help="Generate a full portfolio report.",
    )
    p_port.add_argument("address", help="Wallet address to report on.")
    p_port.add_argument(
        "--chains",
        default=None,
        help="Comma-separated chain list (default: all).",
    )
    p_port.add_argument("--no-tokens", action="store_true", help="Skip token balances.")
    p_port.add_argument("--no-gas", action="store_true", help="Skip gas info.")
    p_port.add_argument("--no-approvals", action="store_true", help="Skip approval scan.")

    return parser


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def _parse_chains(raw: str | None) -> list[str] | None:
    if raw is None:
        return None
    return [c.strip().lower() for c in raw.split(",") if c.strip()]


def cmd_balance(args: argparse.Namespace) -> None:
    from src.wallet import get_all_balances
    chains = _parse_chains(args.chains)
    result = get_all_balances(args.address, chains)
    print(result.summary())


def cmd_gas(args: argparse.Namespace) -> None:
    from src.gas import format_gas_report
    chains = args.chains if args.chains else None
    print(format_gas_report(chains))


def cmd_tokens(args: argparse.Namespace) -> None:
    from src.tokens import format_token_report
    chains = [args.chain] if args.chain else None
    print(format_token_report(args.address, chains))


def cmd_approvals(args: argparse.Namespace) -> None:
    from src.approvals import format_approval_report
    chains = _parse_chains(args.chains)
    print(format_approval_report(args.address, chains))


def cmd_portfolio(args: argparse.Namespace) -> None:
    from src.portfolio import build_portfolio, format_portfolio
    chains = _parse_chains(args.chains)
    report = build_portfolio(
        address=args.address,
        chains=chains,
        include_tokens=not args.no_tokens,
        include_gas=not args.no_gas,
        include_approvals=not args.no_approvals,
    )
    print(format_portfolio(report))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

COMMAND_MAP = {
    "balance": cmd_balance,
    "gas": cmd_gas,
    "tokens": cmd_tokens,
    "approvals": cmd_approvals,
    "portfolio": cmd_portfolio,
}


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.  Returns an exit code (0 = success)."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    # Logging setup
    level = logging.DEBUG if args.verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    if not args.command:
        parser.print_help()
        return 1

    handler = COMMAND_MAP.get(args.command)
    if handler is None:
        parser.print_help()
        return 1

    try:
        handler(args)
        return 0
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
    except Exception as exc:
        logging.getLogger(__name__).exception("Command failed")
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
