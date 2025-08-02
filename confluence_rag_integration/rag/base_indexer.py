"""Base indexer interface for RAG indexing strategies."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Any


class BaseIndexer(ABC):
    """Abstract base class for RAG indexers."""
    
    @abstractmethod
    def build_index(self, export_path: Path) -> Dict[str, Any]:
        """
        Build the index from exported markdown files.
        
        Returns dict with: status, documents_indexed, chunks_created
        """
        pass
    
    @abstractmethod
    def clear_index(self) -> None:
        """Clear the existing index."""
        pass
    
    @abstractmethod
    def get_retriever(self):
        """Get the retriever for query operations."""
        pass