"""MCP Server for Confluence RAG Integration.

This MCP server exposes the retrieve_knowledge functionality as a tool that can be used
by Claude Desktop and other MCP-compatible LLM applications.
"""

import logging
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

from mcp.server.fastmcp import FastMCP
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions
import mcp.server.stdio
import mcp.types as types

from .customers.customer_manager import CustomerManager
from .rag.query_manager import QueryManager
from .mcp_models import (
    RetrieveKnowledgeInput,
    RetrieveKnowledgeOutput,
    DocumentResult
)

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize MCP server
mcp = FastMCP("Confluence RAG")

# Initialize managers (will be instantiated once)
customer_manager: Optional[CustomerManager] = None
query_manager: Optional[QueryManager] = None


def initialize_managers():
    """Initialize the customer and query managers."""
    global customer_manager, query_manager
    if customer_manager is None:
        customer_manager = CustomerManager()
        query_manager = QueryManager(customer_manager)
        logger.info("Initialized CustomerManager and QueryManager")


@mcp.tool()
def retrieve_knowledge(
    query: str,
    customer_id: str = "acme_corp",
    top_k: int = 3
) -> RetrieveKnowledgeOutput:
    """
    Search and retrieve relevant documentation from Confluence knowledge base.
    
    Use this when you need to find information about products, procedures,
    troubleshooting steps, or any documented knowledge to help answer questions.
    
    Args:
        query: The search query or question to find relevant documents
        customer_id: Customer ID for multi-tenant support (default: acme_corp)
        top_k: Number of documents to retrieve (default: 3)
    
    Returns:
        RetrieveKnowledgeOutput with retrieved documents and status
    """
    # Ensure managers are initialized
    initialize_managers()
    
    try:
        logger.info(f"Retrieving knowledge for customer '{customer_id}' with query: {query}")
        
        # Execute query using the QueryManager
        result = query_manager.query(customer_id, query, top_k)
        
        # Convert to MCP output format
        documents = []
        for doc in result.documents:
            documents.append(DocumentResult(
                content=doc.get("content", ""),
                source=doc.get("source", "unknown"),
                metadata=doc.get("metadata", {})
            ))
        
        output = RetrieveKnowledgeOutput(
            documents=documents,
            status=result.status,
            error=result.error,
            customer_id=customer_id,
            query=query
        )
        
        logger.info(f"Retrieved {len(documents)} documents with status: {result.status}")
        return output
        
    except Exception as e:
        logger.error(f"Error retrieving knowledge: {str(e)}", exc_info=True)
        return RetrieveKnowledgeOutput(
            documents=[],
            status="error",
            error=str(e),
            customer_id=customer_id,
            query=query
        )


@mcp.tool()
def list_customers() -> dict:
    """
    List all available customers in the system.
    
    Returns:
        Dictionary with list of customers and their names
    """
    initialize_managers()
    
    try:
        customers = customer_manager.list_customers()
        return {
            "status": "success",
            "customers": customers
        }
    except Exception as e:
        logger.error(f"Error listing customers: {str(e)}", exc_info=True)
        return {
            "status": "error",
            "error": str(e),
            "customers": []
        }


@mcp.tool()
def get_customer_status(customer_id: str = "acme_corp") -> dict:
    """
    Get the current status of a customer's RAG system.
    
    Args:
        customer_id: Customer ID to check status for
    
    Returns:
        Dictionary with customer status information
    """
    initialize_managers()
    
    try:
        state = customer_manager.get_state(customer_id)
        config = customer_manager.load_customer(customer_id)
        
        return {
            "status": "success",
            "customer_id": customer_id,
            "customer_name": config.customer_name,
            "rag_status": state.rag_status,
            "is_ready_for_queries": state.is_ready_for_queries,
            "last_export": state.last_export,
            "last_index": state.last_index
        }
    except Exception as e:
        logger.error(f"Error getting customer status: {str(e)}", exc_info=True)
        return {
            "status": "error",
            "error": str(e),
            "customer_id": customer_id
        }


def main():
    """Run the MCP server."""
    import asyncio
    
    async def run():
        """Async runner for the MCP server."""
        # Use stdio transport for Claude Desktop integration
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            logger.info("Starting Confluence RAG MCP server...")
            
            # Initialize the server with proper options
            initialization_options = InitializationOptions(
                server_name="confluence-rag",
                server_version="1.0.0"
            )
            
            await mcp.run(
                read_stream,
                write_stream,
                initialization_options,
                raise_exceptions=False
            )
    
    # Run the async server
    asyncio.run(run())


if __name__ == "__main__":
    main()