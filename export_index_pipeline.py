#!/usr/bin/env python3
"""Export and Index Pipeline for Confluence RAG Integration.

This script provides a complete workflow to:
1. Load/create customer configuration
2. Export Confluence spaces to markdown
3. Build vector index from exported content
4. Test queries to verify everything works
"""

import os
import sys
import argparse
from pathlib import Path
from typing import Optional, List
from datetime import datetime

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

# Import the simple API functions
from confluence_rag_integration import export_customer, index_customer, query_customer
from confluence_rag_integration.customers.customer_manager import CustomerManager


def run_export_index_pipeline(
    customer_id: str,
    clear_existing: bool = False,
    space_keys: Optional[List[str]] = None,
    test_queries: Optional[List[str]] = None,
    skip_export: bool = False,
    skip_index: bool = False,
    verbose: bool = True
):
    """Run the complete export and index pipeline for a customer.
    
    Args:
        customer_id: The customer identifier
        clear_existing: Whether to clear existing index before building (default: False)
        space_keys: Optional list of specific space keys to export (None = all configured)
        test_queries: Optional list of test queries to run after indexing
        skip_export: Skip the export step if data already exists
        skip_index: Skip the indexing step if index already exists
        verbose: Print detailed progress information
    
    Returns:
        dict: Results of the pipeline execution
    """
    results = {
        "customer_id": customer_id,
        "export": None,
        "index": None,
        "queries": [],
        "success": False
    }
    
    def log(message: str):
        if verbose:
            print(message)
    
    log(f"\n🚀 Starting Export and Index Pipeline for '{customer_id}'")
    log("=" * 60)
    
    try:
        # Step 1: Verify customer exists
        log(f"\n📋 Step 1: Verifying customer configuration...")
        manager = CustomerManager()
        
        try:
            customer_config = manager.load_customer(customer_id)
            log(f"✅ Found customer: {customer_config.customer_name}")
            
            # Show configured spaces
            if hasattr(customer_config, 'space_keys') and customer_config.space_keys:
                log(f"   Configured spaces: {', '.join(customer_config.space_keys)}")
            elif hasattr(customer_config, 'spaces') and customer_config.spaces:
                enabled_spaces = [s['key'] for s in customer_config.spaces if s.get('enabled', True)]
                log(f"   Configured spaces: {', '.join(enabled_spaces)}")
        except Exception as e:
            log(f"❌ Customer '{customer_id}' not found: {str(e)}")
            return results
        
        # Step 2: Export spaces (unless skipped)
        if not skip_export:
            log(f"\n📥 Step 2: Exporting Confluence spaces...")
            log(f"   Spaces to export: {', '.join(space_keys) if space_keys else 'All configured spaces'}")
            
            start_time = datetime.now()
            export_result = export_customer(customer_id, space_keys)
            duration = (datetime.now() - start_time).total_seconds()
            
            results["export"] = {
                "status": export_result.status,
                "pages_exported": export_result.pages_exported,
                "duration_seconds": duration,
                "errors": export_result.errors if hasattr(export_result, 'errors') else []
            }
            
            if export_result.status == "success":
                log(f"✅ Export completed successfully!")
                log(f"   Pages exported: {export_result.pages_exported}")
                log(f"   Duration: {duration:.2f} seconds")
            elif export_result.status == "partial":
                log(f"⚠️  Export partially completed")
                log(f"   Pages exported: {export_result.pages_exported}")
                if export_result.errors:
                    log(f"   Warnings: {len(export_result.errors)} space(s) had issues")
                    for error in export_result.errors[:3]:  # Show first 3 errors
                        log(f"      - {error[:100]}...")
            else:
                log(f"❌ Export failed: {export_result.error if hasattr(export_result, 'error') else 'Unknown error'}")
                return results
        else:
            log(f"\n⏭️  Step 2: Skipping export (--skip-export flag)")
        
        # Step 3: Build index
        if not skip_index:
            log(f"\n🔍 Step 3: Building RAG index...")
            if clear_existing:
                log(f"   Clearing existing index first...")
            
            start_time = datetime.now()
            index_result = index_customer(customer_id, clear_existing=clear_existing)
            duration = (datetime.now() - start_time).total_seconds()
            
            results["index"] = {
                "status": index_result.status,
                "documents_indexed": index_result.documents_indexed,
                "chunks_created": getattr(index_result, 'chunks_created', 0),
                "duration_seconds": duration
            }
            
            if index_result.status == "success":
                log(f"✅ Index built successfully!")
                log(f"   Documents indexed: {index_result.documents_indexed}")
                log(f"   Chunks created: {getattr(index_result, 'chunks_created', 'N/A')}")
                log(f"   Duration: {duration:.2f} seconds")
            else:
                log(f"❌ Indexing failed: {index_result.error if hasattr(index_result, 'error') else 'Unknown error'}")
                return results
        else:
            log(f"\n⏭️  Step 3: Skipping index build (--skip-index flag)")
        
        # Step 4: Test queries (optional)
        if test_queries:
            log(f"\n❓ Step 4: Testing queries...")
            
            for i, question in enumerate(test_queries, 1):
                log(f"\n   Query {i}: \"{question}\"")
                
                try:
                    query_result = query_customer(customer_id, question, top_k=3)
                    
                    results["queries"].append({
                        "question": question,
                        "status": query_result.status,
                        "documents_found": len(query_result.documents) if hasattr(query_result, 'documents') else 0
                    })
                    
                    if query_result.status == "success":
                        doc_count = len(query_result.documents) if hasattr(query_result, 'documents') else 0
                        log(f"   ✅ Found {doc_count} relevant documents")
                        
                        # Show first document preview
                        if doc_count > 0 and verbose:
                            first_doc = query_result.documents[0]
                            title = first_doc.get('metadata', {}).get('title', 'Untitled')
                            content_preview = first_doc.get('content', '')[:200]
                            log(f"      📄 Top result: {title}")
                            log(f"         Preview: {content_preview}...")
                    else:
                        error_msg = query_result.error if hasattr(query_result, 'error') else 'Unknown error'
                        log(f"   ❌ Query failed: {error_msg}")
                        
                except Exception as e:
                    log(f"   ❌ Query error: {str(e)}")
                    results["queries"].append({
                        "question": question,
                        "status": "error",
                        "error": str(e)
                    })
        
        # Step 5: Summary
        log(f"\n📊 Pipeline Summary")
        log("=" * 60)
        
        # Check overall success
        export_ok = skip_export or (results["export"] and results["export"]["status"] in ["success", "partial"])
        index_ok = skip_index or (results["index"] and results["index"]["status"] == "success")
        results["success"] = export_ok and index_ok
        
        if results["success"]:
            log(f"✅ Pipeline completed successfully for customer '{customer_id}'!")
            
            # Show stats
            if results["export"]:
                log(f"\n📥 Export Stats:")
                log(f"   - Pages exported: {results['export']['pages_exported']}")
                log(f"   - Duration: {results['export']['duration_seconds']:.2f}s")
            
            if results["index"]:
                log(f"\n🔍 Index Stats:")
                log(f"   - Documents indexed: {results['index']['documents_indexed']}")
                log(f"   - Chunks created: {results['index']['chunks_created']}")
                log(f"   - Duration: {results['index']['duration_seconds']:.2f}s")
            
            if results["queries"]:
                log(f"\n❓ Query Results:")
                successful_queries = sum(1 for q in results["queries"] if q["status"] == "success")
                log(f"   - Successful queries: {successful_queries}/{len(results['queries'])}")
            
            # Show next steps
            log(f"\n📌 Next Steps:")
            log(f"   You can now query the knowledge base:")
            log(f"   python -c \"from confluence_rag_integration import query_customer; print(query_customer('{customer_id}', 'Your question here'))\"")
        else:
            log(f"❌ Pipeline failed. Please check the errors above.")
        
        return results
        
    except Exception as e:
        log(f"\n❌ Pipeline error: {str(e)}")
        import traceback
        if verbose:
            traceback.print_exc()
        results["error"] = str(e)
        return results


