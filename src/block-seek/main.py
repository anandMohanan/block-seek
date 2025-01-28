from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from typing import Dict, Any, Optional, List
import logging
import time
from pydantic import BaseModel

from agent.core import Web3Agent
from config.settings import get_settings, Settings
from utils.api import APIHandler, RateLimiter

# Initialize settings and logging
settings = get_settings()
logging.basicConfig(level=settings.LOG_LEVEL)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.API_VERSION,
    description="Web3 Intelligence System API"
)

# Add middlewares
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware)

# Initialize API handler
api_handler = APIHandler()

# Request/Response Models
class QueryRequest(BaseModel):
    query: str
    context: Optional[Dict[str, Any]] = None

class QueryResponse(BaseModel):
    status: str
    response: Dict[str, Any]
    execution_time: float

class ErrorResponse(BaseModel):
    status: str = "error"
    error: str
    detail: Optional[str] = None

class HealthResponse(BaseModel):
    status: str
    version: str
    timestamp: float
    api_status: Optional[Dict[str, Any]] = None
    services: Optional[Dict[str, Dict[str, Any]]] = None
    error: Optional[str] = None

# Dependencies
async def get_agent() -> Web3Agent:
    """Dependency for getting Web3Agent instance"""
    try:
        agent = Web3Agent()
        return agent
    except Exception as e:
        logger.error(f"Failed to initialize agent: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to initialize agent")

async def get_api_handler() -> APIHandler:
    """Dependency for getting APIHandler instance"""
    return api_handler

@app.on_event("startup")
async def startup_event():
    """Startup event handler"""
    logger.info("Starting Web3 Intelligence System")
    # Initialize API rate limiters
    api_handler.initialize_rate_limiters({
        "default": settings.RATE_LIMIT_PER_SECOND,
        "opensea": 2,  # 2 requests per second
        "etherscan": 5,  # 5 requests per second
        "defillama": 10  # 10 requests per second
    })

@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown event handler"""
    logger.info("Shutting down Web3 Intelligence System")
    # Cleanup API connections
    await api_handler.cleanup()

@app.get("/health", response_model=HealthResponse)
async def health_check(api: APIHandler = Depends(get_api_handler)):
    """Health check endpoint"""
    # Check API connections
    api_status = await api.check_connections()
    services = {
            "fastapi": {"status": "healthy"},
            "web3": {
                "status": "healthy" if api_status.get("services", {}).get("web3", {}).get("healthy", False) else "degraded",
                "details": api_status.get("services", {}).get("web3", {})
            },
            "etherscan": {
                "status": "healthy" if api_status.get("services", {}).get("etherscan", {}).get("healthy", False) else "degraded",
                "details": api_status.get("services", {}).get("etherscan", {})
            },
            "defillama": {
                "status": "healthy" if api_status.get("services", {}).get("defillama", {}).get("healthy", False) else "degraded",
                "details": api_status.get("services", {}).get("defillama", {})
            }
        }

    return {
            "status": "healthy" if api_status.get("all_healthy", False) else "degraded",
            "version": settings.API_VERSION,
            "timestamp": time.time(),
            "api_status": api_status.get("services", {}),
            "services": services
        }

@app.post("/query", response_model=QueryResponse)
async def process_query(
    request: QueryRequest,
    background_tasks: BackgroundTasks,
    agent: Web3Agent = Depends(get_agent),
    api: APIHandler = Depends(get_api_handler)
):
    """Process a query using the Web3 agent"""
    try:
        # Check API rate limits
        await api.check_rate_limits()
        
        # Record start time
        start_time = time.time()
        
        # Process query
        response = await agent.process_query(
            query=request.query,
            context=request.context
        )
        
        # Calculate execution time
        execution_time = time.time() - start_time
        
        # Add to background tasks
        background_tasks.add_task(
            logger.info,
            f"Query processed successfully in {execution_time:.2f}s"
        )
        
        # Format response using API handler
        formatted_response = await api.format_response(response)
        
        return {
            "status": "success",
            "response": formatted_response,
            "execution_time": execution_time
        }
        
    except Exception as e:
        logger.error(f"Error processing query: {str(e)}")
        error_response = await api.format_error(e)
        raise HTTPException(
            status_code=error_response.get("status_code", 500),
            detail=error_response.get("detail", str(e))
        )

@app.get("/tools", response_model=List[Dict[str, Any]])
async def get_available_tools(
    agent: Web3Agent = Depends(get_agent),
    api: APIHandler = Depends(get_api_handler)
):
    """Get information about available tools"""
    try:
        tools = await agent.get_tool_descriptions()
        return await api.format_response(tools)
    except Exception as e:
        logger.error(f"Error fetching tool descriptions: {str(e)}")
        error_response = await api.format_error(e)
        raise HTTPException(status_code=500, detail=error_response)

@app.get("/history", response_model=List[Dict[str, Any]])
async def get_conversation_history(
    agent: Web3Agent = Depends(get_agent),
    api: APIHandler = Depends(get_api_handler)
):
    """Get conversation history"""
    try:
        history = await agent.get_conversation_history()
        return await api.format_response(history)
    except Exception as e:
        logger.error(f"Error fetching conversation history: {str(e)}")
        error_response = await api.format_error(e)
        raise HTTPException(status_code=500, detail=error_response)

@app.post("/clear")
async def clear_conversation(
    agent: Web3Agent = Depends(get_agent),
    api: APIHandler = Depends(get_api_handler)
):
    """Clear conversation history"""
    try:
        await agent.clear_memory()
        return await api.format_response({
            "status": "success",
            "message": "Conversation cleared"
        })
    except Exception as e:
        logger.error(f"Error clearing conversation: {str(e)}")
        error_response = await api.format_error(e)
        raise HTTPException(status_code=500, detail=error_response)

@app.post("/settings")
async def update_settings(
    settings_update: Dict[str, Any],
    agent: Web3Agent = Depends(get_agent),
    api: APIHandler = Depends(get_api_handler)
):
    """Update agent settings"""
    try:
        await agent.update_settings(settings_update)
        # Update API handler settings if needed
        if "api_settings" in settings_update:
            await api.update_settings(settings_update["api_settings"])
        return await api.format_response({
            "status": "success",
            "message": "Settings updated"
        })
    except Exception as e:
        logger.error(f"Error updating settings: {str(e)}")
        error_response = await api.format_error(e)
        raise HTTPException(status_code=500, detail=error_response)

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Handle HTTP exceptions"""
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            status="error",
            error=str(exc.detail)
        ).dict()
    )

@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Handle general exceptions"""
    logger.error(f"Unhandled exception: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            status="error",
            error="Internal server error",
            detail=str(exc)
        ).dict()
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG
    )
