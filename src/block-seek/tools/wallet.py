from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from web3 import Web3
from eth_typing import Address
from web3.exceptions import BlockNotFound, TransactionNotFound
import aiohttp
import asyncio
from .base import BaseTool, ToolException, retry_on_failure
from utils.blockchain import validate_address

class WalletToolInputs(BaseModel):
    """Input schema for WalletTool"""
    address: str = Field(description="Ethereum wallet address to analyze")
    limit: Optional[int] = Field(default=None, description="Maximum number of transactions to analyze")

class WalletTool(BaseTool):
    """Tool for analyzing Ethereum wallet data and transactions"""
    name = "WalletTool"
    description = "Analyzes Ethereum wallet activity and metrics"

    def __init__(self):
        super().__init__()
        self.w3 = Web3(Web3.HTTPProvider(self.settings.WEB3_PROVIDER_URI))
        self.etherscan_api = "https://api.etherscan.io/api"
        self.api_key = self.settings.ETHERSCAN_API_KEY

    async def validate_input(self, address: str) -> bool:
        """Validate wallet address"""
        if not validate_address(address):
            raise ToolException("Invalid Ethereum address")
        return True

    @retry_on_failure()
    async def get_token_balances(self, address: str) -> List[Dict[str, Any]]:
        """Get ERC20 token balances for address"""
        async with aiohttp.ClientSession() as session:
            params = {
                "module": "account",
                "action": "tokentx",  # Get token transfers for better analysis
                "address": address,
                "startblock": 0,
                "endblock": 99999999,
                "sort": "desc",
                "apikey": self.api_key
            }
            
            async with session.get(self.etherscan_api, params=params) as response:
                data = await response.json()
                if data["status"] != "1":
                    raise ToolException(f"Failed to fetch token balances: {data.get('message')}")
                
                # Process token transfers to get current balances
                token_balances = {}
                for tx in data.get("result", []):
                    token_addr = tx["contractAddress"]
                    if token_addr not in token_balances:
                        token_balances[token_addr] = {
                            "name": tx["tokenName"],
                            "symbol": tx["tokenSymbol"],
                            "decimals": int(tx["tokenDecimal"]),
                            "balance": 0
                        }
                    
                    amount = int(tx["value"]) / (10 ** int(tx["tokenDecimal"]))
                    if tx["to"].lower() == address.lower():
                        token_balances[token_addr]["balance"] += amount
                    if tx["from"].lower() == address.lower():
                        token_balances[token_addr]["balance"] -= amount

                return [
                    {**v, "contract_address": k} 
                    for k, v in token_balances.items() 
                    if v["balance"] > 0
                ]

    @retry_on_failure()
    async def get_transaction_history(self, address: str, limit: int = None) -> List[Dict[str, Any]]:
        """Get transaction history for address"""
        async with aiohttp.ClientSession() as session:
            params = {
                "module": "account",
                "action": "txlist",
                "address": address,
                "startblock": 0,
                "endblock": 99999999,
                "sort": "desc",
                "apikey": self.api_key
            }
            
            if limit:
                params["offset"] = str(limit)
            
            async with session.get(self.etherscan_api, params=params) as response:
                data = await response.json()
                if data["status"] != "1":
                    raise ToolException(f"Failed to fetch transactions: {data.get('message')}")
                
                return data.get("result", [])

    async def analyze_transactions(self, txs: List[Dict[str, Any]], address: str) -> Dict[str, Any]:
        """Analyze transaction patterns"""
        if not txs:
            return {}

        total_sent = 0
        total_received = 0
        gas_spent = 0
        interactions = set()
        last_activity = None
        
        for tx in txs:
            gas_spent += int(tx["gasUsed"]) * int(tx["gasPrice"])
            if tx["from"].lower() == address.lower():
                total_sent += int(tx["value"])
                interactions.add(tx["to"])
            else:
                total_received += int(tx["value"])
                interactions.add(tx["from"])
            
            # Track last activity
            if not last_activity or int(tx["timeStamp"]) > int(last_activity):
                last_activity = tx["timeStamp"]

        return {
            "total_transactions": len(txs),
            "total_sent_eth": float(self.w3.from_wei(total_sent, "ether")),
            "total_received_eth": float(self.w3.from_wei(total_received, "ether")),
            "gas_spent_eth": float(self.w3.from_wei(gas_spent, "ether")),
            "unique_interactions": len(interactions),
            "last_activity": last_activity
        }

    async def execute(self, *args, **kwargs) -> Dict[str, Any]:
        """Execute wallet analysis with flexible input handling"""
        try:
            # Handle both positional and keyword arguments
            if args and isinstance(args[0], (str, dict)):
                input_data = args[0]
            else:
                input_data = kwargs

            # Parse through our schema
            if isinstance(input_data, str):
                # If it's a string, assume it's the address
                params = WalletToolInputs(address=input_data)
            else:
                # If it's a dict, parse it properly
                params = WalletToolInputs.model_validate(input_data)

            # Validate the address
            await self.validate_input(params.address)
            
            # Get ETH balance
            eth_balance = await asyncio.to_thread(self.w3.eth.get_balance, params.address)
            
            # Get token balances
            token_balances = await self.get_token_balances(params.address)
            
            # Get and analyze transactions
            limit = params.limit or self.settings.WALLET_ANALYSIS_DEPTH
            txs = await self.get_transaction_history(params.address, limit)
            tx_analysis = await self.analyze_transactions(txs, params.address)
            
            result = {
                "address": params.address,
                "eth_balance": float(self.w3.from_wei(eth_balance, "ether")),
                "token_balances": token_balances,
                "transaction_analysis": tx_analysis
            }
            
            return await self.format_output(result)
            
        except Exception as e:
            self.logger.error(f"Error in WalletTool: {str(e)}")
            return await self.handle_error(e)

    def get_parameters(self) -> type[BaseModel]:
        """Get tool parameters schema"""
        return WalletToolInputs