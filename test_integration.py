#!/usr/bin/env python3
"""Integration test for the refactored Confluence RAG system."""

import os
import shutil
from pathlib import Path

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

# Import the simple API functions
from confluence_rag_integration import export_customer, index_customer, query_customer
from confluence_rag_integration.customers.customer_manager import CustomerManager


def test_integration_workflow():
    """Test the complete workflow: create customer, export, index, query."""
    
    print("🚀 Starting integration test...")
    
    # Clean up any existing test data
    cleanup_test_data()
    
    try:
        # Step 1: Create customer from config file
        print("\n📋 Step 1: Creating customer from config...")
        manager = CustomerManager()
        config_file = Path("test_sample_config.yaml")
        
        if not config_file.exists():
            print("❌ Config file not found. Please create test_sample_config.yaml")
            return False
        
        customer_config = manager.create_customer(config_file)
        print(f"✅ Created customer: {customer_config.customer_id}")
        
        # Step 2: Export spaces
        print("\n📥 Step 2: Exporting spaces...")
        export_result = export_customer(customer_config.customer_id)
        print(f"✅ Export completed: {export_result.status}, Pages: {export_result.pages_exported}")
        
        if export_result.errors:
            print(f"⚠️  Export warnings: {export_result.errors}")
        
        # Step 3: Build index (with clear_existing=True to clear any old data)
        print("\n🔍 Step 3: Building RAG index (clearing existing data first)...")
        index_result = index_customer(customer_config.customer_id, clear_existing=True)
        print(f"✅ Index built: {index_result.status}, Documents: {index_result.documents_indexed}")
        
        # Step 4: Test queries
        print("\n❓ Step 4: Testing queries...")
        test_questions = [
            "How do I change my account password?",
            "What are the IT access requirements?",
            "How do I register for two-step authentication?"
        ]
        
        for question in test_questions:
            print(f"\n🤔 Question: {question}")
            query_result = query_customer(customer_config.customer_id, question)
            
            if query_result.status == "success":
                print(f"✅ Found {len(query_result.documents)} relevant documents")
                for i, doc in enumerate(query_result.documents[:2]):  # Show first 2
                    title = doc['metadata'].get('title', 'Untitled')
                    preview = doc['content'][:500] + "..." if len(doc['content']) > 100 else doc['content']
                    print(f"   📄 {i+1}. {title}: {preview}")
            else:
                print(f"❌ Query failed: {query_result.error}")
        
        print("\n✅ Integration test completed successfully!")
        return True
        
    except Exception as e:
        print(f"\n❌ Integration test failed: {str(e)}")
        return False
    
    finally:
        # Step 5: Cleanup
        print("\n🧹 Step 5: Cleaning up test data...")
        #cleanup_test_data()
        print("✅ Cleanup completed")


def cleanup_test_data():
    """Clean up test data directories and vector database entries."""
    test_customer_id = "acme_corp"
    
    # Clear vector database before removing directory
    customer_dir = Path("data/customers") / test_customer_id
    if customer_dir.exists() and (customer_dir / "config.yaml").exists():
        try:
            manager = CustomerManager()
            from confluence_rag_integration.rag.indexer_factory import IndexerFactory
            config = manager.load_customer(test_customer_id)
            indexer = IndexerFactory.create_indexer(config)
            indexer.clear_index()
            print("🗑️  Cleared vector database entries")
        except Exception as e:
            print(f"📝 Note: Could not clear vector database: {str(e)}")
    
    # Remove customer data directory
    if customer_dir.exists():
        shutil.rmtree(customer_dir)
        print(f"🗑️  Removed customer directory: {customer_dir}")


if __name__ == "__main__":
    # Check if required environment variables are set
    if not os.getenv("CONFLUENCE_TOKEN"):
        print("⚠️  Warning: CONFLUENCE_TOKEN environment variable not set")
        print("   Set it with: export CONFLUENCE_TOKEN='your-token-here'")
    
    success = test_integration_workflow()
    exit(0 if success else 1)