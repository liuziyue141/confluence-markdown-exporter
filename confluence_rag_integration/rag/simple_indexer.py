"""Simple indexer using direct vector store with markdown header splitting."""

from pathlib import Path
from typing import Dict, Any

from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain.text_splitter import MarkdownHeaderTextSplitter
from langchain_core.documents import Document
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_postgres import PGVector
from langchain.indexes import SQLRecordManager, index

from .base_indexer import BaseIndexer
from ..shared.models import CustomerConfig
from ..shared.utils import extract_metadata_from_content


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
            db_url=customer_config.db_connection,
        )
        self.record_manager.create_schema()

        # Markdown header splitter configuration
        self.headers_to_split_on = [("##", "Header 2")]
        self.markdown_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=self.headers_to_split_on, strip_headers=False
        )

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
            doc_metadata = extract_metadata_from_content(doc.page_content)

            # Split the document into chunks with header metadata
            # split_text returns Document objects with header metadata
            chunks = self.markdown_splitter.split_text(doc.page_content)

            # Process each chunk to merge metadata
            for chunk in chunks:
                # Ensure chunk is a Document object
                if not isinstance(chunk, Document):
                    # This shouldn't happen with split_text, but handle it defensively
                    chunk = Document(
                        page_content=str(chunk),
                        metadata={}
                    )

                # Merge document-level metadata with header metadata from splitter
                # Header metadata (from splitter) takes precedence for headers
                # Document metadata provides title, breadcrumb, url, tags
                merged_metadata = {**doc_metadata, **chunk.metadata}

                # Add source field for record manager tracking
                merged_metadata["source"] = doc.metadata.get(
                    "source",
                    doc.metadata.get("file_path", f"{export_path}/{doc_metadata['title']}.md"),
                )

                # Prepend title to chunk content for better retrieval
                enriched_content = f"Document: {doc_metadata['title']}\n\n{chunk.page_content}"

                # Create final chunk with merged metadata
                enriched_chunk = Document(
                    page_content=enriched_content,
                    metadata=merged_metadata
                )

                all_enriched_chunks.append(enriched_chunk)

        # Index documents with automatic duplicate detection
        # Process in batches to avoid overwhelming the system
        batch_size = 100
        total_added = 0
        total_updated = 0
        total_skipped = 0
        total_deleted = 0
        
        for i in range(0, len(all_enriched_chunks), batch_size):
            batch = all_enriched_chunks[i:i+batch_size]
            
            try:
                result = index(
                    batch,
                    self.record_manager,
                    self.vector_store,
                    cleanup="incremental",
                    source_id_key="source"
                )
                
                total_added += result.get('num_added', 0)
                total_updated += result.get('num_updated', 0)
                total_skipped += result.get('num_skipped', 0)
                total_deleted += result.get('num_deleted', 0)
                
            except Exception as e:
                print(f"Warning: Error in batch {i//batch_size + 1}: {e}")
                continue

        return {
            "status": "success",
            "documents_indexed": len(docs),
            "chunks_created": total_added + total_updated,
        }

    def clear_index(self) -> None:
        """Clear the existing index."""
        # Delete all documents
        index([], self.record_manager, self.vector_store, cleanup="full", source_id_key="source")

    def get_retriever(self, kwargs: dict = {}):
        """Get the vector store as retriever."""
        return self.vector_store.as_retriever(search_kwargs=kwargs)
