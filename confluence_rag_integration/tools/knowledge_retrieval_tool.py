"""LangChain tool for knowledge retrieval from Confluence RAG system."""

from typing import Optional, Type, List, Dict, Any
from pydantic import BaseModel, Field
from langchain.tools import BaseTool
from langchain.callbacks.manager import CallbackManagerForToolRun

from ..customers.customer_manager import CustomerManager
from ..rag.query_manager import QueryManager


# TODO: use simpler syntax like @tool decorator to define the tool
# use tool.invoke() to execute the tool

class KnowledgeRetrievalInput(BaseModel):
    """Input schema for knowledge retrieval tool."""
    query: str = Field(description="The search query or question to find relevant documents")
    customer_id: str = Field(description="The customer ID to search within")
    top_k: int = Field(default=5, description="Number of top results to return")


class KnowledgeRetrievalTool(BaseTool):
    """Tool for retrieving knowledge from Confluence documentation."""
    
    name: str = "confluence_knowledge_retrieval"
    description: str = (
        "Search and retrieve relevant documentation from Confluence knowledge base. "
        "Use this when you need to find information about products, procedures, "
        "troubleshooting steps, or any documented knowledge to help resolve tickets."
    )
    args_schema: Type[BaseModel] = KnowledgeRetrievalInput
    
    def __init__(self):
        super().__init__()
        self._customer_manager = CustomerManager()
        self._query_manager = QueryManager(self._customer_manager)
    
    def _run(
        self,
        query: str,
        customer_id: str,
        top_k: int = 5,
        run_manager: Optional[CallbackManagerForToolRun] = None
    ) -> str:
        """Execute the knowledge retrieval."""
        try:
            # Call the query manager
            result = self._query_manager.query(customer_id, query, top_k)
            
            if result.status == "error":
                return f"Error retrieving documents: {result.error}"
            
            if not result.documents:
                return "No relevant documents found for the query."
            
            # Format results for LLM consumption
            formatted_results = []
            for i, doc in enumerate(result.documents, 1):
                source = doc.get("source", "Unknown")
                content = doc.get("content", "")
                
                formatted_results.append(
                    f"Document {i} (Source: {source}):\n{content}"
                )
            
            return "\n\n---\n\n".join(formatted_results)
            
        except Exception as e:
            return f"Error during retrieval: {str(e)}"
    
    async def _arun(self, *args, **kwargs):
        """Async version not implemented."""
        raise NotImplementedError("Async execution not supported")


def create_retrieval_tool() -> KnowledgeRetrievalTool:
    """Factory function to create the retrieval tool."""
    return KnowledgeRetrievalTool()