# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

confluence-markdown-exporter is a tool that exports Confluence pages to Markdown format. It supports exporting individual pages, pages with descendants, entire spaces, or all spaces from a Confluence instance. The project has recently been extended with a multi-tenant RAG (Retrieval-Augmented Generation) integration system.

## Development Commands

### Setup Environment

```bash
# Set up virtual environment (recommended)
./bin/venv.sh
source ./bin/activate-venv.sh

# Install development dependencies
pip install -e ".[dev]"

# Install VS Code extensions
./bin/setup.sh
```

### Running the Application

```bash
# Main commands
confluence-markdown-exporter pages <page-id-or-url> <output-path>
confluence-markdown-exporter pages-with-descendants <page-id-or-url> <output-path>
confluence-markdown-exporter spaces <space-key> <output-path>
confluence-markdown-exporter all-spaces <output-path>
confluence-markdown-exporter config

# Shorthand
cf-export pages <page-id-or-url> <output-path>
```

### Code Quality

```bash
# Run linter (Ruff)
ruff check .
ruff format .
```

## Architecture

### Core Exporter System
- **Entry Point**: `confluence_markdown_exporter/main.py` - Typer CLI application
- **API Client**: `confluence_markdown_exporter/api_clients.py` - Handles Confluence API interactions
- **Core Logic**: `confluence_markdown_exporter/confluence.py` - Page, Space, and Organization classes
- **Utilities**: `confluence_markdown_exporter/utils/` - Configuration, export logic, type conversion

### Multi-Tenant RAG Integration (Refactored)

The project now includes a simplified multi-tenant RAG system that:
1. Exports Confluence spaces to markdown files per customer
2. Indexes markdown files into vector databases (PostgreSQL + pgvector)
3. Provides retrieval capabilities for querying indexed knowledge

#### Architecture Components
- **Customer Management**: `confluence_rag_integration/customers/` - Customer config and state management
- **Export Orchestration**: `confluence_rag_integration/exporters/` - Space export workflow
- **RAG System**: `confluence_rag_integration/rag/` - Indexing and query functionality with multiple indexer types
- **Shared Models**: `confluence_rag_integration/shared/` - Data models and configuration adapter

#### Data Structure
```
data/
└── customers/
    └── <customer_id>/
        ├── config.yaml          # Customer configuration
        ├── state.json          # Export and index state tracking
        ├── exports/            # Exported Markdown files
        └── logs/               # Customer-specific logs
```

#### Key Features
- **Multiple Indexer Types**: Support for different indexing strategies via `IndexerFactory`
  - `SimpleIndexer`: Basic document indexing
  - `ParentDocumentIndexer`: Advanced chunking with parent-child relationships
- **Customer Isolation**: Each customer has separate data and vector store collections
- **State Management**: Tracks export and indexing status per customer
- **Query Caching**: Efficient retrieval with cached indexer instances

## Configuration System

The project uses a JSON-based configuration system stored in platform-specific app directories. Configuration can be managed through:
- Interactive CLI: `confluence-markdown-exporter config`
- Environment variable: `CME_CONFIG_PATH` for custom config location

Key configuration areas:
- `export.*` - Export behavior (paths, formatting, filenames)
- `auth.confluence.*` - Confluence authentication
- `connection_config.*` - HTTP connection settings






IN PROGRESS: 

### Refractoring NEEDED:

# Confluence RAG Integration - Context for Claude

## Project Overview
This is a multi-tenant RAG (Retrieval-Augmented Generation) system that:
1. Exports Confluence spaces to markdown files
2. Indexes the markdown files into a vector database (PostgreSQL + pgvector)
3. Provides retrieval capabilities for querying the indexed knowledge

## Current State
The codebase is overly complex with too many abstraction layers, defensive programming, and circular dependencies. We need to simplify it while maintaining the core functionality.

## Key Dependencies
- `confluence-markdown-exporter`: Original single-tenant CLI tool (DO NOT MODIFY)
- `langchain`: For RAG operations (ParentDocumentRetriever)
- `pgvector`: PostgreSQL vector database
- `pydantic`/`dataclasses`: For configuration models

## Core Concepts
1. **Customer**: A tenant with their own Confluence instance and isolated data
2. **Export**: Downloading Confluence pages as markdown files
3. **Index**: Building vector embeddings from markdown files
4. **Query**: Retrieving relevant documents based on questions

## Architecture Principles
- Keep it simple - no unnecessary abstractions
- Direct implementation over complex patterns
- Clear separation between batch operations (export/index) and services (query)
- No global state except for monkey-patching the original exporter

## Multi-Tenant RAG Integration Usage

### Simple API Functions
```python
# Export Confluence spaces for a customer
from confluence_rag_integration import export_customer
result = export_customer("acme_corp", space_keys=["PROD", "ENG"])

# Build/rebuild RAG index
from confluence_rag_integration import index_customer
result = index_customer("acme_corp", clear_existing=True)

# Query the indexed knowledge
from confluence_rag_integration import query_customer
result = query_customer("acme_corp", "How do I reset my password?")
```

### Customer Configuration (config.yaml)
```yaml
customer_id: acme_corp
customer_name: "ACME Corporation"

# Confluence credentials
confluence:
  url: https://acme.atlassian.net/
  username: admin@acme.com
  api_token: ${ACME_CONFLUENCE_TOKEN}  # Supports env vars

# Spaces to export
spaces:
  - key: PROD
    name: "Product Documentation"
    enabled: true
  - key: ENG
    name: "Engineering Wiki"
    enabled: true

# RAG settings (optional)
rag:
  indexer_type: "parent_document"  # or "simple"
  embedding_model: "gemini-embedding-001"
  chunk_size: 1000
  db_connection: "postgresql+psycopg://user:pass@localhost:5432/db"
```

### Refactored Architecture

#### Simplified Component Structure
```
confluence_rag_integration/
├── __init__.py              # Simple API entry points
├── customers/
│   └── customer_manager.py  # Config/state management only
├── exporters/
│   └── space_exporter.py    # Export orchestration
├── rag/
│   ├── base_indexer.py      # Abstract base class
│   ├── indexer_factory.py   # Creates indexers by type
│   ├── simple_indexer.py    # Basic indexing
│   ├── parent_document_indexer.py  # Advanced chunking
│   ├── index_manager.py     # Index workflow
│   └── query_manager.py     # Query service with caching
└── shared/
    ├── models.py            # CustomerConfig, CustomerState, Results
    ├── config_adapter.py    # Bridge to original exporter
    └── utils.py             # Shared utilities
```

#### Key Dependencies
- `confluence-markdown-exporter`: Original single-tenant CLI tool (DO NOT MODIFY)
- `langchain`: For RAG operations (ParentDocumentRetriever, embeddings)
- `pgvector`: PostgreSQL vector database extension
- `pydantic`/`dataclasses`: For configuration models

#### Architecture Principles (Refactored)
- **Direct Implementation**: No unnecessary abstractions or complex patterns
- **Clear Separation**: Export/Index are batch operations, Query is a service
- **Minimal Caching**: Only RAGIndexer instances cached in QueryManager
- **Simple State**: Just track last operations and status in state.json
- **Factory Pattern**: Support multiple indexer types without complexity
- **Customer Isolation**: Each customer has separate data and vector store collections

## Important Instruction Reminders
- Do what has been asked; nothing more, nothing less
- NEVER create files unless they're absolutely necessary
- ALWAYS prefer editing existing files over creating new ones
- NEVER proactively create documentation files unless explicitly requested
