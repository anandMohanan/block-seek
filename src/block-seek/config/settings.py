from pydantic_settings import BaseSettings
from pydantic import Field, HttpUrl
from typing import Dict, List, Optional, Union
from functools import lru_cache
import os


class Settings(BaseSettings):
    APP_NAME: str = "Block Seek"
    DEBUG: bool = False
    API_VERSION: str = "v1"
    
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    CORS_ORIGINS: List[str] = ["*"]
    RATE_LIMIT_PER_SECOND: int = 10
    
    AZURE_ENDPOINT: str 
    AZURE_DEPLOYMENT: str
    AZURE_API_VERSION: str
    AZURE_API_KEY: str
    TEMPERATURE: float = 0.0
    MODEL_NAME: str = "gpt-4"



    AZURE_EMBEDDINGS_MODEL: str
    AZURE_EMBEDDINGS_DEPLOYMENT_NAME : str
    AZURE_EMBEDDINGS_ENDPOINT: str
    AZURE_EMBEDDINGS_API_KEY : str
    AZURE_EMBEDDINGS_API_VERSION : str

    OPENSEA_API_KEY: Optional[str] = None
    
    DEFAULT_MODEL: str = "gpt-4"
    TEMPERATURE: int = 0.0
    MAX_TOKENS: int = 2000
    MEMORY_K: int = 5 
    
    WEB3_PROVIDER_URI: str = Field(..., description="Web3 provider URI")
    ALCHEMY_API_KEY: Optional[str] = None
    FALLBACK_PROVIDERS: List[str] = []
    CHAIN_ID: int = 1 
    BLOCK_EXPLORER_API: HttpUrl = Field(
    "https://api.etherscan.io/api",
    description="Block explorer API endpoint"
)
    SUPPORTED_NETWORKS: Dict[str, int] = {
        "mainnet": 1,
    }
    
    ETHERSCAN_API_KEY: str
    DEFILLAMA_BASE_URL: str = "https://api.llama.fi"
    
    WALLET_ANALYSIS_DEPTH: int = 100  
    TOKEN_PRICE_CACHE_TTL: int = 300  
    NFT_ANALYSIS_LIMIT: int = 1000  
    
    KNOWLEDGE_BASE_PATH: str = "knowledge_base"
    VECTOR_DB_PATH: str = "vector_store"
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200
    
    CACHE_TYPE: str = "redis"
    CACHE_URL: Optional[str] = "redis://localhost:6379"
    CACHE_TTL: int = 3600 
    
    LOG_LEVEL: str = "INFO"
    ENABLE_METRICS: bool = True
    SENTRY_DSN: Optional[str] = None

    class Config:
        env_file = '.env'
        case_sensitive = True

@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()

class ConfigError:
    PROVIDER_NOT_FOUND = "Web3 provider URI not found"
    INVALID_CHAIN_ID = "Invalid chain ID specified"
    API_KEY_MISSING = "Required API key not found: {}"

def validate_web3_provider(provider_uri: str) -> bool:
    """Validate Web3 provider URI"""
    return bool(provider_uri and provider_uri.startswith(("http", "ws")))

def validate_api_keys(settings: Settings) -> List[str]:
    """Validate required API keys are present"""
    missing_keys = []
    required_keys = [
        ("ETHERSCAN_API_KEY", settings.ETHERSCAN_API_KEY),
    ]
    
    for key_name, key_value in required_keys:
        if not key_value:
            missing_keys.append(key_name)
    
    return missing_keys

def get_network_config(chain_id: int) -> Dict:
    """Get network configuration by chain ID"""
    settings = get_settings()
    network_configs = {
        1: {
            "name": "mainnet",
            "explorer_url": "https://etherscan.io",
            "block_time": 12
        },
    }
    
    return network_configs.get(chain_id, {})
