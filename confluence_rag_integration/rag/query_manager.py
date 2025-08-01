"""Simplified query manager for document retrieval."""

from typing import Dict, Any

from ..customers.customer_manager import CustomerManager
from ..shared.models import QueryResult
from .rag_indexer import RAGIndexer


class QueryManager:
    """Simple query manager that only retrieves documents."""
    
    def __init__(self, customer_manager: CustomerManager):
        self.customer_manager = customer_manager
        self._indexers: Dict[str, RAGIndexer] = {}  # Cache RAGIndexer instances
    
    def query(self, customer_id: str, question: str, top_k: int = 3) -> QueryResult:
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
            
            # Get or create RAGIndexer from cache
            indexer = self._get_indexer(customer_id)
            
            # Use retriever to get relevant documents
            docs = indexer.retriever.invoke(question)[:top_k]
            
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
    
    def _get_indexer(self, customer_id: str) -> RAGIndexer:
        """Get or create cached RAGIndexer for customer."""
        if customer_id not in self._indexers:
            config = self.customer_manager.load_customer(customer_id)
            self._indexers[customer_id] = RAGIndexer(config)
        
        return self._indexers[customer_id]