"""Simplified query manager for document retrieval."""

from typing import Dict, Any

from ..customers.customer_manager import CustomerManager
from ..shared.models import QueryResult
from .indexer_factory import IndexerFactory
from .base_indexer import BaseIndexer


class QueryManager:
    """Simple query manager that only retrieves documents."""
    
    def __init__(self, customer_manager: CustomerManager):
        self.customer_manager = customer_manager
        self._indexers: Dict[str, BaseIndexer] = {}  # Cache indexer instances
    
    def query(self, customer_id: str, question: str, top_k: int = 5) -> QueryResult:
        """Query documents for a customer."""
        try:
            # Check if customer is ready for queries
            state = self.customer_manager.get_state(customer_id)
            if not state.is_ready_for_queries:
                return QueryResult(
                    customer_id=customer_id,
                    question=question,
                    documents=[],
                    status="error",
                    error="Customer RAG system not ready. Run export and index first."
                )
            
            # Get or create indexer from cache
            indexer = self._get_indexer(customer_id)
            
            # Use retriever to get relevant documents
            retriever = indexer.get_retriever()
            docs = retriever.invoke(question, search_kwargs={"k": top_k})
            
            # Convert to simple format
            documents = []
            for doc in docs:
                documents.append({
                    "content": doc.page_content,
                    "metadata": doc.metadata,
                    "source": doc.metadata.get("source", "unknown")
                })
            
            return QueryResult(
                customer_id=customer_id,
                question=question,
                documents=documents,
                status="success"
            )
            
        except Exception as e:
            return QueryResult(
                customer_id=customer_id,
                question=question,
                documents=[],
                status="error",
                error=str(e)
            )
    
    def _get_indexer(self, customer_id: str) -> BaseIndexer:
        """Get or create cached indexer for customer."""
        if customer_id not in self._indexers:
            config = self.customer_manager.load_customer(customer_id)
            self._indexers[customer_id] = IndexerFactory.create_indexer(config)
        
        return self._indexers[customer_id]