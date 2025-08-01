"""RAG indexer using PostgreSQL+pgvector with ParentDocumentRetriever."""

import os
import re
from pathlib import Path
from typing import List
from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_postgres import PGVector
from langchain.retrievers import ParentDocumentRetriever
from langchain.indexes import SQLRecordManager, index

from ..shared.models import CustomerConfig


def extract_metadata_from_content(content: str) -> dict:
    """Extract metadata from markdown content."""
    lines = content.split('\n')
    
    # Default values
    title = "Untitled"
    breadcrumb_str = "Uncategorized"

    # Find Breadcrumb (usually the first line with '>')
    for line in lines:
        if '>' in line:
            # Extracts text from within markdown links like [Text](link)
            parts = re.findall(r'\[(.*?)\]', line)
            if parts:
                breadcrumb_str = ' > '.join(parts)
                break
    
    # Find Title (the first line starting with '# ')
    for line in lines:
        if line.startswith('# '):
            title = line.strip('# ').strip()
            break

    return {"title": title, "breadcrumb": breadcrumb_str}


class RAGIndexer:
    """RAG indexer using PostgreSQL+pgvector with ParentDocumentRetriever."""
    
    def __init__(self, customer_config: CustomerConfig):
        self.customer_config = customer_config
        self.embeddings = GoogleGenerativeAIEmbeddings(model=customer_config.embedding_model)
        self.vector_store = self._setup_vector_store()
        self.record_manager = self._setup_record_manager()
        
        # Simple in-memory docstore for parent documents
        from ..util.store import PostgresByteStore
        self.docstore = PostgresByteStore(customer_config.db_connection, customer_config.collection_name)
        
        # Parent splitter: Use entire documents (very large chunk size)
        self.parent_splitter = RecursiveCharacterTextSplitter(
            chunk_size=50000,  # Large enough to contain entire documents
            chunk_overlap=0,   # No overlap needed for full documents
            separators=["\n\n", "\n", ".", "!", "?", ",", " ", ""]
        )
        
        # Child splitter: Small chunks for precise semantic search
        self.child_splitter = RecursiveCharacterTextSplitter(
            chunk_size=customer_config.chunk_size,
            chunk_overlap=100,
            separators=["\n\n", "\n", ".", "!", "?", ",", " ", ""]
        )
        
        # Initialize parent document retriever
        self.retriever = ParentDocumentRetriever(
            vectorstore=self.vector_store,
            docstore=self.docstore,
            child_splitter=self.child_splitter,
            parent_splitter=self.parent_splitter,
        )
    
    def _setup_vector_store(self):
        """Setup PostgreSQL vector store"""
        return PGVector(
            embeddings=self.embeddings,
            collection_name=self.customer_config.collection_name,
            connection=self.customer_config.db_connection,
        )
    
    def _setup_record_manager(self):
        """Setup record manager for change tracking"""
        record_manager = SQLRecordManager(
            namespace=f"customer_{self.customer_config.customer_id}",
            db_url=self.customer_config.db_connection
        )
        record_manager.create_schema()
        return record_manager
    
    def build_index(self, export_path: Path) -> dict:
        """Build index from exported markdown files."""
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
                    "documents_indexed": 0,
                    "chunks_created": 0,
                    "timestamp": "",
                    "duration_seconds": 0
                }
            
            # Process documents with metadata
            processed_docs = []
            for doc in raw_docs:
                # Extract metadata from content
                doc_metadata = extract_metadata_from_content(doc.page_content)
                doc.metadata.update(doc_metadata)
                
                # Ensure source field for change tracking
                doc.metadata["source"] = doc.metadata.get("source", doc.metadata.get("file_path", "unknown"))
                processed_docs.append(doc)
            
            # Add documents to parent document retriever
            self.retriever.add_documents(processed_docs)
            
            # Get child documents for change tracking
            child_docs = self._get_child_documents(processed_docs)
            
            # Apply indexing API for change tracking
            result = index(
                child_docs,
                self.record_manager,
                self.vector_store,
                cleanup="incremental",
                source_id_key="source"
            )
            
            return {
                "status": "success",
                "documents_indexed": len(processed_docs),
                "chunks_created": len(child_docs),
                "timestamp": "",
                "duration_seconds": 0
            }
            
        except Exception as e:
            return {
                "status": "failed",
                "documents_indexed": 0,
                "chunks_created": 0,
                "timestamp": "",
                "duration_seconds": 0,
                "error": str(e)
            }
    
    def _get_child_documents(self, documents):
        """Extract child documents that were created by ParentDocumentRetriever"""
        child_docs = []
        for doc in documents:
            # Split into parent chunks
            parent_chunks = self.parent_splitter.split_documents([doc])
            for parent_chunk in parent_chunks:
                # Split parent into child chunks
                children = self.child_splitter.split_documents([parent_chunk])
                child_docs.extend(children)
        return child_docs

    def _clear_index(self):
        """Clear index from vector store"""
        self.vector_store.delete_collection()
        self.vector_store.create_collection()
        index([], self.record_manager, self.vector_store, cleanup="full", source_id_key="source")
        
        # Clear docstore
        from sqlalchemy import delete
        from ..util.store import ByteStore
        with self.docstore.Session() as session:
            session.execute(
                delete(ByteStore).where(
                    ByteStore.collection_name == self.customer_config.collection_name
                )
            )
            session.commit()


