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
from ..shared.utils import extract_metadata_from_content, has_meaningful_content


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
        self.headers_to_split_on = [("#", "Header 1"), ("##", "Header 2"), ("###", "Header 3")]
        self.markdown_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=self.headers_to_split_on, strip_headers=False
        )
    from typing import List
    def chunking(self, docs: List[Document], 
        include_context_in_text: bool = True,
        min_content_length: int = 50,
        content_density_threshold: float = 0.3,
        verbose: bool = False)  -> List[Document]:
        """
        Enhanced chunking that prevents empty header chunks and filters metadata blocks.
        
        Args:
            docs: List of documents to chunk
            include_context_in_text: Whether to prepend hierarchical context to chunk text
            min_content_length: Minimum meaningful content required in a chunk
            content_density_threshold: Minimum ratio of content to total text
            verbose: Print debug information about chunking decisions
        
        Returns:
            List of chunked documents with enriched metadata
        """

        # Initialize the markdown splitter
        markdown_splitter = self.markdown_splitter

        all_chunks = []

        for doc in docs:
            # Extract article-level metadata from potential metadata blocks
            doc_metadata = extract_metadata_from_content(doc.page_content)
            cleaned_content = doc_metadata.pop('processed_content')

            # Split by headers first
            header_chunks = markdown_splitter.split_text(cleaned_content)

            # Process chunks and merge empty headers if needed
            processed_chunks = []
            i = 0
            while i < len(header_chunks):
                chunk = header_chunks[i]

                # Build hierarchical context
                hierarchy = []
                for header_level in ["Header 1", "Header 2", "Header 3", "Header 4"]:
                    if header_level in chunk.metadata:
                        hierarchy.append(chunk.metadata[header_level])

                context_path = " > ".join(hierarchy) if hierarchy else doc_metadata.get("title", "Document")

                # Check if this chunk has meaningful content
                chunk_has_content = has_meaningful_content(
                    chunk.page_content,
                    min_content_length,
                    content_density_threshold
                )


                if verbose:
                    if not chunk_has_content:
                        print(f"Empty chunk detected: {context_path[:50]}...")

                # Skip chunks without meaningful content that couldn't be merged
                if not chunk_has_content:
                    if verbose:
                        print(f"Skipping empty chunk: {context_path[:50]}...")
                    i += 1
                    continue
                # Add context to text if requested
                if include_context_in_text and context_path:
                    chunk.page_content = f"[{context_path}]\n{chunk.page_content}"

                # Enrich metadata for regular chunks
                chunk.metadata.update({
                    'source': doc.metadata.get('source', ''),
                    'title': doc_metadata['title'],
                    'breadcrumb': doc_metadata['breadcrumb'],
                    'url': doc_metadata['url'],
                    'tags': doc_metadata['tags'],
                    'hierarchy_path': context_path,
                    'properties': doc_metadata['properties']
                })

                processed_chunks.append(chunk)

                i += 1

            all_chunks.extend(processed_chunks)

        if verbose:
            print(f"\nChunking complete: {len(all_chunks)} final chunks from {len(docs)} documents")

        return all_chunks
        
    from typing import List, Dict, Any

    def index_with_retry(self, batch: List, max_retries: int = 3, initial_delay: float = 1.0) -> Dict[str, int]:
        """
        Index a batch with retry logic and exponential backoff.
        
        Args:
            batch: The batch of chunks to index
            record_manager: The record manager instance
            vector_store: The vector store instance
            max_retries: Maximum number of retry attempts
            initial_delay: Initial delay in seconds before first retry
        
        Returns:
            Dictionary with indexing results
        """
        delay = initial_delay
        last_exception = None
        
        for attempt in range(max_retries + 1):
            try:
                result = index(
                    batch,
                    self.record_manager,
                    self.vector_store,
                    cleanup="incremental",
                    source_id_key="source"
                )
                return result
            except Exception as e:
                import time
                last_exception = e
                
                if attempt < max_retries:
                    print(f"  ⚠️ Indexing failed (attempt {attempt + 1}/{max_retries + 1}): {str(e)}")
                    print(f"  ⏳ Retrying in {delay:.1f} seconds...")
                    
                    time.sleep(delay)
                    delay *= 2  # Exponential backoff
                else:
                    print(f"  ❌ Failed after {max_retries + 1} attempts: {str(e)}")
                    raise last_exception


    def build_index(self, export_path: Path, min_content_length: int = 50, content_density_threshold: float = 0.3, verbose: bool = False) -> Dict[str, Any]:
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

        chunks = self.chunking(docs,
        include_context_in_text=True,
        min_content_length=min_content_length,
        content_density_threshold=content_density_threshold,
        verbose=verbose)

# Display sample chunk
        batch_size = 500
        total_added = 0
        total_updated = 0
        total_skipped = 0
        total_deleted = 0
        for i in range(0, len(chunks), batch_size):
            print(f"Indexing batch {i//batch_size + 1} of {len(chunks)//batch_size}")
            batch = chunks[i:i+batch_size]
            result = self.index_with_retry(batch)
            total_added += result.get('num_added', 0)
            total_updated += result.get('num_updated', 0)
            total_skipped += result.get('num_skipped', 0)
            total_deleted += result.get('num_deleted', 0)

        print(f"✅ Indexing complete:")
        print(f"  Added: {total_added}")
        print(f"  Updated: {total_updated}")
        print(f"  Skipped: {total_skipped}")
        print(f"  Deleted: {total_deleted}")


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
