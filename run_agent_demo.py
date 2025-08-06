#!/usr/bin/env python
"""Run the Confluence RAG Agent demo."""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

def main():
    """Main entry point."""
    # Check if environment is set up
    try:
        from confluence_rag_integration.api.app import app
        import uvicorn
    except ImportError as e:
        print(f"Error: Missing dependencies. Please install requirements: {e}")
        print("\nRun: pip install -r requirements-integration.txt")
        return 1
    
    # Check for API keys
    if not os.getenv("GOOGLE_API_KEY"):
        print("Warning: GOOGLE_API_KEY not set. The agent may not work properly.")
        print("Set it with: export GOOGLE_API_KEY='your-api-key'")
    
    # Check if customer data exists
    data_dir = Path("data/customers/acme_corp")
    if not data_dir.exists():
        print("\nNote: No customer data found at data/customers/acme_corp")
        print("You may need to:")
        print("1. Set up a customer configuration")
        print("2. Export Confluence spaces")
        print("3. Build the RAG index")
        print("\nExample:")
        print("  from confluence_rag_integration import export_customer, index_customer")
        print("  export_customer('acme_corp', space_keys=['PROD'])")
        print("  index_customer('acme_corp', clear_existing=True)")
    
    print("\n" + "="*50)
    print("Starting Confluence RAG Agent Demo")
    print("="*50)
    print("\nAccess the chat interface at: http://localhost:8000")
    print("API documentation at: http://localhost:8000/docs")
    print("\nPress Ctrl+C to stop the server")
    print("="*50 + "\n")
    
    # Run the FastAPI app
    uvicorn.run(
        "confluence_rag_integration.api.app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )

if __name__ == "__main__":
    sys.exit(main())