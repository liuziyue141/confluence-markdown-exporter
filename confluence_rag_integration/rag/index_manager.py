"""Index manager to orchestrate indexing operations."""

import time
from datetime import datetime
from pathlib import Path

from ..customers.customer_manager import CustomerManager
from ..shared.models import IndexResult
from .indexer_factory import IndexerFactory


class IndexManager:
    """Orchestrates indexing operations for customers."""
    
    def __init__(self, customer_manager: CustomerManager):
        self.customer_manager = customer_manager
    
    def build_index(self, customer_id: str) -> IndexResult:
        """Build RAG index for a customer."""
        start_time = time.time()
        
        try:
            # Load customer config
            config = self.customer_manager.load_customer(customer_id)
            
            # Get export path
            export_path = self.customer_manager.base_path / customer_id / "exports"
            
            if not export_path.exists():
                duration = time.time() - start_time
                result = IndexResult(
                    status="no_documents",
                    documents_indexed=0,
                    chunks_created=0,
                    timestamp=datetime.now().isoformat(),
                    duration_seconds=duration
                )
                self.customer_manager.update_index_state(customer_id, result.__dict__)
                return result
            
            # Create indexer and build index
            indexer = IndexerFactory.create_indexer(config)
            index_result = indexer.build_index(export_path)
            
            # Convert to IndexResult
            duration = time.time() - start_time
            result = IndexResult(
                status=index_result["status"],
                documents_indexed=index_result["documents_indexed"],
                chunks_created=index_result["chunks_created"],
                timestamp=datetime.now().isoformat(),
                duration_seconds=duration
            )
            
            # Update state
            self.customer_manager.update_index_state(customer_id, result.__dict__)
            
            return result
            
        except Exception as e:
            duration = time.time() - start_time
            result = IndexResult(
                status="failed",
                documents_indexed=0,
                chunks_created=0,
                timestamp=datetime.now().isoformat(),
                duration_seconds=duration
            )
            
            self.customer_manager.update_index_state(customer_id, result.__dict__)
            return result