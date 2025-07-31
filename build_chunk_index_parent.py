import os
import re
from typing import List
from dotenv import load_dotenv
from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain.chat_models import init_chat_model
from langchain_postgres import PGVector
from langchain.retrievers import ParentDocumentRetriever
from langchain.storage import InMemoryStore
from langchain.indexes import SQLRecordManager, index
from store import PostgresByteStore

# Load environment variables
load_dotenv()

# Configuration
MARKDOWN_EXPORT_PATH = "/Users/lindalee/confluence_exp"
LLM_MODEL = "gemini-2.5-flash"
EMBEDDING_MODEL = "gemini-embedding-001"
COLLECTION_NAME = "postgres/confluence_parent_docs"
CONNECTION_STRING = "postgresql+psycopg://tim_itagent:Apple3344!@localhost:5432/confluence_exp"

def extract_metadata_from_content(content: str) -> dict:
    """
    Parses the full text of a markdown file to find the breadcrumb and title.

    Args:
        content: The raw string content of a .md file.

    Returns:
        A dictionary containing the 'title' and 'breadcrumb'.
    """
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
                break # Stop after finding the first breadcrumb line
    
    # Find Title (the first line starting with '# ')
    for line in lines:
        if line.startswith('# '):
            title = line.strip('# ').strip()
            break # Stop after finding the main title

    return {"title": title, "breadcrumb": breadcrumb_str}

class SmartParentDocumentRAG:
    """
    Enhanced RAG system using Parent Document Retriever with smart change tracking.
    
    Key features:
    - Returns ENTIRE parent documents for maximum context
    - Child chunks used for precise semantic search targeting
    - Incremental updates using LangChain indexing API
    - No hypothetical question generation for efficiency
    - Semantic text splitting for precise retrieval
    """
    
    def __init__(self):
        """Initialize the smart parent document RAG system"""
        self.embeddings = GoogleGenerativeAIEmbeddings(model=EMBEDDING_MODEL)
        self.vector_store = self._setup_vector_store()
        self.record_manager = self._setup_record_manager()
        
        # Parent document storage
        self.docstore = PostgresByteStore(CONNECTION_STRING, COLLECTION_NAME) # Can upgrade to persistent storage
        
        # Parent splitter: Use entire documents (very large chunk size)
        self.parent_splitter = RecursiveCharacterTextSplitter(
            chunk_size=50000,  # Large enough to contain entire documents
            chunk_overlap=0,   # No overlap needed for full documents
            separators=["\n\n", "\n", ".", "!", "?", ",", " ", ""]
        )
        
        # Child splitter: Small chunks for precise semantic search
        self.child_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
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
            collection_name=COLLECTION_NAME,
            connection=CONNECTION_STRING,
        )
    
    def _setup_record_manager(self):
        """Setup record manager for change tracking"""
        record_manager = SQLRecordManager(
            namespace="postgres/confluence_parent_docs",
            db_url=CONNECTION_STRING
        )
        record_manager.create_schema()
        return record_manager
    
    def process_documents(self, directory_path: str, mode: str = "incremental"):
        """
        Process documents with automatic change detection
        
        Args:
            directory_path: Path to directory containing markdown files
            mode: Cleanup mode - "incremental", "full", or None
            
        Returns:
            Dictionary with processing statistics
        """
        
        # Load documents
        loader = DirectoryLoader(
            directory_path,
            glob="**/*.md",
            loader_cls=TextLoader,
            show_progress=True
        )
        raw_docs = loader.load()
        
        if not raw_docs:
            print("No documents found.")
            return {"processed": 0}
        
        print(f"📁 Loaded {len(raw_docs)} documents")
        
        # Enhanced metadata extraction (keep what works)
        processed_docs = []
        for doc in raw_docs:
            # Extract metadata from content
            doc_metadata = extract_metadata_from_content(doc.page_content)
            doc.metadata.update(doc_metadata)
            
            # Ensure source field for change tracking
            doc.metadata["source"] = doc.metadata.get("source", doc.metadata.get("file_path", "unknown"))
            processed_docs.append(doc)
        
        print(f"🔍 Processed metadata for {len(processed_docs)} documents")
        
        # Use parent document retriever for hierarchical storage
        self.retriever.add_documents(processed_docs)
        
        print(f"📚 Added entire documents to parent document retriever")
        
        # Get child documents for change tracking
        child_docs = self._get_child_documents(processed_docs)
        
        print(f"🧩 Generated {len(child_docs)} child chunks for precise search (parent = entire docs)")
        
        # Apply indexing API for change tracking
        result = index(
            child_docs,
            self.record_manager,
            self.vector_store,
            cleanup=mode,
            source_id_key="source"
        )
        
        print(f"✅ Processing complete: {result}")
        return result
    
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

