#!/usr/bin/env python3
"""Test script to verify the full export fix for 901 pages."""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from confluence_rag_integration import export_customer

def test_full_export(customer_id: str):
    """Test export to verify all pages are retrieved."""
    
    print(f"\n🧪 Testing full export for customer: {customer_id}")
    print("=" * 60)
    print("Expected: Should export ALL pages from the space (901 in your case)")
    print("Previous bug: Only exported ~100 pages due to silent pagination failure")
    print("=" * 60)
    
    try:
        result = export_customer(customer_id)
        
        print(f"\n📊 Export Results:")
        print(f"   Status: {result.status}")
        print(f"   Pages exported: {result.pages_exported}")
        print(f"   Duration: {getattr(result, 'duration_seconds', 'N/A')}s")
        
        if result.errors:
            print(f"\n⚠️  Errors encountered: {len(result.errors)}")
            # Show first 5 errors
            for i, error in enumerate(result.errors[:5], 1):
                print(f"   {i}. {error[:200]}...")
        
        # Check if we got significantly more than 100 pages
        if result.pages_exported > 150:
            print(f"\n✅ SUCCESS! Exported {result.pages_exported} pages (more than the previous 100 limit)")
            print("   The pagination fix is working correctly!")
        elif result.pages_exported > 100:
            print(f"\n⚠️  PARTIAL SUCCESS: Exported {result.pages_exported} pages")
            print("   This is more than 100 but may not be all pages.")
            print("   Check the error messages above for any issues.")
        else:
            print(f"\n❌ ISSUE: Only exported {result.pages_exported} pages")
            print("   The fix may not be working. Check DEBUG output for details.")
            
        return result
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_full_export.py <customer_id>")
        print("\nTo run with DEBUG mode for more details:")
        print("  DEBUG=True python test_full_export.py <customer_id>")
        sys.exit(1)
    
    customer_id = sys.argv[1]
    
    # Check if DEBUG mode is enabled
    import os
    if os.environ.get('DEBUG'):
        print("🔍 DEBUG mode is enabled - you'll see detailed HTTP responses")
    
    test_full_export(customer_id)