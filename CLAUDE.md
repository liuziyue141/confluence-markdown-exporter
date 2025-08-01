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

### Multi-Tenant RAG Integration
- **Customer Management**: `confluence_rag_integration/customers/` - Multi-tenant customer configuration
- **Export Management**: `confluence_rag_integration/exporters/` - Space-level export orchestration
- **RAG System**: `confluence_rag_integration/rag/` - Customer-specific RAG managers and query interfaces
- **Shared Models**: `confluence_rag_integration/shared/` - Common data models and utilities

### Data Structure
```
data/
└── customers/
    └── <customer_name>/
        ├── config.yaml          # Customer configuration
        ├── state.json          # Export state tracking
        ├── exports/            # Exported Markdown files
        ├── vector_store/       # ChromaDB vector storage
        ├── cache/              # Export caching
        └── logs/               # Customer-specific logs
```

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
