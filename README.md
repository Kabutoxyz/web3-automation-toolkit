# Web3 Automation Toolkit

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen.svg)](tests/)
[![Chains](https://img.shields.io/badge/chains-6-purple.svg)](#supported-chains)

A **zero-API-key** multi-chain Web3 toolkit that runs entirely against **public RPC endpoints**. Check balances, monitor gas, scan token approvals, and generate full portfolio reports across Ethereum, Base, Arbitrum, Optimism, Polygon, and Solana.

---

## ✨ Features

- **Multi-chain native balance checker** — ETH, MATIC, SOL across 6 chains
- **ERC-20 token balances** — USDT, USDC, WETH, DAI, WBTC via `eth_call`
- **Gas price tracker** — base fee, max fee, priority fee from on-chain data
- **Transfer cost estimator** — ETH transfer, ERC-20 transfer, swap cost estimates
- **Token approval scanner** — checks allowances against known DeFi spenders
- **Portfolio report** — combines everything into a single formatted view
- **CLI with subcommands** — `balance`, `gas`, `tokens`, `approvals`, `portfolio`
- **No API keys needed** — uses only free public RPCs
- **Proper logging and error handling** — every module logs and gracefully degrades

## 🔗 Supported Chains

| Chain | RPC | Native Token |
|-------|-----|--------------|
| Ethereum | `ethereum-rpc.publicnode.com` | ETH |
| Base | `mainnet.base.org` | ETH |
| Arbitrum | `arb1.arbitrum.io/rpc` | ETH |
| Optimism | `mainnet.optimism.io` | ETH |
| Polygon | `polygon-bor-rpc.publicnode.com` | MATIC |
| Solana | `api.mainnet-beta.solana.com` | SOL |

## 📦 Installation

```bash
git clone https://github.com/your-org/web3-automation-toolkit.git
cd web3-automation-toolkit
pip install -r requirements.txt
```

Requires Python 3.10+.

## 🚀 Usage

### Check native balances across all chains

```bash
python cli.py balance 0x393b8179097abbCC967D8D25c82417F551783c06
```

### Check specific chains only

```bash
python cli.py balance 0x393b8179097abbCC967D8D25c82417F551783c06 --chains ethereum,base
```

### View gas prices and transfer costs

```bash
python cli.py gas
python cli.py gas ethereum arbitrum
```

### Check ERC-20 token balances

```bash
python cli.py tokens 0x393b8179097abbCC967D8D25c82417F551783c06
python cli.py tokens 0x393b8179097abbCC967D8D25c82417F551783c06 --chain ethereum
```

### Scan token approvals

```bash
python cli.py approvals 0x393b8179097abbCC967D8D25c82417F551783c06
```

### Full portfolio report

```bash
python cli.py portfolio 0x393b8179097abbCC967D8D25c82417F551783c06
python cli.py portfolio 0x393b8179097abbCC967D8D25c82417F551783c06 --chains ethereum,base --no-approvals
```

### Verbose mode

Add `-v` before any subcommand for debug logging:

```bash
python -v cli.py balance 0x393b8179097abbCC967D8D25c82417F551783c06
```

## 🏗 Architecture

```
web3-automation-toolkit/
├── cli.py              # Entry point — argparse subcommands
├── requirements.txt    # Python dependencies
├── README.md
├── src/
│   ├── __init__.py
│   ├── wallet.py       # Multi-chain native balance checker
│   ├── gas.py          # Gas price tracker + cost estimator
│   ├── tokens.py       # ERC-20 balance checker (eth_call)
│   ├── approvals.py    # Token approval scanner (allowance checks)
│   └── portfolio.py    # Combines all modules into one report
└── tests/
    └── test_wallet.py  # Integration tests against live RPCs
```

### Module Responsibilities

**`src/wallet.py`** — Calls `eth_getBalance` (EVM) or `getBalance` (Solana) via public JSON-RPC. Returns typed `ChainBalance` dataclasses. Supports single-chain and multi-chain queries with gentle rate-limiting.

**`src/gas.py`** — Calls `eth_gasPrice`, `eth_getBlockByNumber` (for base fee), and `eth_feeHistory` (for priority fee estimation). Computes conservative upper-bound transfer costs for ETH transfers (21k gas), ERC-20 transfers (65k gas), and swaps (180k gas).

**`src/tokens.py`** — Calls `eth_call` with the `balanceOf(address)` function selector (`0x70a08231`) to read ERC-20 balances without any API key. Includes a built-in registry of well-known tokens on each chain.

**`src/approvals.py`** — Calls `eth_call` with the `allowance(address,address)` selector (`0xdd62ed3e`) against known DeFi spender addresses (Uniswap, Aave, OpenSea Seaport, GMX, etc.). Reports unlimited vs. limited approvals.

**`src/portfolio.py`** — Orchestrates all modules and builds a formatted multi-chain portfolio report with warnings and approval highlights.

## 🧪 Running Tests

```bash
python -m pytest tests/ -v
```

Or directly:

```bash
python -m unittest tests.test_wallet -v
```

Tests hit real public RPCs and verify actual on-chain responses. They will pass as long as the RPC endpoints are reachable.

## ⚠️ Notes

- All data is fetched from **free public RPC endpoints**. These may have rate limits.
- The approval scanner checks a curated set of well-known DeFi spender contracts. It does not enumerate all possible spenders.
- Gas estimates are **conservative upper bounds** using `maxFeePerGas`.
- This tool is for **informational purposes only** — always verify on-chain data before transacting.

## 📄 License

MIT


<!-- Last updated: 2026-06-25 -->
