"""Simplified data models for the multi-tenant Confluence RAG integration system."""

from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from datetime import datetime
from pathlib import Path


@dataclass
class CustomerConfig:
    """Customer configuration from config.yaml"""
    customer_id: str
    customer_name: str
    confluence_url: str
    confluence_username: str
    confluence_api_token: str
    space_keys: List[str]
    # RAG settings
    embedding_model: str = "gemini-embedding-001"
    chunk_size: int = 1000
    collection_name: str = None  # Auto-generated if None
    db_connection: str = "postgresql+psycopg://user:pass@localhost:5432/db"
    
    def __post_init__(self):
        if not self.collection_name:
            self.collection_name = f"customer_{self.customer_id}"


@dataclass
class CustomerState:
    """Runtime state from state.json"""
    customer_id: str
    last_export: Optional[Dict[str, Any]] = None  # {timestamp, status, pages_exported, errors}
    last_index: Optional[Dict[str, Any]] = None   # {timestamp, status, documents_indexed, chunks_created}
    rag_status: str = "never_built"  # never_built, building, ready, failed
    
    @property
    def is_ready_for_queries(self) -> bool:
        return self.rag_status == "ready" and self.last_index is not None


@dataclass
class ExportResult:
    """Result from export operation"""
    status: str  # success, partial, failed
    pages_exported: int
    errors: List[str]
    timestamp: str  # ISO format
    duration_seconds: float


@dataclass
class IndexResult:
    """Result from index operation"""
    status: str  # success, no_documents, failed
    documents_indexed: int
    chunks_created: int
    timestamp: str  # ISO format
    duration_seconds: float


@dataclass
class QueryResult:
    """Result from query operation"""
    customer_id: str
    question: str
    documents: List[Dict[str, Any]]  # [{content, metadata, source}, ...]
    status: str  # success, error
    error: Optional[str] = None