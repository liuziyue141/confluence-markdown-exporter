"""Pydantic models for MCP server structured input/output."""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class DocumentResult(BaseModel):
    """Represents a single document retrieved from the knowledge base."""
    content: str = Field(description="The document content/text")
    source: str = Field(description="The source file or location of the document")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata about the document")


class RetrieveKnowledgeInput(BaseModel):
    """Input parameters for the retrieve_knowledge tool."""
    query: str = Field(description="The search query or question to find relevant documents")
    customer_id: str = Field(default="acme_corp", description="Customer ID for multi-tenant support")
    top_k: int = Field(default=3, description="Number of documents to retrieve")


class RetrieveKnowledgeOutput(BaseModel):
    """Output from the retrieve_knowledge tool."""
    documents: List[DocumentResult] = Field(description="List of retrieved documents")
    status: str = Field(description="Status of the retrieval operation (success/error)")
    error: Optional[str] = Field(default=None, description="Error message if retrieval failed")
    customer_id: str = Field(description="Customer ID that was queried")
    query: str = Field(description="The original query that was searched")