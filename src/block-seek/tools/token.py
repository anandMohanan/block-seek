from typing import Dict, Any, List, Optional, Union
import aiohttp
from datetime import datetime, timedelta
import asyncio
from .base import BaseTool, ToolException, retry_on_failure
from utils.blockchain import validate_address
import logging
from pydantic import BaseModel, Field


class TokenToolInputs(BaseModel):
    """Input schema for TokenTool"""
    command: str = Field(default="price", description="Command to execute (price, info)")
    symbol: Optional[str] = Field(default=None, description="Token symbol (e.g., BTC, ETH)")
    token_address: Optional[str] = Field(default=None, description="Ethereum token contract address")

class TokenTool(BaseTool):
    """Tool for analyzing ERC20 tokens and market data"""
    name = "TokenTool"
    description = "Get cryptocurrency prices and token information. Use this for any price queries (BTC, ETH, etc)"
    
    def __init__(self):
        super().__init__()
        self.cmc_api = "https://pro-api.coinmarketcap.com/v1"
        self.cmc_api_key = "89e759c1-7b82-422b-892b-40abef83c8be"
        if not self.cmc_api_key:
            raise ToolException("CoinMarketCap API key is required")
        
        self.cache = {}
        self.cache_ttl = 30
        self.logger = logging.getLogger(__name__)

    async def get_current_price(self, symbol: str) -> Dict[str, Any]:
        """Get real-time price from CoinMarketCap with debug logging"""
        try:
            # Validate and sanitize the symbol
            symbol = symbol.upper().strip()
            if not symbol.isalnum():
                raise ToolException(f"Invalid symbol format: {symbol}. Symbols must be alphanumeric.")

            async with aiohttp.ClientSession() as session:
                headers = {
                    'X-CMC_PRO_API_KEY': self.cmc_api_key,
                    'Accept': 'application/json'
                }
                
                url = f"{self.cmc_api}/cryptocurrency/quotes/latest"
                params = {
                    "symbol": symbol,
                    "convert": "USD"
                }
                
                self.logger.debug(f"Requesting price data for {symbol}")
                self.logger.debug(f"URL: {url}")
                self.logger.debug(f"Params: {params}")
                
                async with session.get(url, params=params, headers=headers) as response:
                    response_text = await response.text()
                    self.logger.debug(f"Response status: {response.status}")
                    self.logger.debug(f"Response text: {response_text}")
                    
                    if response.status != 200:
                        raise ToolException(f"Failed to fetch price data: {response_text}")
                    
                    try:
                        data = await response.json()
                    except Exception as e:
                        self.logger.error(f"Failed to parse JSON response: {str(e)}")
                        self.logger.error(f"Response text: {response_text}")
                        raise ToolException("Failed to parse API response")
                    
                    if "data" not in data:
                        self.logger.error(f"Unexpected response format: {data}")
                        raise ToolException("Invalid API response format")
                    
                    if symbol not in data["data"]:
                        self.logger.error(f"Symbol {symbol} not found in response")
                        raise ToolException(f"No data found for symbol {symbol}")
                    
                    token_data = data["data"][symbol]
                    if "quote" not in token_data or "USD" not in token_data["quote"]:
                        self.logger.error(f"Missing price data in response: {token_data}")
                        raise ToolException("Missing price data in response")
                    
                    quote_data = token_data["quote"]["USD"]
                    
                    result = {
                        "price": quote_data["price"],
                        "market_cap": quote_data["market_cap"],
                        "volume_24h": quote_data["volume_24h"],
                        "percent_change_24h": quote_data["percent_change_24h"],
                        "last_updated": quote_data["last_updated"],
                        "source": "coinmarketcap"
                    }
                    
                    self.logger.info(f"Successfully fetched price for {symbol}: {result['price']}")
                    return result

        except aiohttp.ClientError as e:
            self.logger.error(f"Network error: {str(e)}")
            raise ToolException(f"Network error while fetching price: {str(e)}")
        except Exception as e:
            self.logger.error(f"Unexpected error: {str(e)}")
            raise ToolException(f"Error fetching price from CoinMarketCap: {str(e)}")

    async def execute(self, *args, **kwargs) -> Dict[str, Any]:
        """Execute token analysis with structured input handling"""
        try:
            print(f"Args received: {args}")
            print(f"Kwargs received: {kwargs}")
            
            # Convert kwargs to input data if provided
            if kwargs:
                input_data = kwargs
            # If args provided, use the first argument
            elif args:
                input_data = args[0]
            else:
                raise ToolException("No input data provided")

            self.logger.debug(f"Input data to process: {input_data}")
            print(f"Input data to process: {input_data}")

            # Handle both string and dict inputs
            if isinstance(input_data, str):
                try:
                    params = TokenToolInputs.model_validate_json(input_data)
                except:
                    params = TokenToolInputs(command="price", symbol=input_data)
            else:
                # If it's a dict, parse it directly
                params = TokenToolInputs.model_validate(input_data)
            
            if params.command == "price" and params.symbol:
                result = await self.get_current_price(params.symbol)
                # Format the result nicely
                formatted_result = {
                    "price": f"${result['price']:,.2f}",
                    "market_cap": f"${result['market_cap']:,.0f}",
                    "volume_24h": f"${result['volume_24h']:,.0f}",
                    "percent_change_24h": f"{result['percent_change_24h']:,.2f}%",
                    "last_updated": result['last_updated']
                }
                return await self.format_output(formatted_result)
                
            elif params.token_address:
                result = {"token_info": await self.get_token_info(params.token_address)}
                return await self.format_output(result)
            else:
                raise ToolException("Invalid command or missing parameters")
                
        except Exception as e:
            self.logger.error(f"Error in execute: {str(e)}")
            return await self.handle_error(e)


    def get_parameters(self) -> type[TokenToolInputs]:
        """Get tool parameters schema"""
        return TokenToolInputs