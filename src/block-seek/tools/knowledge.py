import asyncio
from typing import List, Dict, Any
import os
from pathlib import Path
import faiss
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_openai.embeddings import AzureOpenAIEmbeddings
from langchain.vectorstores import FAISS
from langchain.docstore.document import Document
from pydantic import BaseModel, Field
from .base import BaseTool, ToolException, retry_on_failure

class KnowledgeToolInputs(BaseModel):
    query: str = Field(description="The query to search in the knowledge base")
    k: int = Field(default=5, description="Number of results to return")    

class KnowledgeTool(BaseTool):
    """Tool for querying and managing the Web3 knowledge base"""

    def __init__(self):
        super().__init__()
        self.embeddings = AzureOpenAIEmbeddings(
            api_key=self.settings.AZURE_EMBEDDINGS_API_KEY,
            api_version=self.settings.AZURE_EMBEDDINGS_API_VERSION,
            azure_deployment=self.settings.AZURE_EMBEDDINGS_DEPLOYMENT_NAME,
            model=self.settings.AZURE_EMBEDDINGS_MODEL,
            azure_endpoint=self.settings.AZURE_EMBEDDINGS_ENDPOINT)
        self.vector_store = None
        # asyncio.create_task(self.initialize_vector_store())

    async def initialize_vector_store(self):
        """Initialize or load the vector store"""
        vector_store_path = Path(self.settings.VECTOR_DB_PATH)
        if vector_store_path.exists():
            self.vector_store = FAISS.load_local(
                self.settings.VECTOR_DB_PATH,
                self.embeddings
            )
        else:
            await self.build_vector_store()

    @retry_on_failure(max_attempts=3)
    async def build_vector_store(self):
        """Build the vector store from knowledge base documents"""
        try:
            documents = []
            kb_path = Path(self.settings.KNOWLEDGE_BASE_PATH)
            
            for file_path in kb_path.glob("*.md"):
                with open(file_path, "r") as f:
                    content = f.read()
                    documents.append(Document(
                        page_content=content,
                        metadata={"source": file_path.name}
                    ))

            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=self.settings.CHUNK_SIZE,
                chunk_overlap=self.settings.CHUNK_OVERLAP
            )
            
            texts = text_splitter.split_documents(documents)
            self.vector_store = FAISS.from_documents(texts, self.embeddings)
            self.vector_store.save_local(self.settings.VECTOR_DB_PATH)
            
        except Exception as e:
            raise ToolException(f"Failed to build vector store: {str(e)}")

    async def validate_input(self, query: str) -> bool:
        """Validate the query"""
        if not query or not isinstance(query, str):
            raise ToolException("Query must be a non-empty string")
        return True

    @retry_on_failure()
    async def execute(self, query: str, **kwargs) -> Dict[str, Any]:
        """Execute a knowledge base query"""
        try:
            await self.validate_input(query)
            
            if not self.vector_store:
                raise ToolException("Vector store not initialized")

            k = kwargs.get("k", 5)  
            results = self.vector_store.similarity_search_with_score(query, k=k)
            
            formatted_results = []
            for doc, score in results:
                formatted_results.append({
                    "content": doc.page_content,
                    "source": doc.metadata.get("source", "unknown"),
                    "relevance_score": float(score)
                })

            return await self.format_output({
                "query": query,
                "results": formatted_results
            })

        except Exception as e:
            return await self.handle_error(e)

    def get_parameters(self) -> type[BaseModel]:
        return KnowledgeToolInputs
