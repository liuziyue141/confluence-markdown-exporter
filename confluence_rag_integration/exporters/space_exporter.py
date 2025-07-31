"""
Space-focused Confluence exporter for multi-tenant RAG system.

Handles all Confluence API interactions for a specific customer,
focusing on space-level export operations.
"""

import functools
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any, cast

from atlassian.errors import ApiError
from atlassian.errors import ApiNotFoundError
from tqdm import tqdm

# Import from the original confluence exporter
from confluence_markdown_exporter.api_clients import ApiClientFactory
from confluence_markdown_exporter.confluence import (
    Page,
    Space,
    Organization,
    Attachment,
    export_pages as original_export_pages,
    TENANT_CONTEXTS,  # Import the registry
)

from ..shared.models import (
    CustomerConfig,
    ExportResult,
    ExportMetadata,
    ExportStatus,
)
from ..shared.utils import generate_content_hash


class SpaceExporter:
    """
    Handles all Confluence API interactions for a specific customer.
    
    This exporter focuses on space-level operations and maintains complete
    isolation between different customers through clean dependency injection.
    
    Key Responsibilities:
    - Authenticate with customer's Confluence instance
    - Export entire spaces to markdown files
    - Handle API errors and retries with customer-specific settings
    - Generate comprehensive export metadata
    
    Usage:
        exporter = SpaceExporter(customer_config)
        result = exporter.export_spaces(["DEMO", "TECH"])
        
    Thread-Safe: Yes - each instance uses isolated dependencies
    """
    
    def __init__(self, customer_config: CustomerConfig):
        """
        Initialize the exporter with customer-specific configuration.
        
        Args:
            customer_config: Customer configuration containing:
                - Confluence authentication (URL, username, API token)
                - Export settings (output paths, markdown options)
                - Space configurations (which spaces to export)
                
        Sets up:
            - Authenticated Confluence API client
            - Customer-specific export settings
            - Error tracking for this export session
        """
        self.customer_config = customer_config
        self.confluence_client = self._create_confluence_client()
        self.settings = self._create_customer_settings()
        
        # Add context to the global registry
        TENANT_CONTEXTS[self.customer_config.customer_id] = {
            'client': self.confluence_client,
            'settings': self.settings
        }
        
        # Export session tracking
        self.exported_documents: List[ExportMetadata] = []
        self.errors: List[str] = []

    def close(self):
        """Removes this exporter's context from the global registry."""
        if self.customer_config.customer_id in TENANT_CONTEXTS:
            del TENANT_CONTEXTS[self.customer_config.customer_id]
    
    def export_spaces(self, space_keys: Optional[List[str]] = None) -> ExportResult:
        """
        Export specified spaces to markdown files.
        
        This is the main export method that handles multiple spaces,
        processes all pages within each space, and generates comprehensive
        export metadata.
        
        Args:
            space_keys: List of space keys to export (e.g., ["DEMO", "TECH"])
                       If None, exports all enabled spaces from customer config
            
        Returns:
            ExportResult containing:
                - Export statistics (total/successful/failed pages)
                - List of exported document metadata
                - Any errors encountered during export
                - Export timing information
                
        Process:
        1. Validate and filter spaces to export
        2. For each space:
           - Get space information from Confluence
           - Retrieve all pages (homepage + descendants)
           - Export each page to markdown with attachments
           - Generate metadata for change detection
        3. Compile comprehensive results
        
        Error Handling:
        - Individual page failures don't stop the export
        - Space access failures are logged but don't crash
        - Network errors are retried automatically
        """
        result = ExportResult(
            customer_id=self.customer_config.customer_id,
            status=ExportStatus.IN_PROGRESS,
        )
        
        try:
            # Determine which spaces to export
            spaces_to_export = self._get_spaces_to_export(space_keys)
            
            if not spaces_to_export:
                result.status = ExportStatus.COMPLETED
                result.end_time = datetime.utcnow()
                return result
            
            # Export each space with detailed tracking
            total_pages = 0
            successful_pages = 0
            total_attachments = 0
            successful_attachments = 0
            
            for space_config in spaces_to_export:
                try:
                    space_result = self._export_single_space(space_config)
                    
                    # Aggregate statistics
                    total_pages += space_result['total_pages']
                    successful_pages += space_result['successful_pages']
                    total_attachments += space_result['total_attachments']
                    successful_attachments += space_result['successful_attachments']
                    
                    # Collect metadata and errors
                    self.exported_documents.extend(space_result['exported_documents'])
                    self.errors.extend(space_result['errors'])
                    
                except Exception as e:
                    error_msg = f"Failed to export space '{space_config.key}': {str(e)}"
                    self.errors.append(error_msg)
                    print(error_msg)
            
            # Finalize export result
            result.total_pages = total_pages
            result.successful_pages = successful_pages
            result.failed_pages = total_pages - successful_pages
            result.total_attachments = total_attachments
            result.successful_attachments = successful_attachments
            result.exported_documents = self.exported_documents
            result.errors = self.errors
            result.status = ExportStatus.COMPLETED if len(self.errors) == 0 else ExportStatus.PARTIAL
            result.end_time = datetime.utcnow()
            
        except Exception as e:
            result.status = ExportStatus.FAILED
            result.errors = [f"Export failed: {str(e)}"]
            result.end_time = datetime.utcnow()
        
        return result
    
    def test_connection(self) -> bool:
        """
        Test the Confluence connection for this customer.
        
        Validates that we can successfully authenticate and communicate
        with the customer's Confluence instance.
        
        Returns:
            True if connection is successful, False otherwise
            
        This method is used during setup validation to ensure
        credentials are correct before attempting full exports.
        """
        try:
            # Test with minimal API call
            self.confluence_client.get_all_spaces(limit=1)
            return True
        except Exception as e:
            print(f"Connection test failed for customer '{self.customer_config.customer_id}': {str(e)}")
            return False
    
    def _get_spaces_to_export(self, space_keys: Optional[List[str]]) -> List:
        """Get list of space configurations to export."""
        if space_keys is None:
            # Export all enabled spaces
            return [space for space in self.customer_config.spaces if space.enabled]
        else:
            # Export only specified spaces that are enabled
            return [
                space for space in self.customer_config.spaces 
                if space.key in space_keys and space.enabled
            ]
    
    def _export_single_space(self, space_config) -> Dict[str, Any]:
        """
        Export a single space with all its pages.
        
        Args:
            space_config: Space configuration object
            
        Returns:
            Dictionary with export statistics and results for this space
        """
        try:
            # Get space information using customer's Confluence client
            space = self._get_space_with_dependencies(space_config.key)
            
            # Determine pages to export based on configuration
            if space_config.export_descendants:
                page_ids = space.pages  # Homepage + all descendants
            else:
                page_ids = [space.homepage]  # Only homepage
            
            # Export all pages in this space
            return self._export_pages_in_space(page_ids)
            
        except Exception as e:
            return {
                'total_pages': 0,
                'successful_pages': 0,
                'total_attachments': 0,
                'successful_attachments': 0,
                'exported_documents': [],
                'errors': [f"Failed to export space '{space_config.key}': {str(e)}"]
            }
    
    def _get_space_with_dependencies(self, space_key: str):
        """Get space information using clean dependency injection."""
        # Pass the hashable customer_id
        return Space.from_key(
            space_key, 
            customer_id=self.customer_config.customer_id
        )
    
    def _export_pages_in_space(self, page_ids: List[int]) -> Dict[str, Any]:
        """
        Export all pages in a space using customer-specific configuration.
        
        Args:
            page_ids: List of page IDs to export
            
        Returns:
            Dictionary with detailed export statistics and metadata
        """
        successful_pages = 0
        total_attachments = 0
        successful_attachments = 0
        exported_documents = []
        errors = []
        
        # Process each page with progress tracking
        for page_id in tqdm(page_ids, desc=f"Exporting pages for {self.customer_config.customer_id}"):
            try:
                # Create page with injected dependencies (no global state!)
                # Pass the hashable customer_id
                page = Page.from_id(
                    page_id,
                    customer_id=self.customer_config.customer_id
                )
                
                if page.title == "Page not accessible":
                    print(f"Skipping inaccessible page with ID {page_id}")
                    continue
                
                # Export page to markdown with attachments
                page.export()
                
                # Generate metadata for caching and change detection
                export_metadata = ExportMetadata(
                    page_id=page.id,
                    space_key=page.space.key,
                    space_name=page.space.name,
                    title=page.title,
                    export_path=self.customer_config.export.output_path / page.export_path,
                    breadcrumb=" > ".join([
                        Page.from_id(
                            ancestor,
                            customer_id=self.customer_config.customer_id
                        ).title 
                        for ancestor in page.ancestors
                    ]),
                    labels=[label.name for label in page.labels],
                    content_hash=generate_content_hash(page.markdown),
                )
                
                exported_documents.append(export_metadata)
                successful_pages += 1
                
                # Track attachment statistics
                total_attachments += len(page.attachments)
                successful_attachments += len(page.attachments)  # Simplified for now
                
            except Exception as e:
                error_msg = f"Failed to export page {page_id}: {str(e)}"
                errors.append(error_msg)
                print(error_msg)
        
        return {
            'total_pages': len(page_ids),
            'successful_pages': successful_pages,
            'total_attachments': total_attachments,
            'successful_attachments': successful_attachments,
            'exported_documents': exported_documents,
            'errors': errors,
        }
    
    def _create_confluence_client(self):
        """Create authenticated Confluence client for this customer."""
        auth_config = self.customer_config.confluence
        connection_config = {
            "backoff_and_retry": True,
            "backoff_factor": 2,
            "max_backoff_seconds": 60,
            "max_backoff_retries": 5,
            "retry_status_codes": [413, 429, 502, 503, 504],
            "verify_ssl": True,
        }
        
        factory = ApiClientFactory(connection_config)
        
        # Convert our config to the format expected by the API factory
        api_details = type('ApiDetails', (), {
            'url': auth_config.url,
            'username': auth_config.username,
            'api_token': auth_config.api_token,
            'pat': auth_config.pat,
        })()
        
        return factory.create_confluence(api_details)
    
    def _create_customer_settings(self):
        """Create a settings object compatible with the original exporter."""
        from confluence_markdown_exporter.utils.app_data_store import ExportConfig
        
        # Convert our customer config to the original format
        export_config = ExportConfig(
            output_path=self.customer_config.export.output_path,
            page_path=self.customer_config.export.page_path,
            attachment_path=self.customer_config.export.attachment_path,
            page_breadcrumbs=self.customer_config.export.include_breadcrumbs,
            include_document_title=self.customer_config.export.include_document_title,
            download_external_images=self.customer_config.export.download_external_images,
        )
        
        # Create a settings object that mimics the original structure
        settings = type('Settings', (), {
            'export': export_config
        })()
        
        return settings 