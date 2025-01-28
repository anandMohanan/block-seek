from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from functools import wraps
import time
import logging
from config.settings import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

class ToolException(Exception):
    """Base exception for tool errors"""
    pass

def retry_on_failure(max_attempts: int = 3, delay: float = 1.0):
    """Decorator for retrying failed operations"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    if attempt < max_attempts - 1:
                        await asyncio.sleep(delay * (attempt + 1))
            raise last_error
        return wrapper
    return decorator

class BaseTool(ABC):
    """Base class for all tools"""
    
    def __init__(self):
        self.name = self.__class__.__name__
        self.description = self.__doc__ or "No description available"
        self.settings = get_settings()
        self.logger = logging.getLogger(self.name)

    @abstractmethod
    async def execute(self, *args, **kwargs) -> Dict[str, Any]:
        """Execute the tool's main functionality"""
        pass

    async def validate_input(self, *args, **kwargs) -> bool:
        """Validate input parameters"""
        return True

    async def format_output(self, result: Any) -> Dict[str, Any]:
        """Format the output for the agent"""
        return {
            "status": "success",
            "tool": self.name,
            "result": result
        }

    async def handle_error(self, error: Exception) -> Dict[str, Any]:
        """Handle and format errors"""
        self.logger.error(f"Error in {self.name}: {str(error)}")
        return {
            "status": "error",
            "tool": self.name,
            "error": str(error)
        }

    @classmethod
    def get_tool_description(cls) -> Dict[str, Any]:
        """Get tool metadata for the agent"""
        return {
            "name": cls.__name__,
            "description": cls.__doc__ or "No description available",
            "parameters": cls.get_parameters()
        }

    @staticmethod
    def get_parameters() -> Dict[str, Any]:
        """Get tool parameters definition"""
        return {}
