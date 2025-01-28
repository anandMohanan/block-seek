from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from web3 import Web3
from .base import BaseTool, ToolException, retry_on_failure
from utils.blockchain import validate_address
from utils.api import APIHandler

class DeFiTool(BaseTool):
    """Tool for analyzing DeFi protocols, pools, and yield opportunities using DefiLlama"""
    
    def __init__(self):
        super().__init__()
        self.w3 = Web3(Web3.HTTPProvider(self.settings.WEB3_PROVIDER_URI))
        self.defillama_api = "https://api.llama.fi"
        self.cache = {}
        self.cache_ttl = 300  # 5 minutes
        self.defillama_handler = APIHandler()
        self.lending_pool_abi = self._load_abi("lending_pool")
        self.pair_abi = self._load_abi("uniswap_pair")
        self.router_abi = self._load_abi("uniswap_router")

    def _load_abi(self, name: str) -> List[Dict[str, Any]]:
        """Load ABI from JSON file"""
        try:
            with open(f"utils/abis/{name}.json") as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"Failed to load ABI {name}: {str(e)}")
            return []

    async def get_protocol_data(self, protocol_id: str) -> Dict[str, Any]:
        """Get comprehensive protocol data from DefiLlama"""
        cache_key = f"protocol_{protocol_id}"
        if cache_key in self.cache:
            cached_data = self.cache[cache_key]
            if datetime.now() - cached_data["timestamp"] < timedelta(seconds=self.cache_ttl):
                return cached_data["data"]

        # Get protocol data
        protocol_url = f"{self.defillama_api}/protocol/{protocol_id}"
        protocol_response = await self.defillama_handler.make_request(
            api_name="defillama",
            url=protocol_url,
            retry_count=3
        )
        if not protocol_response["success"]:
            raise ToolException(f"Failed to fetch protocol data: {protocol_response['error']}")

        # Get protocol chart data
        chart_url = f"{self.defillama_api}/protocol/{protocol_id}/chart"
        chart_response = await self.defillama_handler.make_request(
            api_name="defillama",
            url=chart_url,
            retry_count=3
        )

        data = protocol_response["data"]
        result = {
            "name": data.get("name"),
            "description": data.get("description"),
            "current_tvl": data.get("tvl", 0),
            "chains": data.get("chains", []),
            "category": data.get("category"),
            "total_volume_24h": data.get("volume24h", 0),
            "tvl_history": chart_response["data"] if chart_response["success"] else [],
            "audit_links": data.get("audit_links", []),
            "url": data.get("url"),
            "github": data.get("github")
        }

        self.cache[cache_key] = {
            "timestamp": datetime.now(),
            "data": result
        }
        return result

    async def get_chain_tvl(self, chain: str) -> Dict[str, Any]:
        """Get TVL data for a specific chain"""
        url = f"{self.defillama_api}/v2/chains"
        response = await self.defillama_handler.make_request(
            api_name="defillama",
            url=url,
            retry_count=3
        )
        if not response["success"]:
            raise ToolException(f"Failed to fetch chain TVL: {response['error']}")
        
        chain_data = next((item for item in response["data"] if item["name"].lower() == chain.lower()), None)
        if not chain_data:
            raise ToolException(f"Chain {chain} not found")
        
        return {
            "tvl": chain_data.get("tvl", 0),
            "tokenSymbol": chain_data.get("tokenSymbol"),
            "change_1d": chain_data.get("change_1d", 0),
            "change_7d": chain_data.get("change_7d", 0)
        }

    async def assess_protocol_risk(self, protocol_data: Dict[str, Any]) -> Dict[str, Any]:
        """Assess protocol risk metrics using DefiLlama data"""
        try:
            tvl = protocol_data.get("current_tvl", 0)
            volume_24h = protocol_data.get("total_volume_24h", 0)
            
            # Calculate risk metrics
            tvl_score = min(tvl / 1e9, 1.0)  # Normalize by $1B
            volume_to_tvl = volume_24h / tvl if tvl > 0 else 0
            volume_score = min(volume_to_tvl, 1.0)
            
            # Check for audits
            audit_score = 0.8 if protocol_data.get("audit_links") else 0.2
            
            # Calculate chain diversification
            chain_count = len(protocol_data.get("chains", []))
            chain_score = min(chain_count / 5, 1.0)  # Normalize by 5 chains
            
            risk_factors = {
                "tvl_score": tvl_score,
                "volume_score": volume_score,
                "audit_score": audit_score,
                "chain_diversification": chain_score
            }
            
            overall_risk = sum(risk_factors.values()) / len(risk_factors)
            
            return {
                "risk_factors": risk_factors,
                "overall_risk": overall_risk,
                "risk_level": "HIGH" if overall_risk < 0.3 else 
                             "MEDIUM" if overall_risk < 0.7 else 
                             "LOW"
            }
        except Exception as e:
            raise ToolException(f"Failed to assess protocol risk: {str(e)}")

    async def execute(self, action: str, **kwargs) -> Dict[str, Any]:
        """Execute DeFi analysis using DefiLlama data"""
        try:
            result = {}
            
            if action == "protocol":
                protocol_id = kwargs.get("protocol_id")
                if not protocol_id:
                    raise ToolException("Protocol ID required")
                
                protocol_data = await self.get_protocol_data(protocol_id)
                result["protocol_data"] = protocol_data
                
                if kwargs.get("include_risk"):
                    result["risk_analysis"] = await self.assess_protocol_risk(protocol_data)
            
            elif action == "chain":
                chain = kwargs.get("chain")
                if not chain:
                    raise ToolException("Chain name required")
                
                result = await self.get_chain_tvl(chain)
            
            else:
                raise ToolException(f"Invalid action: {action}")
            
            return await self.format_output(result)
            
        except Exception as e:
            return await self.handle_error(e)

    @staticmethod
    def get_parameters() -> Dict[str, Any]:
        """Get tool parameters"""
        return {
            "action": {
                "type": "string",
                "description": "Analysis action (protocol, chain)",
                "required": True
            },
            "protocol_id": {
                "type": "string",
                "description": "Protocol identifier for analysis",
                "required": False
            },
            "chain": {
                "type": "string",
                "description": "Chain name for TVL analysis",
                "required": False
            },
            "include_risk": {
                "type": "boolean",
                "description": "Include risk analysis",
                "required": False,
                "default": False
            }
        }
