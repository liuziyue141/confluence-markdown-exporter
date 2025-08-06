#!/bin/bash

# Script to run the Confluence RAG MCP server
# This script activates the virtual environment and launches the MCP server

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Activate virtual environment if it exists
if [ -f "$PROJECT_ROOT/venv/bin/activate" ]; then
    echo "Activating virtual environment..."
    source "$PROJECT_ROOT/venv/bin/activate"
elif [ -f "$PROJECT_ROOT/.venv/bin/activate" ]; then
    echo "Activating virtual environment..."
    source "$PROJECT_ROOT/.venv/bin/activate"
fi

# Change to project root
cd "$PROJECT_ROOT"

# Export environment variables (if .env file exists)
if [ -f ".env" ]; then
    echo "Loading environment variables from .env..."
    export $(grep -v '^#' .env | xargs)
fi

# Ensure required environment variables are set
if [ -z "$GOOGLE_API_KEY" ]; then
    echo "Warning: GOOGLE_API_KEY is not set. RAG queries may fail."
fi

if [ -z "$DB_CONNECTION" ]; then
    echo "Warning: DB_CONNECTION is not set. Using default PostgreSQL connection."
fi

# Run the MCP server
echo "Starting Confluence RAG MCP server..."
echo "Server will be available for Claude Desktop to connect to."
echo "Press Ctrl+C to stop the server."
echo ""

python -m confluence_rag_integration.mcp_server