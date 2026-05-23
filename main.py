#!/usr/bin/env python3
"""
Web3 Automation Toolkit - Multi-chain Explorer
Checks balances and transactions across chains
"""
import requests
from datetime import datetime

def get_eth_balance(address):
    """Get ETH balance from Etherscan"""
    url = "https://api.etherscan.io/api"
    params = {
        'module': 'account',
        'action': 'balance',
        'address': address,
        'tag': 'latest'
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data['status'] == '1':
                balance = int(data['result']) / 10**18
                print(f"\n💎 Ethereum Balance")
                print(f"Address: {address[:20]}...")
                print(f"Balance: {balance:.6f} ETH")
                return True
        print(f"❌ Error: {data.get('message', 'Unknown')}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def get_eth_transactions(address, limit=5):
    """Get recent ETH transactions"""
    url = "https://api.etherscan.io/api"
    params = {
        'module': 'account',
        'action': 'txlist',
        'address': address,
        'startblock': 0,
        'endblock': 99999999,
        'page': 1,
        'offset': limit,
        'sort': 'desc'
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data['status'] == '1':
                print(f"\n📝 Recent Transactions")
                print("-" * 60)
                for tx in data['result'][:limit]:
                    value = int(tx['value']) / 10**18
                    from_addr = tx['from'][:15] + '...'
                    to_addr = tx['to'][:15] + '...' if tx['to'] else 'Contract'
                    status = "✅" else "❌"
                    print(f"  {status} {value:.6f} ETH | {from_addr} → {to_addr}")
                return True
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def get_gas_tracker():
    """Get current gas prices"""
    url = "https://api.etherscan.io/api"
    params = {'module': 'gastracker', 'action': 'gasoracle'}
    
    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data['status'] == '1':
                result = data['result']
                print(f"\n⛽ Gas Tracker")
                print(f"Safe: {result['SafeGasPrice']} Gwei")
                print(f"Standard: {result['ProposeGasPrice']} Gwei")
                print(f"Fast: {result['FastGasPrice']} Gwei")
                return True
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def get_eth_price():
    """Get current ETH price"""
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {
        'ids': 'ethereum',
        'vs_currencies': 'usd',
        'include_24hr_change': 'true'
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if 'ethereum' in data:
                info = data['ethereum']
                print(f"\n💰 Ethereum Price")
                print(f"Price: ${info['usd']:,.2f}")
                print(f"24h Change: {info.get('usd_24h_change', 0):+.2f}%")
                return True
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    print(f"🔧 Web3 Automation Toolkit")
    print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 40)
    
    get_eth_price()
    get_gas_tracker()
    
    # Example address (Vitalik's)
    example_address = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"
    get_eth_balance(example_address)
    
    print("\n✅ All checks completed!")
    print("💡 Use: python main.py <address> to check specific wallet")