def main():
    """Main entry point for the pipeline script."""
    parser = argparse.ArgumentParser(
        description="Export and Index Pipeline for Confluence RAG Integration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run full pipeline for a customer
  python export_index_pipeline.py acme_corp
  
  # Clear existing index and rebuild
  python export_index_pipeline.py acme_corp --clear-existing
  
  # Export specific spaces only
  python export_index_pipeline.py acme_corp --spaces PROD ENG
  
  # Skip export if data already exists
  python export_index_pipeline.py acme_corp --skip-export
  
  # Test with sample queries
  python export_index_pipeline.py acme_corp --test-queries "How to reset password?" "What is two-factor auth?"
        """
    )
    
    parser.add_argument(
        "customer_id",
        help="Customer identifier (must have existing configuration)"
    )
    
    parser.add_argument(
        "--clear-existing",
        action="store_true",
        default=False,
        help="Clear existing index before building (default: False)"
    )
    
    parser.add_argument(
        "--spaces", "-s",
        nargs="+",
        help="Specific space keys to export (default: all configured spaces)"
    )
    
    parser.add_argument(
        "--test-queries", "-q",
        nargs="+",
        help="Test queries to run after indexing"
    )
    
    parser.add_argument(
        "--skip-export",
        action="store_true",
        help="Skip the export step (use existing exported data)"
    )
    
    parser.add_argument(
        "--skip-index",
        action="store_true",
        help="Skip the indexing step (use existing index)"
    )
    
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Minimal output (only show errors)"
    )
    
    args = parser.parse_args()
    
    # Default test queries if none provided
    default_test_queries = None
    if not args.skip_index and not args.test_queries:
        # Provide some default test queries for validation
        default_test_queries = [
            "How do I reset my password?",
            "What are the security requirements?",
            "How to set up two-factor authentication?"
        ]
        if not args.quiet:
            print("💡 Tip: Use --test-queries to specify your own test questions")
    
    # Run the pipeline
    results = run_export_index_pipeline(
        customer_id=args.customer_id,
        clear_existing=args.clear_existing,
        space_keys=args.spaces,
        test_queries=args.test_queries or default_test_queries,
        skip_export=args.skip_export,
        skip_index=args.skip_index,
        verbose=not args.quiet
    )
    
    # Exit with appropriate code
    sys.exit(0 if results["success"] else 1)


if __name__ == "__main__":
    main()