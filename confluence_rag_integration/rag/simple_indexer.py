"""Simple indexer using direct vector store with markdown header splitting."""

import re
from pathlib import Path
from typing import Dict, Any, List

from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain.text_splitter import MarkdownHeaderTextSplitter
from langchain_core.documents import Document
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_postgres import PGVector
from langchain.indexes import SQLRecordManager, index

from .base_indexer import BaseIndexer
from ..shared.models import CustomerConfig


class SimpleIndexer(BaseIndexer):
    """Simple indexer using markdown header splitting and direct vector store."""
    
    def __init__(self, customer_config: CustomerConfig):
        self.customer_config = customer_config
        self.embeddings = GoogleGenerativeAIEmbeddings(model=customer_config.embedding_model)
        self.vector_store = PGVector(
            embeddings=self.embeddings,
            collection_name=customer_config.collection_name,
            connection=customer_config.db_connection,
        )
        
        self.record_manager = SQLRecordManager(
            namespace=f"customer_{customer_config.customer_id}",
            db_url=customer_config.db_connection
        )
        self.record_manager.create_schema()
        
        # Markdown header splitter configuration
        self.headers_to_split_on = [("##", "Header 2")]
        self.markdown_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=self.headers_to_split_on, 
            strip_headers=False
        )
    
    def extract_metadata_from_content(self, content: str) -> dict:
        """Parse markdown file to find breadcrumb and title."""
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
    
    def build_index(self, export_path: Path) -> Dict[str, Any]:
        """Build index from exported markdown files."""
        # Load documents
        loader = DirectoryLoader(
            str(export_path),
            glob="**/*.md",
            loader_cls=TextLoader,
            show_progress=True,
        )
        docs = loader.load()
        
        if not docs:
            return {
                "status": "no_documents",
                "documents_indexed": 0,
                "chunks_created": 0,
            }

        all_enriched_chunks = []
        
        for doc in docs:
            # Extract metadata from the full document content
            doc_metadata = self.extract_metadata_from_content(doc.page_content)

            # Split the document into text chunks
            chunks = self.markdown_splitter.split_text(doc.page_content)

            # Add the document-level metadata to each chunk
            for chunk in chunks:
                # If chunk is just text, convert to Document
                if isinstance(chunk, str):
                    chunk = Document(page_content=chunk, metadata={})
                elif not isinstance(chunk, Document):
                    chunk = Document(
                        page_content=chunk.page_content if hasattr(chunk, 'page_content') else str(chunk),
                        metadata=chunk.metadata if hasattr(chunk, 'metadata') else {}
                    )
                
                # Update metadata
                chunk.metadata.update(doc_metadata)
                
                # Add source field for record manager tracking
                chunk.metadata["source"] = doc.metadata.get(
                    "source", 
                    doc.metadata.get("file_path", f"{export_path}/{doc_metadata['title']}.md")
                )
                
                all_enriched_chunks.append(chunk)

        # Index documents with automatic duplicate detection
        result = index(
            all_enriched_chunks,
            self.record_manager,
            self.vector_store,
            cleanup="incremental",
            source_id_key="source"
        )
        
        return {
            "status": "success",
            "documents_indexed": len(docs),
            "chunks_created": result.get('num_added', 0) + result.get('num_updated', 0),
        }
    
    def clear_index(self) -> None:
        """Clear the existing index."""
        # Delete all documents
        index(
            [],
            self.record_manager,
            self.vector_store,
            cleanup="full",
            source_id_key="source"
        )
    
    def get_retriever(self):
        """Get the vector store as retriever."""
        return self.vector_store.as_retriever()