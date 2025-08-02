# RAG Indexers

This module provides configurable indexing strategies for the Confluence RAG integration system.

## Available Indexers

### SimpleIndexer (Default)
- Uses markdown header splitting (splits on `##` headers)
- Direct vector store indexing
- Lightweight and fast
- Best for straightforward document retrieval

### ParentDocumentIndexer
- Uses LangChain's ParentDocumentRetriever
- Stores full documents while indexing smaller chunks
- Better context preservation for complex queries
- Higher storage requirements but better retrieval quality

## Configuration

In your customer configuration YAML file, specify the indexer type:

```yaml
# For simple indexing (default)
indexer_type: simple

# For parent document indexing
indexer_type: parent_document
```

## Architecture

```
BaseIndexer (Abstract)
├── SimpleIndexer
└── ParentDocumentIndexer

IndexerFactory
└── create_indexer(config) → BaseIndexer
```

## Usage

The indexer is automatically selected based on the customer configuration:

```python
from confluence_rag_integration.rag import IndexerFactory
from confluence_rag_integration.shared.models import CustomerConfig

# Load customer config
config = CustomerConfig(...)

# Factory creates the appropriate indexer
indexer = IndexerFactory.create_indexer(config)

# Build index
result = indexer.build_index(export_path)

# Get retriever for queries
retriever = indexer.get_retriever()
```

## When to Use Which Indexer

**Use SimpleIndexer when:**
- You need fast indexing and querying
- Documents have clear section headers
- Storage space is a concern
- Simple keyword/semantic search is sufficient

**Use ParentDocumentIndexer when:**
- You need better context in retrieved results
- Documents have complex relationships
- Query accuracy is more important than speed
- You want to retrieve full document context