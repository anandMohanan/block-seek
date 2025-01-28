from typing import Dict, Any
import time
import asyncio
import aiohttp
from fastapi import HTTPException

class RateLimiter:
    """Rate limiter for API requests"""
    
    def __init__(self, requests_per_second: int = 10):
        self.requests_per_second = requests_per_second
        self.last_request_time = {}
        self._lock = asyncio.Lock()

    async def check_rate_limit(self, key: str = "default") -> None:
        """Check if request is within rate limit"""
        async with self._lock:
            current_time = time.time()
            if key in self.last_request_time:
                time_passed = current_time - self.last_request_time[key]
                if time_passed < 1.0 / self.requests_per_second:
                    raise HTTPException(
                        status_code=429,
                        detail="Rate limit exceeded"
                    )
            self.last_request_time[key] = current_time

class APIHandler:
    """Handle external API requests"""
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key
        self.rate_limiters: Dict[str, RateLimiter] = {}
    
    def initialize_rate_limiters(self, rate_limits: Dict[str, int]) -> None:
        """Initialize rate limiters for different APIs
        
        Args:
            rate_limits: Dictionary mapping API names to their rate limits per second
                Example: {
                    "default": 10,
                    "opensea": 2,
                    "etherscan": 5,
                    "defillama": 10
                }
        """
        for api_name, requests_per_second in rate_limits.items():
            self.rate_limiters[api_name] = RateLimiter(requests_per_second)

    def get_rate_limiter(self, api_name: str) -> RateLimiter:
        """Get or create rate limiter for specific API"""
        if api_name not in self.rate_limiters:
            self.rate_limiters[api_name] = RateLimiter()
        return self.rate_limiters[api_name]
    
    async def check_connections(self) -> Dict[str, Any]:
        """Check the health of API connections
        
        Returns:
            Dict containing status of each API connection and overall health
        """
        api_endpoints = {
            "etherscan": "https://api.etherscan.io/api?module=proxy&action=eth_blockNumber",
            "defillama": "https://api.llama.fi/protocols",
        }
        
        status = {}
        all_healthy = True

        for api_name, url in api_endpoints.items():
            try:
                response = await self.make_request(
                    api_name=api_name,
                    url=url,
                    timeout=5,
                    retry_count=1
                )
                status[api_name] = {
                    "healthy": response["success"],
                    "latency": response.get("latency", 0),
                    "error": response.get("error", None)
                }
                if not response["success"]:
                    all_healthy = False
            except Exception as e:
                status[api_name] = {
                    "healthy": False,
                    "error": str(e)
                }
                all_healthy = False

        # Add Web3 provider check
        try:
            web3_url = "https://eth-mainnet.g.alchemy.com/v2/E6VKOZUoZJ77hCrSt187y2rSW3AHqIE7"  
            async with aiohttp.ClientSession() as session:
                async with session.post(web3_url, json={
                    "jsonrpc": "2.0",
                    "method": "eth_blockNumber",
                    "params": [],
                    "id": 1
                }, timeout=5) as response:
                    status["web3"] = {
                        "healthy": response.status == 200,
                        "latency": 0
                    }
                    if response.status != 200:
                        all_healthy = False
        except Exception as e:
            status["web3"] = {
                "healthy": False,
                "error": str(e)
            }
            all_healthy = False

        return {
            "all_healthy": all_healthy,
            "services": status,
            "timestamp": time.time()
        }

    async def make_request(
        self,
        api_name: str,
        url: str,
        method: str = "GET",
        params: Dict[str, Any] = None,
        headers: Dict[str, Any] = None,
        timeout: int = 30,
        json_data: Dict[str, Any] = None,
        retry_count: int = 3,
        retry_delay: int = 1
    ) -> Dict[str, Any]:
        """Make API request with rate limiting
        
        Args:
            api_name: Name of the API for rate limiting
            url: Request URL
            method: HTTP method (GET, POST, etc.)
            params: URL parameters
            headers: Request headers
            timeout: Request timeout in seconds
            json_data: JSON data for POST/PUT requests
            retry_count: Number of retries on failure
            retry_delay: Delay between retries in seconds
            
        Returns:
            Dict containing response data or error information
        """
        # Check rate limit
        rate_limiter = self.get_rate_limiter(api_name)
        await rate_limiter.check_rate_limit(api_name)
        
        # Merge headers with default headers
        request_headers = {
            "Accept": "application/json",
            "User-Agent": "Web3-Intelligence-Agent/1.0"
        }
        if self.api_key:
            request_headers["Authorization"] = f"Bearer {self.api_key}"
        if headers:
            request_headers.update(headers)

        # Prepare request kwargs
        request_kwargs = {
            "url": url,
            "headers": request_headers,
            "timeout": timeout
        }
        
        if params:
            request_kwargs["params"] = params
            
        if json_data and method in ["POST", "PUT", "PATCH"]:
            request_kwargs["json"] = json_data

        # Try request with retries
        for attempt in range(retry_count):
            try:
                async with aiohttp.ClientSession() as session:
                    async with getattr(session, method.lower())(**request_kwargs) as response:
                        # Check status code
                        if response.status // 100 not in [2, 3]:  # Not 2xx or 3xx
                            error_data = await response.text()
                            return {
                                "success": False,
                                "error": f"HTTP {response.status}",
                                "detail": error_data,
                                "status_code": response.status
                            }
                        
                        # Try to parse JSON response
                        try:
                            data = await response.json()
                            return {
                                "success": True,
                                "data": data,
                                "status_code": response.status
                            }
                        except ValueError:
                            # If not JSON, return text
                            text_data = await response.text()
                            return {
                                "success": True,
                                "data": text_data,
                                "status_code": response.status
                            }
                            
            except asyncio.TimeoutError:
                if attempt == retry_count - 1:
                    return {
                        "success": False,
                        "error": "Request timeout",
                        "detail": f"Request to {url} timed out after {timeout} seconds"
                    }
                    
            except aiohttp.ClientError as e:
                if attempt == retry_count - 1:
                    return {
                        "success": False,
                        "error": "Connection error",
                        "detail": str(e)
                    }
                    
            except Exception as e:
                if attempt == retry_count - 1:
                    return {
                        "success": False,
                        "error": "Request failed",
                        "detail": str(e)
                    }
            
            # Wait before retrying
            if attempt < retry_count - 1:
                await asyncio.sleep(retry_delay * (attempt + 1))


    async def format_response(self, data: Any) -> Dict[str, Any]:
        """Format successful response
        
        Args:
            data: Response data to format
            
        Returns:
            Dict containing formatted response data
        """
        if isinstance(data, dict):
            return data
        elif isinstance(data, (list, tuple)):
            return {"items": data}
        else:
            return {"data": data}
        
    async def format_error(self, error: Exception) -> Dict[str, Any]:
        """Format error response
        
        Args:
            error: Exception object
            
        Returns:
            Dict containing formatted error information
        """
        if isinstance(error, HTTPException):
            return {
                "status_code": error.status_code,
                "detail": str(error.detail),
                "error": "HTTP Exception"
            }
        
        return {
            "status_code": 500,
            "detail": str(error),
            "error": error.__class__.__name__
        }
    async def cleanup(self) -> None:
        """Cleanup resources before shutdown"""
        # Clear rate limiters
        self.rate_limiters.clear()

    async def check_rate_limits(self) -> None:
        """Check all API rate limits"""
        for api_name, rate_limiter in self.rate_limiters.items():
            await rate_limiter.check_rate_limit(api_name)

    async def update_settings(self, settings: Dict[str, Any]) -> None:
        """Update API handler settings
        
        Args:
            settings: Dictionary of settings to update
        """
        if "rate_limits" in settings:
            self.initialize_rate_limiters(settings["rate_limits"])
