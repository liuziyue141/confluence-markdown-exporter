"""Simplified query manager for document retrieval."""

from typing import Dict, Any, Optional, List
import os

from ..customers.customer_manager import CustomerManager
from ..shared.models import QueryResult
from .indexer_factory import IndexerFactory
from .base_indexer import BaseIndexer
from ..shared.utils import get_environment_variable
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger()
class QueryManager:
    """Simple query manager that only retrieves documents."""
    
    def __init__(self, customer_manager: CustomerManager):
        self.customer_manager = customer_manager
        self._indexers: Dict[str, BaseIndexer] = {}  # Cache indexer instances
        self._reranker = None  # Cache reranker instance
    
    def query(self, customer_id: str, question: str, top_k: int = 5) -> QueryResult:
        """Query documents for a customer with optional reranking."""
        logger.info(f"Querying for customer {customer_id} with question {question}")
        logger.info(f"Top K: {top_k}")
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
            
            # Load customer configuration
            config = self.customer_manager.load_customer(customer_id)

            # Get or create indexer from cache
            indexer = self._get_indexer(customer_id)
            
            # Determine how many documents to retrieve initially
            initial_k = top_k
            if config.enable_reranking:
                initial_k = max(top_k * config.rerank_top_k_multiplier, 50)
            
            # Use retriever to get relevant documents
            retriever = indexer.get_retriever({"k": initial_k})
            docs = retriever.invoke(question)
            logger.info(f"question: {question}")
            logger.info(f"Retrieved {len(docs)} documents")
            # Apply reranking if enabled and documents were retrieved
            reranking_applied = False
            relevance_scores = None
            
            if config.enable_reranking and docs:
                reranked_docs, scores = self._rerank_documents(
                    docs, question, top_k, config.rerank_model
                )
                logger.info(f"Retrieved after reranking {len(docs)} documents")
                if reranked_docs is not None:
                    docs = reranked_docs
                    relevance_scores = scores
                    reranking_applied = True
            # Convert to simple format
            documents = []
            for i, doc in enumerate(docs[:top_k]):
                doc_dict = {
                    "content": doc.page_content,
                    "metadata": doc.metadata,
                    "source": doc.metadata.get("source", "unknown")
                }                # Add relevance score if available
                if relevance_scores and i < len(relevance_scores):
                    if relevance_scores[i] <= 0.2:
                        break
                    doc_dict["relevance_score"] = relevance_scores[i]
                    logger.info(f"meta: {doc.metadata}")
                    logger.info(f"relevance_score: {relevance_scores[i]}")
                documents.append(doc_dict)
            return QueryResult(
                customer_id=customer_id,
                question=question,
                documents=documents,
                status="success",
                reranking_applied=reranking_applied,
                relevance_scores=relevance_scores[:len(documents)] if relevance_scores else None
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
    
    def _rerank_documents(
        self, 
        docs: List[Any], 
        query: str, 
        top_k: int,
        model: str
    ) -> tuple[Optional[List[Any]], Optional[List[float]]]:
        """
        Rerank documents using Cohere reranker.
        
        Returns:
            Tuple of (reranked_docs, relevance_scores) or (None, None) if reranking fails
        """
        try:
            # Lazy import to avoid dependency issues if not using reranking
            from langchain_cohere import CohereRerank
            
            # Initialize reranker if not cached
            if self._reranker is None:
                cohere_key = get_environment_variable("COHERE_KEY", required=False)
                if not cohere_key:
                    print("Warning: COHERE_KEY not found in environment, skipping reranking")
                    return None, None
                
                # Get model from environment or use provided model
                cohere_model = get_environment_variable("COHERE_MODEL", default=model, required=False)
                
                self._reranker = CohereRerank(
                    cohere_api_key=cohere_key,
                    model=cohere_model
                )
            
            # Rerank the documents
            reranked_results = self._reranker.rerank(
                documents=docs,
                query=query,
                top_n=min(top_k, len(docs))
            )
            
            # Extract reranked documents and scores
            reranked_docs = []
            relevance_scores = []
            
            # The rerank method returns a list of dictionaries with 'index' and 'relevance_score' keys
            for result in reranked_results:
                if isinstance(result, dict):
                    # Get the original document by index
                    original_index = result.get('index', 0)
                    if original_index < len(docs):
                        reranked_docs.append(docs[original_index])
                        relevance_scores.append(result.get('relevance_score', 0.0))
                else:
                    # Fallback for other formats
                    reranked_docs.append(docs[0] if docs else None)
                    relevance_scores.append(0.0)
            
            return reranked_docs, relevance_scores
            
        except ImportError:
            print("Warning: langchain-cohere not installed, skipping reranking")
            return None, None
        except Exception as e:
            print(f"Warning: Reranking failed with error: {e}, using original ranking")
            return None, None