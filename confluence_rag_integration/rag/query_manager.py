"""Customer-specific RAG query management."""

from typing import List, Optional
from datetime import datetime

from langchain_core.documents import Document

from ..shared.models import CustomerConfig, QueryResult, ExportMetadata
from .customer_rag_manager import CustomerRAGManager


class CustomerQueryManager:
    """
    Handle customer-specific RAG queries with retrieval optimization.
    
    Features:
    - Customer-isolated query processing
    - Query result formatting with metadata
    - Performance tracking per customer
    - Source document attribution
    """
    
    def __init__(self, customer_config: CustomerConfig):
        """
        Initialize customer query manager.
        
        Args:
            customer_config: Customer configuration including RAG settings
        """
        self.customer_config = customer_config
        self.customer_id = customer_config.customer_id
        self.rag_manager = CustomerRAGManager(customer_config)
        
        # Get the retriever instance
        try:
            self.retriever = self.rag_manager.get_retriever()
        except ValueError:
            # Fallback if parent retriever not enabled
            self.retriever = None
    
    def query(self, question: str, top_k: int = 3) -> QueryResult:
        """
        Execute customer-specific RAG query.
        
        Args:
            question: Question to ask
            top_k: Number of documents to retrieve
            
        Returns:
            QueryResult with answer and source attribution
        """
        start_time = datetime.utcnow()
        
        try:
            # Use customer's isolated vector collection
            if self.retriever:
                documents = self.retriever.get_relevant_documents(question)[:top_k]
            else:
                documents = self.rag_manager.query(question, top_k)
            
            # Convert documents to source metadata
            sources = []
            for doc in documents:
                metadata = ExportMetadata(
                    page_id=doc.metadata.get('page_id', 0),
                    space_key=doc.metadata.get('space_key', 'unknown'),
                    space_name=doc.metadata.get('space_name', 'Unknown Space'),
                    title=doc.metadata.get('title', 'Untitled'),
                    url=doc.metadata.get('url'),
                    export_path=doc.metadata.get('source', 'unknown'),
                    breadcrumb=doc.metadata.get('breadcrumb', ''),
                    labels=doc.metadata.get('labels', []),
                    last_modified=doc.metadata.get('last_modified'),
                    content_hash=doc.metadata.get('content_hash')
                )
                sources.append(metadata)
            
            end_time = datetime.utcnow()
            response_time_ms = (end_time - start_time).total_seconds() * 1000
            
            # For now, return the raw context as "answer"
            # In a full implementation, this would be passed to an LLM
            context_text = "\n\n---\n\n".join([
                f"**{doc.metadata.get('title', 'Untitled')}**\n{doc.page_content[:500]}..."
                for doc in documents
            ])
            
            return QueryResult(
                customer_id=self.customer_id,
                question=question,
                answer=f"Based on the retrieved documents:\n\n{context_text}",
                sources=sources,
                confidence_score=None,  # Could be implemented based on similarity scores
                query_time=start_time,
                response_time_ms=response_time_ms
            )
            
        except Exception as e:
            end_time = datetime.utcnow()
            response_time_ms = (end_time - start_time).total_seconds() * 1000
            
            return QueryResult(
                customer_id=self.customer_id,
                question=question,
                answer=f"Error processing query: {str(e)}",
                sources=[],
                confidence_score=0.0,
                query_time=start_time,
                response_time_ms=response_time_ms
            )
    
    def get_relevant_documents(self, question: str, top_k: int = 3) -> List[Document]:
        """
        Get relevant documents without generating an answer.
        
        Args:
            question: Question to search for
            top_k: Number of documents to retrieve
            
        Returns:
            List of relevant documents from customer's collection
        """
        return self.rag_manager.query(question, top_k)
    
    def get_collection_stats(self) -> dict:
        """
        Get statistics about customer's RAG collection.
        
        Returns:
            Dictionary with collection statistics
        """
        return self.rag_manager.get_stats()
    
    def is_ready(self) -> bool:
        """
        Check if customer's RAG system is ready for queries.
        
        Returns:
            True if ready, False otherwise
        """
        try:
            # Try a simple test query
            test_docs = self.rag_manager.query("test", 1)
            return len(test_docs) >= 0  # Even 0 results means system is working
        except Exception:
            return False


class RAGFactory:
    """
    Factory for creating customer-specific RAG managers and query managers on demand.
    
    Provides lazy loading and caching to optimize memory usage.
    """
    
    _rag_instances = {}
    _query_instances = {}
    
    @classmethod
    def get_rag_manager(cls, customer_config: CustomerConfig) -> CustomerRAGManager:
        """
        Get or create RAG manager for customer (with caching).
        
        Args:
            customer_config: Customer configuration
            
        Returns:
            CustomerRAGManager instance for the customer
        """
        customer_id = customer_config.customer_id
        
        if customer_id not in cls._rag_instances:
            cls._rag_instances[customer_id] = CustomerRAGManager(customer_config)
        
        return cls._rag_instances[customer_id]
    
    @classmethod
    def get_query_manager(cls, customer_config: CustomerConfig) -> CustomerQueryManager:
        """
        Get or create query manager for customer (with caching).
        
        Args:
            customer_config: Customer configuration
            
        Returns:
            CustomerQueryManager instance for the customer
        """
        customer_id = customer_config.customer_id
        
        if customer_id not in cls._query_instances:
            cls._query_instances[customer_id] = CustomerQueryManager(customer_config)
        
        return cls._query_instances[customer_id]
    
    @classmethod
    def clear_cache(cls, customer_id: Optional[str] = None):
        """
        Clear cached instances.
        
        Args:
            customer_id: Specific customer to clear, or None for all
        """
        if customer_id:
            cls._rag_instances.pop(customer_id, None)
            cls._query_instances.pop(customer_id, None)
        else:
            cls._rag_instances.clear()
            cls._query_instances.clear() 