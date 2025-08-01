# Overall Architecture Refactoring

## Goal
Simplify the multi-tenant Confluence RAG integration by removing unnecessary abstractions and reducing code complexity by ~50%.

Feel Free to created some essential helper function to improve the code's readability. However, do not abuse the function to make entire codename unnecessarily abstract. 


config.yaml (Static Configuration)
    ↓
CustomerManager.create_customer()
    ↓
CustomerConfig object + state.json (empty state)
    ↓
┌─────────────────────────────────────┐
│         EXPORT WORKFLOW             │
├─────────────────────────────────────┤
│ SpaceExporter.export_spaces()       │
│   ↓                                 │
│ ConfigAdapter.to_original_config()    │
│   ↓                                 │
│ Set global Setting & Confluence      │
│   ↓                                 │
│ Export pages                        │
│   ↓                                 │
│ CustomerManager.update_export_state()│
│   ↓                                 │
│ state.json updated                  │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│         INDEX WORKFLOW              │
├─────────────────────────────────────┤
│ QueryManager.build_index()          │
│   ↓                                 │
│ RAGIndexer.build_index()            │
│   ↓                                 │
│ ParentDocumentRetriever.add_docs()  │
│   ↓                                 │
│ CustomerManager.update_index_state() │
│   ↓                                 │
│ state.json updated                  │
└─────────────────────────────────────┘

Query Workflow
┌─────────────────────────────────────┐
│         QUERY WORKFLOW              │
├─────────────────────────────────────┤
│ QueryManager.query()                │
│   ↓                                 │
│ Check state.is_ready_for_queries    │
│   ↓                                 │
│ Get cached RAGIndexer               │
│   ↓                                 │
│ Use indexer.retriever.get_docs()    │
└─────────────────────────────────────┘

## Core Components (Keep These)

### 1. Data Models (`shared/models.py`)
- `CustomerConfig`: Configuration from config.yaml
- `CustomerState`: Runtime state in state.json
- `ExportResult`, `IndexResult`, `QueryResult`: Operation results

### 2. Customer Management (`customers/customer_manager.py`)
- `CustomerManager`: Single source of truth for config and state
- Handles config.yaml and state.json files
- No caching, no complex logic

### 3. Export Pipeline (`exporters/space_exporter.py`)
- `SpaceExporter`: Batch operation for exporting Confluence spaces
- Uses `ConfigAdapter` to bridge to original exporter

### 4. Index Pipeline (`rag/index_manager.py`, `rag/rag_indexer.py`)
- `IndexManager`: Orchestrates indexing operation
- `RAGIndexer`: Handles ParentDocumentRetriever setup

### 5. Query Service (`rag/query_manager.py`)
- `QueryManager`: Service for document retrieval
- Caches `RAGIndexer` instances for performance

### 6. Configuration Bridge (`shared/config_adapter.py`)
- `ConfigAdapter`: Converts our simple config to original format

## Components to Remove

DELETE these files/folders:
- `exporters/export_manager.py`
- `rag/customer_rag_manager.py`
- `rag/rag_interface.py`
- `integration/` folder
- `customers/customer_config.py` (merge into models.py)
- Any factory classes or abstract base classes

## Directory Structure After Refactoring
confluence_rag_integration/
├── shared/
│   ├── models.py          # All dataclasses
│   └── config_adapter.py  # ConfigAdapter
├── customers/
│   └── customer_manager.py # CustomerManager
├── exporters/
│   └── space_exporter.py  # SpaceExporter
├── rag/
│   ├── rag_indexer.py     # RAGIndexer
│   ├── index_manager.py   # IndexManager (new)
│   └── query_manager.py   # QueryManager
└── __init__.py           # Simple API functions
step 1: 
New Shared Model (Cleaned):

```
# shared/models.py
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from datetime import datetime
from pathlib import Path

@dataclass
class CustomerConfig:
    """Customer configuration from config.yaml"""
    customer_id: str
    customer_name: str
    confluence_url: str
    confluence_username: str
    confluence_api_token: str
    space_keys: List[str]
    # RAG settings
    embedding_model: str = "gemini-embedding-001"
    chunk_size: int = 1000
    collection_name: str = None  # Auto-generated if None
    db_connection: str = "postgresql+psycopg://user:pass@localhost:5432/db"
    
    def __post_init__(self):
        if not self.collection_name:
            self.collection_name = f"customer_{self.customer_id}"

@dataclass
class CustomerState:
    """Runtime state from state.json"""
    customer_id: str
    last_export: Optional[Dict[str, Any]] = None  # {timestamp, status, pages_exported, errors}
    last_index: Optional[Dict[str, Any]] = None   # {timestamp, status, documents_indexed, chunks_created}
    rag_status: str = "never_built"  # never_built, building, ready, failed
    
    @property
    def is_ready_for_queries(self) -> bool:
        return self.rag_status == "ready" and self.last_index is not None

@dataclass
class ExportResult:
    """Result from export operation"""
    status: str  # success, partial, failed
    pages_exported: int
    errors: List[str]
    timestamp: str  # ISO format
    duration_seconds: float

@dataclass
class IndexResult:
    """Result from index operation"""
    status: str  # success, no_documents, failed
    documents_indexed: int
    chunks_created: int
    timestamp: str  # ISO format
    duration_seconds: float

@dataclass
class QueryResult:
    """Result from query operation"""
    customer_id: str
    question: str
    documents: List[Dict[str, Any]]  # [{content, metadata, source}, ...]
    status: str  # success, error
    error: Optional[str] = None
```

