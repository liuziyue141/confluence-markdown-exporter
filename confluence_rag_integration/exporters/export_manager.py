"""
Export workflow manager for multi-tenant Confluence RAG system.

Orchestrates the complete export workflow with caching, tracking,
and environment validation for space-level operations.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

from .space_exporter import SpaceExporter
from ..rag.customer_rag_manager import CustomerRAGManager
from ..shared.models import (
    CustomerConfig,
    ExportResult,
    ExportStatus,
    ExportMetadata,
    RAGStatus,
)


class ExportManager:
    """
    Orchestrates the complete export workflow with caching and tracking.
    
    This manager coordinates space export operations, manages caching for
    change detection, tracks export history, and validates the environment.
    
    Key Responsibilities:
    - Coordinate space export operations via SpaceExporter
    - Cache management for change detection and optimization
    - Export result tracking and historical analysis
    - Environment validation (connections, file permissions, etc.)
    
    Usage:
        manager = ExportManager(customer_config)
        result = manager.export(["DEMO", "TECH"])
        
    Cache Structure:
        cache/export_cache.json     - Page metadata for change detection
        cache/export_results/       - Historical export results
        
    Thread-Safe: Yes - each instance operates on isolated customer data
    """
    
    def __init__(self, customer_config: CustomerConfig):
        """
        Initialize export manager for a specific customer.
        
        Args:
            customer_config: Customer configuration containing:
                - Export settings (output paths, cache locations)
                - Space configurations
                - Confluence authentication details
                - RAG configuration
                
        Sets up:
            - SpaceExporter instance for API operations
            - CustomerRAGManager for RAG operations
            - Cache directory structure
            - Export result tracking system
        """
        self.customer_config = customer_config
        self.exporter = SpaceExporter(customer_config)
        self._rag_manager = None  # Lazy initialization for RAG integration
        
        # Cache and tracking setup
        self.cache_path = customer_config.export.output_path.parent / "cache"
        self.cache_path.mkdir(exist_ok=True)
        
        # Change detection cache
        self._export_cache_file = self.cache_path / "export_cache.json"
        self._previous_exports: Dict[int, ExportMetadata] = self._load_export_cache()
    
    @property
    def rag_manager(self) -> CustomerRAGManager:
        """Lazy initialization of RAG manager to avoid startup issues."""
        if self._rag_manager is None:
            self._rag_manager = CustomerRAGManager(self.customer_config)
        return self._rag_manager
    
    def export(self, space_keys: Optional[List[str]] = None) -> ExportResult:
        """
        Main export workflow for space-level operations.
        
        This is the primary method for exporting Confluence spaces.
        It coordinates the entire workflow from validation through
        completion with comprehensive result tracking.
        
        Args:
            space_keys: List of space keys to export (e.g., ["DEMO", "TECH"])
                       If None, exports all enabled spaces from customer config
            
        Returns:
            ExportResult containing:
                - Detailed export statistics
                - List of exported document metadata
                - Error information if any issues occurred
                - Timing and performance data
                
        Workflow:
        1. Log export initiation
        2. Execute space export via SpaceExporter
        3. Update cache with new page metadata (for change detection)
        4. Save export result for historical tracking
        5. Return comprehensive results
        
        Error Handling:
        - Individual page/space failures don't stop the entire export
        - Results include partial success information
        - All errors are captured and reported
        """
        print(f"🚀 Starting export for customer: {self.customer_config.customer_id}")
        
        # Execute the space export
        result = self.exporter.export_spaces(space_keys)
        
        # Update cache with successful exports for change detection
        if result.status in [ExportStatus.COMPLETED, ExportStatus.PARTIAL]:
            self._update_export_cache(result.exported_documents)
        
        # Save export result for historical tracking and debugging
        self._save_export_result(result)
        
        # Log completion
        print(f"✅ Export completed with status: {result.status.value}")
        if result.errors:
            print(f"⚠️  {len(result.errors)} errors occurred during export")
        
        return result
    
    def export_and_index(self, space_keys: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Complete workflow: Export spaces then build RAG index.
        
        This is the integrated workflow that combines export and RAG indexing
        operations for a seamless experience. It performs the export first,
        then automatically builds/updates the RAG index if export is successful.
        
        Args:
            space_keys: List of space keys to export (e.g., ["DEMO", "TECH"])
                       If None, exports all enabled spaces from customer config
                       
        Returns:
            Dict containing both export and RAG results:
                export_result: ExportResult from the export operation
                rag_result: Dict from RAG indexing operation
                overall_status: Combined status of both operations
                
        Workflow:
        1. Execute space export via standard export() method
        2. If export successful (COMPLETED or PARTIAL), build/update RAG index
        3. Return combined results for both operations
        
        Error Handling:
        - Export failures prevent RAG indexing
        - RAG failures don't affect export results
        - Both results are returned for troubleshooting
        """
        print(f"🚀 Starting integrated export + indexing for customer: {self.customer_config.customer_id}")
        
        # Step 1: Export spaces
        export_result = self.export(space_keys)
        
        # Step 2: Build/update RAG index if export successful
        rag_result = {}
        if export_result.status in [ExportStatus.COMPLETED, ExportStatus.PARTIAL]:
            print(f"📚 Export successful, starting RAG indexing...")
            
            try:
                rag_result = self.rag_manager.update_index(self.customer_config.export.output_path)
                print(f"✅ RAG indexing completed: {rag_result.get('status', 'unknown')}")
            except Exception as e:
                rag_result = {
                    "status": "error",
                    "error": str(e),
                    "customer_id": self.customer_config.customer_id
                }
                print(f"❌ RAG indexing failed: {e}")
        else:
            print(f"⚠️  Skipping RAG indexing due to export status: {export_result.status}")
            rag_result = {
                "status": "skipped",
                "reason": f"Export status was {export_result.status}",
                "customer_id": self.customer_config.customer_id
            }
        
        # Determine overall status
        if export_result.status == ExportStatus.COMPLETED and rag_result.get("status") == "success":
            overall_status = "completed"
        elif export_result.status in [ExportStatus.COMPLETED, ExportStatus.PARTIAL] and rag_result.get("status") in ["success", "skipped"]:
            overall_status = "partial"
        else:
            overall_status = "failed"
        
        combined_result = {
            "export_result": export_result,
            "rag_result": rag_result,
            "overall_status": overall_status,
            "customer_id": self.customer_config.customer_id,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        print(f"🎯 Integrated workflow completed with status: {overall_status}")
        return combined_result
    
    def build_rag_index(self, force_rebuild: bool = False) -> Dict[str, Any]:
        """
        Build or rebuild RAG index for customer's exported documents.
        
        Args:
            force_rebuild: If True, performs full rebuild. If False, does incremental update.
            
        Returns:
            Dict with RAG indexing results
        """
        print(f"🧠 {'Rebuilding' if force_rebuild else 'Updating'} RAG index for customer: {self.customer_config.customer_id}")
        
        try:
            if force_rebuild:
                result = self.rag_manager.build_index(self.customer_config.export.output_path)
            else:
                result = self.rag_manager.update_index(self.customer_config.export.output_path)
            
            print(f"✅ RAG indexing completed: {result.get('status', 'unknown')}")
            return result
        except Exception as e:
            error_result = {
                "status": "error",
                "error": str(e),
                "customer_id": self.customer_config.customer_id
            }
            print(f"❌ RAG indexing failed: {e}")
            return error_result
    
    def get_rag_stats(self) -> Dict[str, Any]:
        """
        Get RAG statistics for this customer.
        
        Returns:
            Dict with customer RAG statistics
        """
        return self.rag_manager.get_stats()
    
    def test_setup(self) -> Dict[str, Any]:
        """
        Validate complete export environment for this customer.
        
        Performs comprehensive validation of all components needed
        for successful exports. This should be run before attempting
        actual exports to catch configuration issues early.
        
        Returns:
            Dict containing validation results:
                confluence_connection: bool - Can connect to Confluence
                export_directory_writable: bool - Can write to export directory  
                cache_directory_writable: bool - Can write to cache directory
                accessible_spaces: int - Number of spaces we can access
                total_configured_spaces: int - Total enabled spaces in config
                validation_summary: str - Overall status message
                
        Validation Checks:
        1. Confluence API connectivity and authentication
        2. File system permissions for export and cache directories
        3. Space accessibility for all configured spaces
        4. Overall environment readiness assessment
        """
        results = {}
        
        # Test Confluence connection and authentication
        print("🔍 Testing Confluence connection...")
        results['confluence_connection'] = self.exporter.test_connection()
        
        # Test export directory write permissions
        print("📁 Testing export directory permissions...")
        try:
            self.customer_config.export.output_path.mkdir(parents=True, exist_ok=True)
            test_file = self.customer_config.export.output_path / ".test_write"
            test_file.write_text("test")
            test_file.unlink()
            results['export_directory_writable'] = True
        except Exception as e:
            results['export_directory_writable'] = False
            results['export_directory_error'] = str(e)
        
        # Test cache directory write permissions
        print("💾 Testing cache directory permissions...")
        try:
            self.cache_path.mkdir(parents=True, exist_ok=True)
            test_file = self.cache_path / ".test_write"
            test_file.write_text("test")
            test_file.unlink()
            results['cache_directory_writable'] = True
        except Exception as e:
            results['cache_directory_writable'] = False
            results['cache_directory_error'] = str(e)
        
        # Test space accessibility
        print("🏢 Testing space accessibility...")
        accessible_spaces = []
        enabled_spaces = [s for s in self.customer_config.spaces if s.enabled]
        
        for space_config in enabled_spaces:
            try:
                # Test basic space access
                space = self.exporter._get_space_with_dependencies(space_config.key)
                accessible_spaces.append(space_config.key)
            except Exception as e:
                print(f"   ⚠️  Cannot access space '{space_config.key}': {e}")
        
        results['accessible_spaces'] = len(accessible_spaces)
        results['total_configured_spaces'] = len(enabled_spaces)
        results['accessible_space_keys'] = accessible_spaces
        
        # Generate validation summary
        all_passed = (
            results['confluence_connection'] and
            results['export_directory_writable'] and
            results['cache_directory_writable'] and
            results['accessible_spaces'] == results['total_configured_spaces']
        )
        
        if all_passed:
            results['validation_summary'] = "✅ All validation checks passed - ready for export"
        else:
            issues = []
            if not results['confluence_connection']:
                issues.append("Confluence connection failed")
            if not results['export_directory_writable']:
                issues.append("Export directory not writable")
            if not results['cache_directory_writable']:
                issues.append("Cache directory not writable")
            if results['accessible_spaces'] < results['total_configured_spaces']:
                issues.append(f"Only {results['accessible_spaces']}/{results['total_configured_spaces']} spaces accessible")
            
            results['validation_summary'] = f"❌ Issues found: {'; '.join(issues)}"
        
        return results
    
    def get_export_history(self, limit: int = 10) -> List[Dict]:
        """
        Get history of recent exports for analysis and monitoring.
        
        Args:
            limit: Maximum number of recent exports to return
            
        Returns:
            List of export result summaries, newest first
            
        Each summary contains:
            - timestamp: When the export started
            - status: completed/partial/failed
            - total_pages: Number of pages processed
            - successful_pages: Number of pages exported successfully
            - duration: How long the export took
            - errors_count: Number of errors encountered
        """
        results_dir = self.cache_path / "export_results"
        
        if not results_dir.exists():
            return []
        
        history = []
        
        # Get all result files, sorted by modification time (newest first)
        result_files = sorted(
            results_dir.glob("export_result_*.json"),
            key=lambda f: f.stat().st_mtime,
            reverse=True
        )
        
        for result_file in result_files[:limit]:
            try:
                with open(result_file, 'r', encoding='utf-8') as f:
                    result_data = json.load(f)
                
                # Create summary
                summary = {
                    'timestamp': result_data.get('start_time'),
                    'status': result_data.get('status'),
                    'total_pages': result_data.get('total_pages', 0),
                    'successful_pages': result_data.get('successful_pages', 0),
                    'duration': result_data.get('duration'),
                    'errors_count': len(result_data.get('errors', [])),
                }
                
                history.append(summary)
                
            except Exception as e:
                print(f"Error reading export result file {result_file}: {e}")
        
        return history
    
    def cleanup_old_exports(self, keep_days: int = 30):
        """
        Clean up old export results and cache files to manage disk usage.
        
        Args:
            keep_days: Number of days of history to retain
            
        Removes:
            - Export result files older than keep_days
            - Does NOT remove export_cache.json (needed for change detection)
            - Does NOT remove actual exported markdown files
        """
        cutoff_time = datetime.utcnow() - timedelta(days=keep_days)
        cutoff_timestamp = cutoff_time.timestamp()
        
        results_dir = self.cache_path / "export_results"
        
        if results_dir.exists():
            cleaned_count = 0
            for result_file in results_dir.glob("export_result_*.json"):
                try:
                    if result_file.stat().st_mtime < cutoff_timestamp:
                        result_file.unlink()
                        cleaned_count += 1
                except Exception as e:
                    print(f"Error cleaning up {result_file}: {e}")
            
            if cleaned_count > 0:
                print(f"🧹 Cleaned up {cleaned_count} old export result files")
    
    def _load_export_cache(self) -> Dict[int, ExportMetadata]:
        """
        Load previous export cache for change detection.
        
        The export cache contains metadata about previously exported pages,
        including content hashes. This enables future incremental exports
        by detecting which pages have actually changed.
        
        Cache structure:
        {
            "page_id": {
                "page_id": 12345,
                "space_key": "DEMO",
                "title": "My Page", 
                "content_hash": "abc123...",
                "export_path": "/path/to/page.md",
                "exported_at": "2024-01-15T10:30:00Z"
            }
        }
        """
        cache = {}
        
        if self._export_cache_file.exists():
            try:
                with open(self._export_cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                
                for page_id_str, metadata_dict in cache_data.items():
                    try:
                        # Convert string keys back to int
                        page_id = int(page_id_str)
                        # Convert dict back to ExportMetadata
                        metadata_dict['export_path'] = Path(metadata_dict['export_path'])
                        cache[page_id] = ExportMetadata(**metadata_dict)
                    except Exception as e:
                        print(f"Error loading cached metadata for page {page_id_str}: {e}")
                        
            except Exception as e:
                print(f"Error loading export cache: {e}")
        
        return cache
    
    def _save_export_cache(self):
        """Save export cache to disk for future change detection."""
        cache_data = {}
        
        for page_id, metadata in self._previous_exports.items():
            # Convert to dict for JSON serialization
            metadata_dict = metadata.dict()
            metadata_dict['export_path'] = str(metadata_dict['export_path'])
            cache_data[str(page_id)] = metadata_dict
        
        try:
            with open(self._export_cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2, default=str)
        except Exception as e:
            print(f"Error saving export cache: {e}")
    
    def _update_export_cache(self, exported_documents: List[ExportMetadata]):
        """Update the export cache with newly exported documents."""
        for metadata in exported_documents:
            self._previous_exports[metadata.page_id] = metadata
        
        self._save_export_cache()
    
    def _save_export_result(self, result: ExportResult):
        """
        Save export result for historical tracking and debugging.
        
        Results are saved with timestamp-based filenames for easy analysis.
        These files help with:
        - Debugging export issues
        - Performance monitoring
        - Historical analysis of export patterns
        """
        results_dir = self.cache_path / "export_results"
        results_dir.mkdir(exist_ok=True)
        
        timestamp = result.start_time.strftime("%Y%m%d_%H%M%S")
        result_file = results_dir / f"export_result_{timestamp}.json"
        
        try:
            # Convert result to dict for serialization
            result_dict = result.dict()
            
            # Convert paths to strings for JSON compatibility
            for doc in result_dict.get('exported_documents', []):
                if 'export_path' in doc:
                    doc['export_path'] = str(doc['export_path'])
            
            with open(result_file, 'w', encoding='utf-8') as f:
                json.dump(result_dict, f, indent=2, default=str)
                
        except Exception as e:
            print(f"Error saving export result: {e}") 