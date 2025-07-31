"""Shared data models for the Confluence RAG integration system."""

import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
from enum import Enum

from pydantic import BaseModel, Field, SecretStr, AnyHttpUrl, validator


class ExportStatus(str, Enum):
    """Export operation status."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


class RAGStatus(str, Enum):
    """RAG indexing status."""
    NEVER_BUILT = "never_built"
    BUILDING = "building" 
    READY = "ready"
    FAILED = "failed"
    UPDATING = "updating"


class ConfluenceAuthConfig(BaseModel):
    """Confluence authentication configuration."""
    
    url: AnyHttpUrl = Field(..., description="Confluence instance URL")
    username: str = Field(..., description="Username or email for authentication")
    api_token: SecretStr = Field(..., description="API token for authentication")
    pat: Optional[SecretStr] = Field(None, description="Personal Access Token (alternative to username/token)")
    
    @validator('url')
    def validate_url(cls, v):
        """Ensure URL ends with /"""
        url_str = str(v)
        if not url_str.endswith('/'):
            return AnyHttpUrl(f"{url_str}/")
        return v


class SpaceConfig(BaseModel):
    """Configuration for a Confluence space."""
    
    key: str = Field(..., description="Space key")
    name: str = Field(..., description="Space name")
    enabled: bool = Field(True, description="Whether to export this space")
    export_descendants: bool = Field(True, description="Whether to export child pages")
    include_attachments: bool = Field(True, description="Whether to export attachments")


class ExportConfig(BaseModel):
    """Export configuration settings."""
    
    output_path: Path = Field(..., description="Base output directory for exports")
    page_path: str = Field(
        "{space_name}/{ancestor_titles}/{page_title}.md",
        description="Template for page file paths"
    )
    attachment_path: str = Field(
        "{space_name}/attachments/{attachment_file_id}{attachment_extension}",
        description="Template for attachment file paths"
    )
    include_breadcrumbs: bool = Field(True, description="Include breadcrumbs in exported pages")
    include_document_title: bool = Field(True, description="Include document title as H1")
    download_external_images: bool = Field(True, description="Download external images locally")
    max_file_size_mb: int = Field(100, description="Maximum file size for downloads (MB)")
    
    @validator('output_path')
    def ensure_absolute_path(cls, v):
        """Ensure output path is absolute."""
        return v.resolve()


class RAGConfig(BaseModel):
    """RAG system configuration."""
    
    vector_store_path: Path = Field(..., description="Path to customer's vector store")
    collection_name: str = Field(..., description="Customer-specific collection name")
    connection_string: str = Field(
        "postgresql+psycopg://tim_itagent:Apple3344!@localhost:5432/confluence_exp", 
        description="Database connection string"
    )
    enable_parent_retriever: bool = Field(True, description="Use parent document retrieval")
    chunk_size: int = Field(1000, description="Document chunk size")
    chunk_overlap: int = Field(100, description="Chunk overlap size")
    parent_chunk_size: int = Field(50000, description="Parent document chunk size")
    embedding_model: str = Field("gemini-embedding-001", description="Embedding model to use")
    
    @validator('vector_store_path')
    def ensure_absolute_path(cls, v):
        """Ensure vector store path is absolute."""
        return v.resolve()


class CustomerConfig(BaseModel):
    """Complete configuration for a customer."""
    
    customer_id: str = Field(..., description="Unique customer identifier")
    name: str = Field(..., description="Customer display name")
    confluence: ConfluenceAuthConfig = Field(..., description="Confluence authentication")
    spaces: List[SpaceConfig] = Field(default_factory=list, description="Configured spaces")
    export: ExportConfig = Field(..., description="Export settings")
    rag: RAGConfig = Field(..., description="RAG settings")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Configuration creation time")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Last update time")
    active: bool = Field(True, description="Whether customer is active")
    
    @validator('customer_id')
    def validate_customer_id(cls, v):
        """Validate customer ID format."""
        import re
        if not re.match(r'^[a-z0-9_-]+$', v):
            raise ValueError('Customer ID must contain only lowercase letters, numbers, underscores, and hyphens')
        return v
    
    def update_timestamp(self):
        """Update the updated_at timestamp."""
        self.updated_at = datetime.utcnow()


class ExportMetadata(BaseModel):
    """Metadata for an exported document."""
    
    page_id: int = Field(..., description="Confluence page ID")
    space_key: str = Field(..., description="Space key")
    space_name: str = Field(..., description="Space name")
    title: str = Field(..., description="Page title")
    url: Optional[str] = Field(None, description="Original Confluence URL")
    export_path: Path = Field(..., description="Local export file path")
    breadcrumb: str = Field("", description="Page breadcrumb path")
    labels: List[str] = Field(default_factory=list, description="Page labels")
    last_modified: Optional[datetime] = Field(None, description="Last modification time")
    content_hash: Optional[str] = Field(None, description="Content hash for change detection")


class ExportResult(BaseModel):
    """Result of an export operation."""
    
    customer_id: str = Field(..., description="Customer identifier")
    status: ExportStatus = Field(..., description="Export status")
    total_pages: int = Field(0, description="Total pages processed")
    successful_pages: int = Field(0, description="Successfully exported pages")
    failed_pages: int = Field(0, description="Failed page exports")
    total_attachments: int = Field(0, description="Total attachments processed")
    successful_attachments: int = Field(0, description="Successfully exported attachments")
    exported_documents: List[ExportMetadata] = Field(default_factory=list, description="List of exported documents")
    errors: List[str] = Field(default_factory=list, description="Error messages")
    start_time: datetime = Field(default_factory=datetime.utcnow, description="Export start time")
    end_time: Optional[datetime] = Field(None, description="Export end time")
    
    @property
    def duration(self) -> Optional[float]:
        """Export duration in seconds."""
        if self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return None
    
    @property
    def success_rate(self) -> float:
        """Success rate as percentage."""
        if self.total_pages == 0:
            return 0.0
        return (self.successful_pages / self.total_pages) * 100


class IndexingResult(BaseModel):
    """Result of RAG indexing operation."""
    
    customer_id: str = Field(..., description="Customer identifier")
    documents_processed: int = Field(0, description="Number of documents processed")
    documents_indexed: int = Field(0, description="Number of documents successfully indexed")
    chunks_created: int = Field(0, description="Number of chunks created")
    errors: List[str] = Field(default_factory=list, description="Indexing errors")
    start_time: datetime = Field(default_factory=datetime.utcnow, description="Indexing start time")
    end_time: Optional[datetime] = Field(None, description="Indexing end time")
    
    @property
    def duration(self) -> Optional[float]:
        """Indexing duration in seconds."""
        if self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return None


class QueryResult(BaseModel):
    """Result of a RAG query."""
    
    customer_id: str = Field(..., description="Customer identifier")
    question: str = Field(..., description="Original question")
    answer: str = Field(..., description="Generated answer")
    sources: List[ExportMetadata] = Field(default_factory=list, description="Source documents used")
    confidence_score: Optional[float] = Field(None, description="Confidence score if available")
    query_time: datetime = Field(default_factory=datetime.utcnow, description="Query timestamp")
    response_time_ms: Optional[float] = Field(None, description="Response time in milliseconds")


class CustomerState(BaseModel):
    """Current state of a customer's data."""
    
    customer_id: str = Field(..., description="Customer identifier")
    last_export: Optional[datetime] = Field(None, description="Last successful export time")
    last_index: Optional[datetime] = Field(None, description="Last successful indexing time")
    total_documents: int = Field(0, description="Total documents in vector store")
    total_chunks: int = Field(0, description="Total chunks in vector store")
    export_status: ExportStatus = Field(ExportStatus.PENDING, description="Current export status")
    
    # RAG-specific state
    rag_status: RAGStatus = Field(RAGStatus.NEVER_BUILT, description="Current RAG status")
    last_index_time: Optional[datetime] = Field(None, description="Last RAG index time")
    total_indexed_documents: int = Field(0, description="Total indexed documents")
    total_indexed_chunks: int = Field(0, description="Total indexed chunks")
    rag_collection_name: str = Field("", description="RAG collection name")
    
    data_path: Path = Field(..., description="Customer data directory path")
    config_path: Path = Field(..., description="Customer config file path")
    
    @property
    def is_ready_for_queries(self) -> bool:
        """Check if customer is ready for RAG queries."""
        return (
            self.last_export is not None and 
            self.last_index_time is not None and 
            self.total_indexed_documents > 0 and
            self.export_status == ExportStatus.COMPLETED and
            self.rag_status == RAGStatus.READY
        ) 

# ✅ SOLUTION: Unique collection per customer
def generate_collection_name(customer_id: str) -> str:
    safe_id = re.sub(r'[^a-zA-Z0-9_]', '_', customer_id.lower())
    return f"customer_{safe_id}_documents"

# Examples:
# customer_itagent_documents
# customer_acme_corp_documents 