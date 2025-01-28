from typing import Dict, Any, List
from web3 import Web3
from eth_typing import Address
import json

def validate_address(address: str) -> bool:
    """Validate Ethereum address"""
    return Web3.is_address(address)

def validate_transaction_hash(tx_hash: str) -> bool:
    """Validate transaction hash format"""
    return len(tx_hash) == 66 and tx_hash.startswith("0x")

class Web3Utils:
    """Utility functions for Web3 interactions"""
    def __init__(self, provider_uri: str):
        self.w3 = Web3(Web3.HTTPProvider(provider_uri))

    def get_latest_block(self) -> Dict[str, Any]:
        """Get latest block information"""
        block = self.w3.eth.get_block('latest')
        return dict(block)

    async def get_transaction_receipt(self, tx_hash: str) -> Dict[str, Any]:
        """Get transaction receipt"""
        receipt = self.w3.eth.get_transaction_receipt(tx_hash)
        return dict(receipt)

    def decode_contract_call(
        self, 
        contract_abi: List[Dict], 
        input_data: str
    ) -> Dict[str, Any]:
        """Decode contract function call from input data"""
        try:
            contract = self.w3.eth.contract(abi=contract_abi)
            func_obj, func_params = contract.decode_function_input(input_data)
            return {
                "function": func_obj.fn_name,
                "params": func_params
            }
        except Exception as e:
            return {
                "error": f"Failed to decode: {str(e)}", 
                "raw_data": input_data
            }

    def load_contract(
        self, 
        address: str, 
        abi_path: str
    ) -> Any:
        """Load contract instance"""
        try:
            with open(abi_path) as f:
                abi = json.load(f)
            return self.w3.eth.contract(
                address=self.w3.to_checksum_address(address),
                abi=abi
            )
        except Exception as e:
            raise Exception(f"Failed to load contract: {str(e)}")

    def estimate_gas(
        self,
        to_address: str,
        from_address: str,
        value: int = 0,
        data: str = ""
    ) -> int:
        """Estimate gas for transaction"""
        return self.w3.eth.estimate_gas({
            'to': to_address,
            'from': from_address,
            'value': value,
            'data': data
        })

    def get_logs(
        self,
        address: str,
        topics: List[str],
        from_block: int,
        to_block: int = 'latest'
    ) -> List[Dict[str, Any]]:
        """Get contract event logs"""
        logs = self.w3.eth.get_logs({
            'address': address,
            'topics': topics,
            'fromBlock': from_block,
            'toBlock': to_block
        })
        return [dict(log) for log in logs]