class DocumentManager:
    """
    Document management API for the Smart Parent Document RAG system
    """
    
    def __init__(self, processor: SmartParentDocumentRAG):
        self.processor = processor
    
    def add_single_document(self, file_path: str):
        """Add or update a single document"""
        loader = TextLoader(file_path)
        doc = loader.load()[0]
        
        # Process metadata
        doc_metadata = extract_metadata_from_content(doc.page_content)
        doc.metadata.update(doc_metadata)
        doc.metadata["source"] = file_path
        
        # Add to parent document retriever
        self.processor.retriever.add_documents([doc])
        
        # Get child docs for change tracking
        child_docs = self.processor._get_child_documents([doc])
        
        # Update with change tracking
        result = index(
            child_docs,
            self.processor.record_manager,
            self.processor.vector_store,
            cleanup="incremental",
            source_id_key="source"
        )
        
        return result
    
    def sync_directory(self, directory_path: str, full_sync: bool = False):
        """Sync entire directory with change detection"""
        mode = "full" if full_sync else "incremental"
        return self.processor.process_documents(directory_path, mode=mode)
    
    def remove_document(self, source_path: str):
        """Remove document by source path"""
        # This requires implementing a custom cleanup
        # For now, use full sync without the document
        print(f"⚠️ Document removal not fully implemented for {source_path}")
        print("Recommendation: Run full sync after removing the file from source directory")
        pass
    
    def get_stats(self):
        """Get processing statistics"""
        # Count documents in docstore and vector store
        try:
            docstore_keys = list(self.processor.docstore.yield_keys())
            docstore_count = len(docstore_keys)
        except:
            docstore_count = "Unknown"
        
        return {
            "parent_documents": docstore_count,
            "last_update": "Not implemented",  # Could add timestamp tracking
            "vector_store_collection": COLLECTION_NAME,
            "record_manager_namespace": "confluence_parent_docs"
        }

def build_index():
    """Main function to build the parent document index"""
    print("🚀 Starting parent document indexing...")
    
    processor = SmartParentDocumentRAG()
    result = processor.process_documents(MARKDOWN_EXPORT_PATH, mode="full")
    
    print(f"✅ Parent document index built: {result}")
    return processor

def daily_sync():
    """Daily incremental sync script"""
    processor = SmartParentDocumentRAG()
    manager = DocumentManager(processor)
    
    result = manager.sync_directory(
        MARKDOWN_EXPORT_PATH,
        full_sync=False
    )
    
    print(f"📈 Daily sync complete:")
    print(f"  Added: {result.get('num_added', 0)}")
    print(f"  Updated: {result.get('num_updated', 0)}")
    print(f"  Skipped: {result.get('num_skipped', 0)}")
    print(f"  Deleted: {result.get('num_deleted', 0)}")

def weekly_full_sync():
    """Weekly full sync script"""
    processor = SmartParentDocumentRAG()
    manager = DocumentManager(processor)
    
    result = manager.sync_directory(
        MARKDOWN_EXPORT_PATH,
        full_sync=True
    )
    
    print(f"🔄 Weekly full sync complete: {result}")

if __name__ == "__main__":
    # Default to building index
    build_index()
