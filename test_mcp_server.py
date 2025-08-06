#!/usr/bin/env python
"""Test script for the Confluence RAG MCP server."""

import asyncio
import json
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

async def test_mcp_tools():
    """Test the MCP server tools directly."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    
    from confluence_rag_integration.mcp_server import (
        retrieve_knowledge,
        list_customers,
        get_customer_status
    )
    
    print("Testing MCP Server Tools")
    print("=" * 50)
    
    # Test 1: List customers
    print("\n1. Testing list_customers():")
    result = list_customers()
    print(json.dumps(result, indent=2))
    
    # Test 2: Get customer status
    print("\n2. Testing get_customer_status():")
    result = get_customer_status("acme_corp")
    print(json.dumps(result, indent=2, default=str))
    
    # Test 3: Retrieve knowledge
    print("\n3. Testing retrieve_knowledge():")
    result = retrieve_knowledge(
        query="How do I reset my password?",
        customer_id="acme_corp",
        top_k=2
    )
    
    # Convert Pydantic model to dict for printing
    result_dict = {
        "status": result.status,
        "customer_id": result.customer_id,
        "query": result.query,
        "error": result.error,
        "documents": [
            {
                "source": doc.source,
                "content": doc.content[:200] + "..." if len(doc.content) > 200 else doc.content,
                "metadata": doc.metadata
            }
            for doc in result.documents
        ]
    }
    print(json.dumps(result_dict, indent=2))
    
    print("\n" + "=" * 50)
    print("MCP Server Tools Test Complete!")


if __name__ == "__main__":
    asyncio.run(test_mcp_tools())