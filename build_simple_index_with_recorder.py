import re
from dotenv import load_dotenv
from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain.text_splitter import MarkdownHeaderTextSplitter
from langchain_core.documents import Document
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_postgres import PGVector
from langchain.indexes import SQLRecordManager, index

# Load environment variables
load_dotenv()

# Configuration
MARKDOWN_EXPORT_PATH = "/Users/lindalee/confluence_exp"
EMBEDDING_MODEL = "gemini-embedding-001"
COLLECTION_NAME = "confluence_background_knowledge_structure_simple"
CONNECTION_STRING = "postgresql+psycopg://tim_itagent:Apple3344!@localhost:5432/confluence_exp"
RECORD_MANAGER_NAMESPACE = "postgres/confluence_simple"

def setup_embeddings():
    """Initialize embeddings model"""
    embeddings = GoogleGenerativeAIEmbeddings(model=EMBEDDING_MODEL)
    return embeddings

def setup_vector_store(embeddings):
    """Initialize vector store"""
    vector_store = PGVector(
        embeddings=embeddings,
        collection_name=COLLECTION_NAME,
        connection=CONNECTION_STRING,
    )
    return vector_store

def setup_record_manager():
    """Setup record manager for change tracking and duplicate detection"""
    record_manager = SQLRecordManager(
        namespace=RECORD_MANAGER_NAMESPACE,
        db_url=CONNECTION_STRING
    )
    record_manager.create_schema()
    return record_manager

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

def load_and_split_documents():
    """Load markdown documents and split them into chunks"""
    loader = DirectoryLoader(
        MARKDOWN_EXPORT_PATH,
        glob="**/*.md",
        loader_cls=TextLoader,
        show_progress=True,
    )
    docs = loader.load()
    
    if not docs:
        print("No markdown documents found. Please check the export path.")
        return []

    headers_to_split_on = [("##", "Header 2")]
    markdown_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=headers_to_split_on, strip_headers=False
    )

    all_enriched_chunks = []
    print("Extracting metadata and splitting documents...")
    
    for doc in docs:
        # Extract metadata from the full document content
        doc_metadata = extract_metadata_from_content(doc.page_content)

        # Split the document into text chunks
        chunks = markdown_splitter.split_text(doc.page_content)

        # Add the document-level metadata to each chunk
        for chunk in chunks:
            # Ensure chunk has metadata and page_content
            if hasattr(chunk, 'metadata'):
                chunk.metadata.update(doc_metadata)
            else:
                # If chunk is just text, convert to Document
                chunk = Document(
                    page_content=chunk if isinstance(chunk, str) else chunk.page_content,
                    metadata=doc_metadata.copy()
                )
            
            # Add source field for record manager tracking
            chunk.metadata["source"] = doc.metadata.get("source", doc.metadata.get("file_path", f"{MARKDOWN_EXPORT_PATH}/{doc_metadata['title']}.md"))
            
            all_enriched_chunks.append(chunk)

    print(f"Processed {len(docs)} documents into {len(all_enriched_chunks)} enriched chunks.")
    return all_enriched_chunks

def build_index():
    """Main function to build the chunk index with duplicate detection"""
    print("🚀 Starting document indexing process...")
    
    # Setup embeddings, vector store, and record manager
    embeddings = setup_embeddings()
    vector_store = setup_vector_store(embeddings)
    record_manager = setup_record_manager()
    
    # Load and process documents
    chunks = load_and_split_documents()
    if not chunks:
        return
    
    # Index documents with automatic duplicate detection
    print("📥 Adding documents to vector store with duplicate detection...")
    
    # Clear existing documents if you want a fresh index
    # Use cleanup="full" to remove all existing documents
    # Use cleanup="incremental" to only add new/updated documents
    # Use cleanup=None to add all documents regardless of duplicates
    
    result = index(
        chunks,
        record_manager,
        vector_store,
        cleanup="incremental",  # This will only add new/changed documents
        source_id_key="source"
    )
    
    print(f"✅ Indexing complete:")
    print(f"  Added: {result.get('num_added', 0)}")
    print(f"  Updated: {result.get('num_updated', 0)}")
    print(f"  Skipped: {result.get('num_skipped', 0)}")
    print(f"  Deleted: {result.get('num_deleted', 0)}")
    
    return vector_store, record_manager

def clear_index():
    """Clear the existing index (useful for fresh starts)"""
    print("🗑️  Clearing existing index...")
    
    embeddings = setup_embeddings()
    vector_store = setup_vector_store(embeddings)
    record_manager = setup_record_manager()
    
    # Delete all documents
    result = index(
        [],  # Empty list
        record_manager,
        vector_store,
        cleanup="full",  # Remove all existing documents
        source_id_key="source"
    )
    
    print(f"✅ Index cleared:")
    print(f"  Deleted: {result.get('num_deleted', 0)}")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--clear":
        clear_index()
    else:
        build_index()