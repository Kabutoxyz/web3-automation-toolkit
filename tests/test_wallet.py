#!/usr/bin/env python3
"""
Tests for src.wallet — multi-chain balance checker.

These tests hit real public RPC endpoints.  They use a known address
(0x393b8179097abbCC967D8D25c82417F551783c06) expected to have some balance
on at least one chain.  No mocks — every assertion validates actual network
responses.
"""

import sys
import os
import unittest

# Ensure the repo root is on the path so `import src.wallet` works
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.wallet import (
    get_balance,
    get_all_balances,
    get_chain_info,
    ChainBalance,
    WalletBalances,
    RPC_ENDPOINTS,
    CHAIN_NATIVE_SYMBOL,
    CHAIN_DECIMALS,
)

# A wallet known to hold some assets
TEST_ADDRESS = "0x393b8179097abbCC967D8D25c82417F551783c06"


class TestChainInfo(unittest.TestCase):
    """get_chain_info() should return metadata for every supported chain."""

    def test_all_chains_have_metadata(self):
        for chain in RPC_ENDPOINTS:
            info = get_chain_info(chain)
            self.assertIn("name", info)
            self.assertIn("symbol", info)
            self.assertIn("decimals", info)
            self.assertIn("rpc_url", info)
            self.assertEqual(info["name"], chain)

    def test_unsupported_chain_raises(self):
        with self.assertRaises(ValueError):
            get_chain_info("solana_mainnet_does_not_exist")


class TestEvmBalance(unittest.TestCase):
    """Integration tests that hit live public RPCs for EVM chains."""

    def test_ethereum_balance(self):
        result = get_balance("ethereum", TEST_ADDRESS)
        self.assertIsInstance(result, ChainBalance)
        self.assertEqual(result.chain, "ethereum")
        self.assertEqual(result.symbol, "ETH")
        self.assertTrue(result.success, msg=f"Error: {result.error}")
        self.assertGreaterEqual(result.balance_raw, 0)
        self.assertGreaterEqual(result.balance_formatted, 0.0)

    def test_base_balance(self):
        result = get_balance("base", TEST_ADDRESS)
        self.assertIsInstance(result, ChainBalance)
        self.assertEqual(result.chain, "base")
        self.assertTrue(result.success, msg=f"Error: {result.error}")

    def test_arbitrum_balance(self):
        result = get_balance("arbitrum", TEST_ADDRESS)
        self.assertIsInstance(result, ChainBalance)
        self.assertEqual(result.chain, "arbitrum")
        self.assertTrue(result.success, msg=f"Error: {result.error}")

    def test_optimism_balance(self):
        result = get_balance("optimism", TEST_ADDRESS)
        self.assertIsInstance(result, ChainBalance)
        self.assertEqual(result.chain, "optimism")
        self.assertTrue(result.success, msg=f"Error: {result.error}")

    def test_polygon_balance(self):
        result = get_balance("polygon", TEST_ADDRESS)
        self.assertIsInstance(result, ChainBalance)
        self.assertEqual(result.chain, "polygon")
        self.assertEqual(result.symbol, "MATIC")
        self.assertTrue(result.success, msg=f"Error: {result.error}")


class TestSolanaBalance(unittest.TestCase):
    """Integration test for Solana balance (different RPC protocol)."""

    def test_solana_balance(self):
        # Use a known Solana address (Binance cold wallet)
        sol_addr = "2ojv9BAiHUrvsm9gxDe7fJSzbNZSoTb3AZXGTGKqGeHM"
        result = get_balance("solana", sol_addr)
        self.assertIsInstance(result, ChainBalance)
        self.assertEqual(result.chain, "solana")
        self.assertEqual(result.symbol, "SOL")
        # This address may or may not have balance; just ensure the call works
        self.assertTrue(result.success, msg=f"Error: {result.error}")
        self.assertGreaterEqual(result.balance_raw, 0)


class TestGetAllBalances(unittest.TestCase):
    """get_all_balances should query multiple chains and return aggregated data."""

    def test_all_chains(self):
        wallet = get_all_balances(TEST_ADDRESS)
        self.assertIsInstance(wallet, WalletBalances)
        self.assertEqual(wallet.address, TEST_ADDRESS)
        # Should have one result per chain in RPC_ENDPOINTS
        self.assertEqual(len(wallet.balances), len(RPC_ENDPOINTS))
        # At least one should succeed (assuming the RPCs are reachable)
        successes = [b for b in wallet.balances if b.success]
        self.assertGreater(len(successes), 0, "At least one chain should return successfully")

    def test_subset_of_chains(self):
        chains = ["ethereum", "base"]
        wallet = get_all_balances(TEST_ADDRESS, chains=chains)
        self.assertEqual(len(wallet.balances), 2)
        chain_names = {b.chain for b in wallet.balances}
        self.assertEqual(chain_names, {"ethereum", "base"})

    def test_summary_string(self):
        wallet = get_all_balances(TEST_ADDRESS, chains=["ethereum"])
        text = wallet.summary()
        self.assertIn(TEST_ADDRESS, text)
        self.assertIn("ethereum", text.lower())


class TestBalanceValidation(unittest.TestCase):
    """Edge-case / validation tests."""

    def test_unsupported_chain_raises(self):
        with self.assertRaises(ValueError):
            get_balance("avalanche", TEST_ADDRESS)

    def test_chain_balance_str_success(self):
        cb = ChainBalance(
            chain="ethereum", address=TEST_ADDRESS,
            balance_raw=1500000000000000000,
            balance_formatted=1.5, symbol="ETH",
        )
        self.assertIn("1.500000", str(cb))
        self.assertIn("ETH", str(cb))

    def test_chain_balance_str_error(self):
        cb = ChainBalance(
            chain="ethereum", address=TEST_ADDRESS,
            balance_raw=0, balance_formatted=0.0,
            symbol="ETH", success=False, error="timeout",
        )
        self.assertIn("ERROR", str(cb))
        self.assertIn("timeout", str(cb))

    def test_decimals_consistency(self):
        for chain, rpc in RPC_ENDPOINTS.items():
            self.assertIn(chain, CHAIN_NATIVE_SYMBOL)
            self.assertIn(chain, CHAIN_DECIMALS)
            self.assertIn(chain, RPC_ENDPOINTS)


if __name__ == "__main__":
    unittest.main(verbosity=2)
