"""Simplified space exporter for batch export operations."""

import time
from datetime import datetime
from typing import List, Optional

from ..customers.customer_manager import CustomerManager
from ..shared.config_adapter import ConfigAdapter
from ..shared.models import ExportResult


class SpaceExporter:
    """Simple batch operation for exporting Confluence spaces."""
    
    def __init__(self, customer_manager: CustomerManager):
        self.customer_manager = customer_manager
    
    def export_spaces(self, customer_id: str, space_keys: Optional[List[str]] = None) -> ExportResult:
        """Export spaces for a customer using the original exporter."""
        start_time = time.time()
        
        try:
            # Load config
            config = self.customer_manager.load_customer(customer_id)
            
            # Use ConfigAdapter to set up global configuration before using Space
            customer_confluence = ConfigAdapter.setup_global_config(
                config, 
                self.customer_manager.base_path
            )
            from confluence_markdown_exporter.confluence import confluence
            confluence = customer_confluence
            
            # Determine which spaces to export
            spaces_to_export = space_keys or config.space_keys
            
            # Export using original exporter
            pages_exported = 0
            errors = []
            
            for space_key in spaces_to_export:
                try:
                    # Import and use original space export functionality
                    from confluence_markdown_exporter.confluence import Space
                    
                    space = Space.from_key(space_key)
                    
                    # Export all pages in space
                    for page_id in space.pages:
                        try:
                            from confluence_markdown_exporter.confluence import Page
                            page = Page.from_id(page_id)
                            page.export()
                            pages_exported += 1
                        except Exception as e:
                            errors.append(f"Failed to export page {page_id}: {str(e)}")
                            
                except Exception as e:
                    errors.append(f"Failed to export space {space_key}: {str(e)}")
            
            # Create result
            duration = time.time() - start_time
            status = "success" if not errors else ("partial" if pages_exported > 0 else "failed")
            
            result = ExportResult(
                status=status,
                pages_exported=pages_exported,
                errors=errors,
                timestamp=datetime.now().isoformat(),
                duration_seconds=duration
            )
            
            # Update state
            self.customer_manager.update_export_state(customer_id, result.__dict__)
            
            return result
            
        except Exception as e:
            duration = time.time() - start_time
            result = ExportResult(
                status="failed",
                pages_exported=0,
                errors=[str(e)],
                timestamp=datetime.now().isoformat(),
                duration_seconds=duration
            )
            
            self.customer_manager.update_export_state(customer_id, result.__dict__)
            return result