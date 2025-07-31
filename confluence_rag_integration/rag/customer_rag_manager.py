"""Customer-aware RAG manager with complete data isolation."""

import os
import json
from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path

from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_postgres import PGVector
from langchain.retrievers import ParentDocumentRetriever
from langchain.indexes import SQLRecordManager, index

from ..shared.models import CustomerConfig, RAGStatus, IndexingResult
from ..shared.utils import extract_metadata_from_content
from store import PostgresByteStore


class CustomerRAGManager:
    """
    Customer-aware RAG system with complete data isolation.
    
    Key Features:
    - Customer-specific vector collections
    - Isolated document processing  
    - Parent document retrieval per customer
    - Incremental indexing with change detection
    """
    
    def __init__(self, customer_config: CustomerConfig):
        """
        Initialize customer-specific RAG manager.
        
        Args:
            customer_config: Customer configuration including RAG settings
        """
        self.customer_config = customer_config
        self.customer_id = customer_config.customer_id
        self.rag_config = customer_config.rag
        
        # Initialize components
        self.embeddings = GoogleGenerativeAIEmbeddings(
            model=self.rag_config.embedding_model
        )
        self.vector_store = self._setup_vector_store()
        self.record_manager = self._setup_record_manager()
        
        # Customer-specific document storage
        self.docstore = PostgresByteStore(
            self.rag_config.connection_string, 
            self.rag_config.collection_name
        )
        
        # Configure document splitters
        self.parent_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.rag_config.parent_chunk_size,
            chunk_overlap=0,
            separators=["\n\n", "\n", ".", "!", "?", ",", " ", ""]
        )
        
        self.child_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.rag_config.chunk_size,
            chunk_overlap=self.rag_config.chunk_overlap,
            separators=["\n\n", "\n", ".", "!", "?", ",", " ", ""]
        )
        
        # Initialize parent document retriever
        self.retriever = ParentDocumentRetriever(
            vectorstore=self.vector_store,
            docstore=self.docstore,
            child_splitter=self.child_splitter,
            parent_splitter=self.parent_splitter,
        ) if self.rag_config.enable_parent_retriever else None
        
    def _setup_vector_store(self) -> PGVector:
        """Setup customer-specific PostgreSQL vector store."""
        return PGVector(
            embeddings=self.embeddings,
            collection_name=self.rag_config.collection_name,
            connection=self.rag_config.connection_string,
        )
    
    def _setup_record_manager(self) -> SQLRecordManager:
        """Setup customer-specific record manager for change tracking."""
        record_manager = SQLRecordManager(
            namespace=f"{self.rag_config.collection_name}_records",
            db_url=self.rag_config.connection_string
        )
        record_manager.create_schema()
        return record_manager
    
    def build_index(self, export_path: Path) -> Dict[str, Any]:
        """
        Build RAG index from exported documents.
        
        Args:
            export_path: Path to exported markdown files
            
        Returns:
            Dictionary with indexing results and statistics
        """
        start_time = datetime.utcnow()
        
        try:
            # Load documents from customer's export directory
            loader = DirectoryLoader(
                str(export_path),
                glob="**/*.md",
                loader_cls=TextLoader,
                show_progress=True
            )
            raw_docs = loader.load()
            
            if not raw_docs:
                return {
                    "status": "no_documents",
                    "message": f"No documents found in {export_path}",
                    "processed": 0,
                    "indexed": 0,
                    "duration": 0
                }
            
            # Process documents with metadata extraction
            processed_docs = self._process_documents(raw_docs)
            
            # Use parent document retriever for hierarchical storage
            if self.retriever:
                self.retriever.add_documents(processed_docs)
            
            # Get child documents for change tracking
            child_docs = self._get_child_documents(processed_docs)
            
            # Apply indexing with change tracking (full rebuild)
            index_result = index(
                child_docs,
                self.record_manager,
                self.vector_store,
                cleanup="full",
                source_id_key="source"
            )
            
            end_time = datetime.utcnow()
            duration = (end_time - start_time).total_seconds()
            
            return {
                "status": "success",
                "customer_id": self.customer_id,
                "collection_name": self.rag_config.collection_name,
                "documents_processed": len(processed_docs),
                "documents_indexed": len(processed_docs),
                "chunks_created": len(child_docs),
                "index_result": index_result,
                "duration": duration,
                "start_time": start_time,
                "end_time": end_time
            }
            
        except Exception as e:
            end_time = datetime.utcnow()
            duration = (end_time - start_time).total_seconds()
            
            return {
                "status": "error",
                "customer_id": self.customer_id,
                "error": str(e),
                "duration": duration,
                "processed": 0,
                "indexed": 0
            }
    
    def update_index(self, export_path: Path) -> Dict[str, Any]:
        """
        Update RAG index incrementally.
        
        Args:
            export_path: Path to exported markdown files
            
        Returns:
            Dictionary with update results and statistics
        """
        start_time = datetime.utcnow()
        
        try:
            # Load documents
            loader = DirectoryLoader(
                str(export_path),
                glob="**/*.md",
                loader_cls=TextLoader,
                show_progress=True
            )
            raw_docs = loader.load()
            
            if not raw_docs:
                return {
                    "status": "no_documents",
                    "message": f"No documents found in {export_path}",
                    "updated": 0,
                    "duration": 0
                }
            
            # Process documents
            processed_docs = self._process_documents(raw_docs)
            
            # Add to parent document retriever
            if self.retriever:
                self.retriever.add_documents(processed_docs)
            
            # Get child documents
            child_docs = self._get_child_documents(processed_docs)
            
            # Apply incremental indexing
            index_result = index(
                child_docs,
                self.record_manager,
                self.vector_store,
                cleanup="incremental",
                source_id_key="source"
            )
            
            end_time = datetime.utcnow()
            duration = (end_time - start_time).total_seconds()
            
            return {
                "status": "success",
                "customer_id": self.customer_id,
                "collection_name": self.rag_config.collection_name,
                "documents_processed": len(processed_docs),
                "chunks_created": len(child_docs),
                "index_result": index_result,
                "duration": duration,
                "start_time": start_time,
                "end_time": end_time
            }
            
        except Exception as e:
            end_time = datetime.utcnow()
            duration = (end_time - start_time).total_seconds()
            
            return {
                "status": "error",
                "customer_id": self.customer_id,
                "error": str(e),
                "duration": duration,
                "updated": 0
            }
    
    def get_retriever(self) -> ParentDocumentRetriever:
        """
        Get customer-specific retriever.
        
        Returns:
            Parent document retriever for this customer
            
        Raises:
            ValueError: If parent retriever is not enabled
        """
        if not self.retriever:
            raise ValueError(f"Parent retriever not enabled for customer {self.customer_id}")
        
        return self.retriever
    
    def query(self, question: str, top_k: int = 3) -> List[Document]:
        """
        Query customer-specific knowledge base.
        
        Args:
            question: Question to ask
            top_k: Number of documents to retrieve
            
        Returns:
            List of relevant documents from customer's collection only
        """
        if not self.retriever:
            # Fallback to direct vector store query
            return self.vector_store.similarity_search(question, k=top_k)
        
        return self.retriever.get_relevant_documents(question)[:top_k]
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get RAG statistics for this customer.
        
        Returns:
            Dictionary with customer RAG statistics
        """
        try:
            # Count documents in docstore
            docstore_keys = list(self.docstore.yield_keys())
            docstore_count = len(docstore_keys)
        except:
            docstore_count = "Unknown"
        
        try:
            # Get vector store stats (this might need custom implementation)
            # For now, we'll use a simple count
            vector_docs = self.vector_store.similarity_search("test", k=1)
            vector_store_accessible = True
        except:
            vector_store_accessible = False
        
        return {
            "customer_id": self.customer_id,
            "collection_name": self.rag_config.collection_name,
            "parent_documents": docstore_count,
            "vector_store_accessible": vector_store_accessible,
            "parent_retriever_enabled": self.rag_config.enable_parent_retriever,
            "embedding_model": self.rag_config.embedding_model,
            "chunk_size": self.rag_config.chunk_size,
            "parent_chunk_size": self.rag_config.parent_chunk_size,
        }
    
    def cleanup_index(self) -> bool:
        """
        Cleanup customer's RAG index.
        
        Returns:
            True if cleanup successful, False otherwise
        """
        try:
            # Clear vector store collection
            # Note: This would need proper implementation based on PGVector capabilities
            # For now, we'll use the record manager to track what needs cleanup
            
            # Clear document store
            keys_to_delete = list(self.docstore.yield_keys())
            for key in keys_to_delete:
                self.docstore.delete([key])
            
            return True
        except Exception as e:
            print(f"Error cleaning up index for customer {self.customer_id}: {e}")
            return False
    
    def _process_documents(self, raw_docs: List[Document]) -> List[Document]:
        """Process documents with metadata extraction."""
        processed_docs = []
        
        for doc in raw_docs:
            # Extract metadata from content
            doc_metadata = extract_metadata_from_content(doc.page_content)
            doc.metadata.update(doc_metadata)
            
            # Ensure source field for change tracking
            doc.metadata["source"] = doc.metadata.get("source", doc.metadata.get("file_path", "unknown"))
            
            # Add customer identifier to metadata
            doc.metadata["customer_id"] = self.customer_id
            
            processed_docs.append(doc)
        
        return processed_docs
    
    def _get_child_documents(self, documents: List[Document]) -> List[Document]:
        """Extract child documents for indexing."""
        child_docs = []
        
        for doc in documents:
            # Split into parent chunks
            parent_chunks = self.parent_splitter.split_documents([doc])
            for parent_chunk in parent_chunks:
                # Split parent into child chunks
                children = self.child_splitter.split_documents([parent_chunk])
                child_docs.extend(children)
        
        return child_docs 