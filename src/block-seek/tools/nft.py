from typing import Dict, Any, List, Optional    
import numpy as np
from datetime import datetime, timedelta
from collections import Counter

from pydantic import BaseModel, Field
from .base import BaseTool, ToolException, retry_on_failure
from utils.blockchain import validate_address
from utils.api import APIHandler

class NFTToolInputs(BaseModel):
    contract_address: str = Field(description="NFT contract address to analyze")
    token_id: Optional[int] = Field(default=None, description="Specific token ID to analyze")
    include_rarity: bool = Field(default=False, description="Include rarity analysis")
    include_sales: bool = Field(default=False, description="Include sales history and analysis")
    days: int = Field(default=30, description="Number of days of sales history")
    limit: int = Field(default=1000, description="Maximum number of tokens to analyze for rarity")

class NFTTool(BaseTool):
    """Tool for analyzing NFT collections and market data"""
    name = "NFTTool"
    description = "Analyzes NFT collections and markets"

    def __init__(self):
        super().__init__()
        self.opensea_api = "https://api.opensea.io/api/v1"
        self.cache = {}
        self.cache_ttl = 300  # 5 minutes
        # Initialize API handler with OpenSea API key
        self.api_handler = APIHandler(self.settings.OPENSEA_API_KEY)

    async def validate_input(self, contract_address: str) -> bool:
        """Validate NFT contract address"""
        if not validate_address(contract_address):
            raise ToolException("Invalid NFT contract address")
        return True

    @retry_on_failure()
    async def get_collection_stats(self, contract_address: str) -> Dict[str, Any]:
        """Get NFT collection statistics from OpenSea"""
        cache_key = f"stats_{contract_address}"
        if cache_key in self.cache:
            cached_data = self.cache[cache_key]
            if datetime.now() - cached_data["timestamp"] < timedelta(seconds=self.cache_ttl):
                return cached_data["data"]

        url = f"{self.opensea_api}/collection/{contract_address}/stats"
        headers = {"X-API-KEY": self.settings.OPENSEA_API_KEY}
        
        response = await self.api_handler.make_request(
            api_name="opensea",
            url=url,
            headers=headers,
            retry_count=3
        )
        
        if not response["success"]:
            raise ToolException(f"Failed to fetch collection stats: {response['error']}")
            
        stats = response["data"]["stats"]
        result = {
            "floor_price": stats.get("floor_price"),
            "total_supply": stats.get("total_supply"),
            "num_owners": stats.get("num_owners"),
            "total_volume": stats.get("total_volume"),
            "average_price": stats.get("average_price"),
            "market_cap": stats.get("market_cap"),
            "one_day_volume": stats.get("one_day_volume"),
            "one_day_sales": stats.get("one_day_sales"),
            "one_day_average_price": stats.get("one_day_average_price"),
            "seven_day_volume": stats.get("seven_day_volume"),
            "seven_day_sales": stats.get("seven_day_sales"),
            "seven_day_average_price": stats.get("seven_day_average_price")
        }
        
        self.cache[cache_key] = {
            "timestamp": datetime.now(),
            "data": result
        }
        
        return result

    @retry_on_failure()
    async def get_token_metadata(self, contract_address: str, token_id: int) -> Dict[str, Any]:
        """Get metadata for a specific NFT"""
        url = f"{self.opensea_api}/asset/{contract_address}/{token_id}"
        headers = {"X-API-KEY": self.settings.OPENSEA_API_KEY}
        
        response = await self.api_handler.make_request(
            api_name="opensea",
            url=url,
            headers=headers
        )
        
        if not response["success"]:
            raise ToolException(f"Failed to fetch token metadata: {response['error']}")
            
        data = response["data"]
        return {
            "name": data.get("name"),
            "description": data.get("description"),
            "traits": data.get("traits", []),
            "image_url": data.get("image_url"),
            "owner": data.get("owner", {}).get("address"),
            "last_sale": data.get("last_sale"),
            "token_id": data.get("token_id")
        }

    async def calculate_rarity_scores(self, contract_address: str, limit: int = 1000) -> Dict[str, Any]:
        """Calculate rarity scores for collection traits"""
        assets = []
        offset = 0
        headers = {"X-API-KEY": self.settings.OPENSEA_API_KEY}
        
        while len(assets) < limit:
            url = f"{self.opensea_api}/assets"
            params = {
                "asset_contract_address": contract_address,
                "limit": min(50, limit - len(assets)),
                "offset": offset
            }
            
            response = await self.api_handler.make_request(
                api_name="opensea",
                url=url,
                headers=headers,
                params=params
            )
            
            if not response["success"]:
                break
                
            data = response["data"]
            if not data.get("assets"):
                break
                
            assets.extend(data["assets"])
            offset += len(data["assets"])

        if not assets:
            raise ToolException("Failed to fetch assets for rarity calculation")

    @retry_on_failure()
    async def get_sales_history(self, contract_address: str, days: int = 30) -> List[Dict[str, Any]]:
        """Get collection sales history"""
        url = f"{self.opensea_api}/events"
        headers = {"X-API-KEY": self.settings.OPENSEA_API_KEY}
        params = {
            "asset_contract_address": contract_address,
            "event_type": "successful",
            "occurred_after": int((datetime.now() - timedelta(days=days)).timestamp())
        }
        
        response = await self.api_handler.make_request(
            api_name="opensea",
            url=url,
            headers=headers,
            params=params
        )
        
        if not response["success"]:
            raise ToolException(f"Failed to fetch sales history: {response['error']}")
            
        data = response["data"]
        sales = []
        
        for event in data.get("asset_events", []):
            sale = {
                "token_id": event.get("asset", {}).get("token_id"),
                "price_eth": float(event.get("total_price", 0)) / 1e18,
                "timestamp": event.get("transaction", {}).get("timestamp"),
                "buyer": event.get("winner_account", {}).get("address"),
                "seller": event.get("seller", {}).get("address")
            }
            sales.append(sale)

        return sales

    async def analyze_price_trends(self, sales_history: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze price trends from sales history"""
        if not sales_history:
            return {}

        prices = [sale["price_eth"] for sale in sales_history]
        
        return {
            "average_price": np.mean(prices),
            "median_price": np.median(prices),
            "min_price": min(prices),
            "max_price": max(prices),
            "price_std_dev": np.std(prices),
            "total_sales": len(sales_history),
            "total_volume": sum(prices)
        }

    async def execute(self, contract_address: str, **kwargs) -> Dict[str, Any]:
        """Execute NFT analysis"""
        try:
            await self.validate_input(contract_address)
            
            # Build result dictionary
            result = {
                "collection_stats": await self.get_collection_stats(contract_address)
            }
            
            # Add rarity analysis if requested
            if kwargs.get("include_rarity"):
                limit = kwargs.get("limit", self.settings.NFT_ANALYSIS_LIMIT)
                result["rarity_analysis"] = await self.calculate_rarity_scores(
                    contract_address, 
                    limit
                )
            
            # Add sales analysis if requested
            if kwargs.get("include_sales"):
                days = kwargs.get("days", 30)
                sales_history = await self.get_sales_history(contract_address, days)
                result["sales_history"] = sales_history
                result["price_analysis"] = await self.analyze_price_trends(sales_history)
            
            # Add specific token metadata if requested
            if kwargs.get("token_id") is not None:
                result["token_metadata"] = await self.get_token_metadata(
                    contract_address,
                    kwargs["token_id"]
                )
            
            return await self.format_output(result)
            
        except Exception as e:
            return await self.handle_error(e)

    def get_parameters(self) -> type[BaseModel]:
        return NFTToolInputs