Simplify ConsumerManager: 

3. Refactor CustomerManager (customers/customer_manager.py)

Remove all RAG-specific methods
Keep only:

create_customer(config_file: Path) -> CustomerConfig
load_customer(customer_id: str) -> CustomerConfig
get_state(customer_id: str) -> CustomerState
update_export_state(customer_id: str, result: Dict)
update_index_state(customer_id: str, result: Dict)

difference between create_customer and load_customer is 
create_customer will config_file path and save it into base_path/customer_id
load_customer will load config_file directly from base_path/customer_id


Remove caching - load from disk each time

Simplify SpaceExporter (exporters/space_exporter.py):
class SpaceExporter:
    def __init__(self, customer_manager: CustomerManager):
        self.customer_manager = customer_manager
    
    def export_spaces(self, customer_id: str, space_keys: Optional[List[str]] = None) -> Export_Result:
        # 1. Load config via customer_manager
        # 2. Use ConfigAdapter to create client and original config
        # 3. Monkey-patch globals directly (no thread-local needed)
        # 4. Export spaces
        # 5. Update state via customer_manager

Create Clean Indexer:
class RAGIndexer:
    def __init__(self, customer_config: CustomerConfig):
        # Initialize embeddings, vector store, retriever
        
    def build_index(self, export_path: Path) -> IndexResult:
        # Load documents and index using ParentDocumentRetriever
        
    @property
    def retriever(self) -> ParentDocumentRetriever:
        # Expose retriever for QueryManager to use

Refractor QueryManager:
```
class QueryManager:
    def __init__(self, customer_manager: CustomerManager):
        self.customer_manager = customer_manager
        self._indexers = {}  # Cache RAGIndexer instances
        
    def query(self, customer_id: str, question: str, top_k: int = 3) -> QueryResult:
        # 1. Check state.is_ready_for_queries
        # 2. Get or create RAGIndexer from cache
        # 3. Use indexer.retriever.get_relevant_documents()
        # 4. Return documents (no LLM)
```

Remove Unnecessary Files
Delete these files/classes:

exporters/export_manager.py - Functionality moved to SpaceExporter
rag/customer_rag_manager.py - Replaced by simpler RAGIndexer
rag/rag_interface.py - Over-abstraction, not needed
integration/ folder - Not needed
CustomerQueryManager - Merged into QueryManager
RAGFactory - Not needed, QueryManager handles caching

Simplify Entry Points
Create simple functions in __init__.py:
pythondef export_customer(customer_id: str, space_keys: Optional[List[str]] = None):
    manager = CustomerManager()
    exporter = SpaceExporter(manager)
    return exporter.export_spaces(customer_id, space_keys)

def index_customer(customer_id: str):
    manager = CustomerManager()
    query_mgr = QueryManager(manager)
    return query_mgr.build_index(customer_id)

def query_customer(customer_id: str, question: str):
    manager = CustomerManager()
    query_mgr = QueryManager(manager)
    return query_mgr.query(customer_id, question)

Key Principles to Follow

No complex Global Registry - Direct monkey-patching is fine for batch operations
Minimal Caching - Only cache RAGIndexer in QueryManager, nothing else
Clear Separation - Export/Index are batch operations, Query is a service
No LLM in Core - QueryManager returns documents, LLM integration is external
Simple State - Just track last operations and status in state.json
Direct Implementation - Avoid abstract base classes and factories

Testing: 

Only Workflow test is needed. Created a sample config.yaml. Export the spaces. Index the spaces. Query the spaces with some IT Access & Account related questions. Clean the recorder. Clean the vector database. 

example config.yaml:

# data/customers/{customer_id}/config.yaml
customer_id: acme_corp
customer_name: "ACME Corporation"

# Confluence credentials
confluence:
  url: https://acme.atlassian.net/
  username: admin@acme.com
  api_token: ${ACME_CONFLUENCE_TOKEN}  # Can use env vars for security

# Spaces to export
spaces:
  - key: PROD
    name: "Product Documentation"
    enabled: true
  - key: ENG
    name: "Engineering Wiki"
    enabled: true
  - key: ARCHIVE
    name: "Archived Content"
    enabled: false

# Optional overrides (if not specified, uses defaults)
export:
  include_breadcrumbs: true
  download_external_images: true

rag:
  embedding_model: "gemini-embedding-001"
  chunk_size: 1000
