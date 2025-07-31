#!/usr/bin/env python3
"""
Demonstration of Multi-Tenant RAG Integration System

This script demonstrates the complete multi-tenant RAG integration workflow
including customer creation, export + indexing, and querying with complete
data isolation between customers.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

from confluence_rag_integration.rag import create_rag_interface, MultiTenantRAGInterface
from confluence_rag_integration.shared.models import RAGStatus

# Load environment variables
load_dotenv()

def main():
    """Main demonstration workflow."""
    print("🚀 Multi-Tenant RAG Integration System Demo")
    print("=" * 60)
    
    # Initialize the RAG interface
    print("\n📋 1. Initializing Multi-Tenant RAG Interface...")
    rag_interface = create_rag_interface()
    
    # Get customer manager
    customer_manager = rag_interface.get_customer_manager()
    
    print(f"   ✅ Interface initialized")
    print(f"   📁 Data path: {customer_manager.base_data_path}")
    
    # List existing customers
    print("\n👥 2. Checking Existing Customers...")
    existing_customers = customer_manager.list_customers()
    
    if existing_customers:
        print(f"   Found {len(existing_customers)} existing customers:")
        for customer_id in existing_customers:
            try:
                state = customer_manager.get_customer_state(customer_id)
                print(f"   📋 {customer_id}: RAG Status = {state.rag_status.value}")
            except Exception as e:
                print(f"   ⚠️  {customer_id}: Error loading state - {e}")
    else:
        print("   No existing customers found")
    
    # Create a demo customer if none exist
    if not existing_customers:
        print("\n🏗️  3. Creating Demo Customer...")
        demo_customer_config = create_demo_customer(customer_manager)
        print(f"   ✅ Created customer: {demo_customer_config.customer_id}")
        existing_customers = [demo_customer_config.customer_id]
    
    # Select first customer for demo
    demo_customer = existing_customers[0]
    print(f"\n🎯 4. Using Customer: {demo_customer}")
    
    # Validate customer RAG configuration
    print("\n🔍 5. Validating Customer RAG Configuration...")
    validation_result = rag_interface.validate_customer_rag(demo_customer)
    
    if validation_result["valid"]:
        print("   ✅ RAG configuration is valid")
        print(f"   📦 Collection: {validation_result['collection_name']}")
        print(f"   🔗 Vector store: {validation_result['vector_store_path_exists']}")
        print(f"   🧠 Model: {validation_result['embedding_model']}")
    else:
        print("   ⚠️  RAG configuration has issues:")
        if "error" in validation_result:
            print(f"      Error: {validation_result['error']}")
    
    # Get current RAG statistics
    print("\n📊 6. Current RAG Statistics...")
    stats = rag_interface.get_customer_rag_stats(demo_customer)
    
    print(f"   📋 Customer: {stats['customer_id']}")
    print(f"   🎯 Status: {stats.get('rag_status', 'unknown')}")
    print(f"   📚 Documents: {stats.get('total_indexed_documents', 0)}")
    print(f"   🧩 Chunks: {stats.get('total_indexed_chunks', 0)}")
    print(f"   ⏰ Last Index: {stats.get('last_index_time', 'Never')}")
    print(f"   🚦 Ready for Queries: {stats.get('is_ready_for_queries', False)}")
    
    # Check if we have exported data
    customer_config = customer_manager.load_customer(demo_customer)
    export_path = customer_config.export.output_path
    result = rag_interface.export_and_index(demo_customer, space_keys=["DEMO"])
        
        # Test queries
    print("\n🤔 9. Testing RAG Queries...")
    test_questions = [
        "How do I reset my password?",
        "What is two-factor authentication?",
        "How do I access my account?",
    ]
    
    for i, question in enumerate(test_questions, 1):
        print(f"\n   Question {i}: {question}")
        try:
            query_result = rag_interface.query_customer(demo_customer, question, top_k=2)
            
            print(f"   📝 Answer Preview: {query_result.answer[:150]}...")
            print(f"   📚 Sources Found: {len(query_result.sources)}")
            print(f"   ⏱️  Response Time: {query_result.response_time_ms:.1f}ms")
            
            for j, source in enumerate(query_result.sources[:2], 1):
                print(f"      📄 Source {j}: {source.title}")
                print(f"         📂 Path: {source.breadcrumb}")
            
        except Exception as e:
            print(f"   ❌ Query failed: {e}")
    
    # Show final statistics for all customers
    print("\n📈 10. Final Multi-Tenant RAG Statistics...")
    all_stats = rag_interface.get_all_customer_stats()
    
    for customer_id, customer_stats in all_stats.items():
        print(f"\n   👤 {customer_id}:")
        if "error" in customer_stats:
            print(f"      ❌ Error: {customer_stats['error']}")
        else:
            print(f"      🎯 Status: {customer_stats.get('rag_status', 'unknown')}")
            print(f"      📚 Documents: {customer_stats.get('total_indexed_documents', 0)}")
            print(f"      🧩 Chunks: {customer_stats.get('total_indexed_chunks', 0)}")
            print(f"      🚦 Ready: {customer_stats.get('is_ready_for_queries', False)}")
    
    print("\n🎉 Multi-Tenant RAG Integration Demo Complete!")
    print("=" * 60)


def create_demo_customer(customer_manager):
    """Create a demo customer configuration for testing."""
    
    # Try to get Confluence credentials from environment
    confluence_url = os.getenv('CONFLUENCE_URL')
    username = os.getenv('CONFLUENCE_USERNAME')
    api_token = os.getenv('CONFLUENCE_API_TOKEN')
    
    if not all([confluence_url, username, api_token]):
        print("\n⚠️  Missing Confluence credentials!")
        print("Please set the following environment variables:")
        print("  - CONFLUENCE_URL")
        print("  - CONFLUENCE_USERNAME")
        print("  - CONFLUENCE_API_TOKEN")
        print("\nSee .env.example for more details.")
        raise ValueError("Missing required Confluence credentials")
    
    print(f"   Creating customer with URL: {confluence_url}")
    
    return customer_manager.create_customer(
        customer_id="demo_customer",
        name="Demo Customer",
        confluence_url=confluence_url,
        username=username,
        api_token=api_token,
        spaces=[
            {"key": "DEMO", "name": "Demo service project", "enabled": True},
        ]
    )


if __name__ == "__main__":
    main() 