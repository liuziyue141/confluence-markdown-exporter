# Confluence RAG MCP Server Setup Guide

## Overview

The Confluence RAG MCP (Model Context Protocol) server exposes the knowledge retrieval functionality from your Confluence knowledge bases as tools that can be used by Claude Desktop and other MCP-compatible applications.

## Features

The MCP server provides three main tools:

1. **retrieve_knowledge**: Search and retrieve relevant documentation from Confluence knowledge base
2. **list_customers**: List all available customers in the system
3. **get_customer_status**: Get the current status of a customer's RAG system

## Prerequisites

1. Python 3.10 or higher
2. Confluence RAG system already set up with indexed knowledge bases
3. Required environment variables:
   - `GOOGLE_API_KEY`: For embeddings and LLM operations
   - `DB_CONNECTION`: PostgreSQL connection string (optional, uses default if not set)
   - Customer-specific Confluence tokens (e.g., `ACME_CONFLUENCE_TOKEN`)

## Installation

1. Install the MCP dependencies (already done if you followed the main setup):
   ```bash
   pip install -e ".[dev]"
   ```

2. Verify the installation:
   ```bash
   python test_mcp_server.py
   ```

## Running the MCP Server

### Method 1: Using the Launch Script

```bash
./bin/run_mcp_server.sh
```

### Method 2: Direct Python Command

```bash
python -m confluence_rag_integration.mcp_server
```

### Method 3: Using MCP Dev Tools

```bash
mcp dev confluence_rag_integration/mcp_server.py
```

## Integrating with Claude Desktop

### Option 1: Manual Configuration

1. Locate your Claude Desktop configuration file:
   - macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - Windows: `%APPDATA%\Claude\claude_desktop_config.json`
   - Linux: `~/.config/Claude/claude_desktop_config.json`

2. Add the Confluence RAG server configuration:

```json
{
  "mcpServers": {
    "confluence-rag": {
      "command": "python",
      "args": [
        "-m",
        "confluence_rag_integration.mcp_server"
      ],
      "env": {
        "PYTHONPATH": "/Users/lindalee/Desktop/confluence-markdown-exporter",
        "GOOGLE_API_KEY": "your-google-api-key",
        "ACME_CONFLUENCE_TOKEN": "your-confluence-token",
        "DB_CONNECTION": "postgresql+psycopg://user:pass@localhost:5432/db"
      },
      "cwd": "/Users/lindalee/Desktop/confluence-markdown-exporter"
    }
  }
}
```

3. Restart Claude Desktop

### Option 2: Using the Provided Config

Copy the provided `mcp_config.json` to your Claude Desktop configuration and merge it with existing servers:

```bash
# Backup existing config
cp ~/Library/Application\ Support/Claude/claude_desktop_config.json ~/Library/Application\ Support/Claude/claude_desktop_config.backup.json

# Manually merge the configurations or use a JSON merge tool
```

## Usage Examples

Once integrated with Claude Desktop, you can use natural language to query your Confluence knowledge bases:

### Example Queries in Claude

1. **Search for information:**
   ```
   "Search the knowledge base for password reset procedures"
   ```

2. **Get specific documentation:**
   ```
   "Find documentation about Active Directory account management"
   ```

3. **Check system status:**
   ```
   "What customers are available in the RAG system?"
   "Is the acme_corp knowledge base ready for queries?"
   ```

### Programmatic Usage

You can also use the MCP server programmatically:

```python
from confluence_rag_integration.mcp_server import retrieve_knowledge

# Search for knowledge
result = retrieve_knowledge(
    query="How do I configure VPN access?",
    customer_id="acme_corp",
    top_k=5
)

# Process results
for doc in result.documents:
    print(f"Source: {doc.source}")
    print(f"Content: {doc.content[:200]}...")
    print("---")
```

## Environment Variables

Set these in your `.env` file or system environment:

```bash
# Required for embeddings and LLM
GOOGLE_API_KEY=your-google-api-key

# Database connection (optional, uses default if not set)
DB_CONNECTION=postgresql+psycopg://user:password@localhost:5432/ragdb

# Customer-specific Confluence tokens
ACME_CONFLUENCE_TOKEN=your-confluence-api-token
```

## Troubleshooting

### Server Won't Start

1. Check that all dependencies are installed:
   ```bash
   pip install -e ".[dev]"
   ```

2. Verify environment variables are set:
   ```bash
   echo $GOOGLE_API_KEY
   echo $DB_CONNECTION
   ```

3. Check that the PostgreSQL database is running:
   ```bash
   psql -h localhost -U user -d ragdb -c "SELECT 1;"
   ```

### No Results from Queries

1. Verify customer data is indexed:
   ```python
   python test_mcp_server.py
   ```

2. Check customer status to ensure RAG is ready:
   - Look for `"rag_status": "ready"`
   - Verify `"is_ready_for_queries": true`

3. Ensure the customer has been exported and indexed:
   ```python
   from confluence_rag_integration import export_customer, index_customer
   
   # Re-export and index if needed
   export_customer("acme_corp")
   index_customer("acme_corp")
   ```

### Claude Desktop Can't Connect

1. Verify the server is running:
   ```bash
   ./bin/run_mcp_server.sh
   ```

2. Check Claude Desktop logs for connection errors

3. Ensure the path in Claude Desktop config is absolute and correct

4. Try running with verbose logging:
   ```bash
   export MCP_LOG_LEVEL=DEBUG
   python -m confluence_rag_integration.mcp_server
   ```

## Advanced Configuration

### Custom Customer Configuration

Each customer can have different settings in their `config.yaml`:

```yaml
customer_id: acme_corp
customer_name: "ACME Corporation"

# RAG settings
rag:
  indexer_type: "parent_document"  # or "simple"
  embedding_model: "gemini-embedding-001"
  chunk_size: 1000
  db_connection: "postgresql+psycopg://user:pass@localhost:5432/db"
```

### Multiple Customers

The MCP server supports multiple customers. Use the `customer_id` parameter to specify which knowledge base to query:

```python
# Query different customers
result1 = retrieve_knowledge("policy question", customer_id="acme_corp")
result2 = retrieve_knowledge("policy question", customer_id="beta_inc")
```

## Security Considerations

1. **API Keys**: Never commit API keys to version control. Use environment variables or secure secret management.

2. **Database Credentials**: Store database connection strings securely.

3. **Customer Isolation**: Each customer's data is isolated in separate vector store collections.

4. **Access Control**: The MCP server currently doesn't implement authentication. Add authentication if exposing to untrusted environments.

## Next Steps

1. Set up additional customers by creating their config files
2. Schedule regular exports and re-indexing to keep knowledge bases current
3. Monitor query performance and adjust indexing parameters as needed
4. Consider implementing caching for frequently accessed queries