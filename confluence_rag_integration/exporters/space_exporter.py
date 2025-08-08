"""Simplified space exporter for batch export operations."""

import time
from datetime import datetime
from typing import List, Optional
from tqdm import tqdm

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
                    from confluence_markdown_exporter.utils.app_data_store import get_settings
                    
                    # Get rate limiting settings
                    settings = get_settings()
                    request_delay = getattr(settings.export, 'request_delay', 0.5)
                    batch_size = getattr(settings.export, 'rate_limit_batch_size', 50)
                    batch_pause = getattr(settings.export, 'rate_limit_batch_pause', 5.0)
                    
                    space = Space.from_key(space_key)
                    page_list = space.pages
                    
                    # Export all pages in space with rate limiting and progress bar
                    print(f"Exporting space {space_key} ({len(page_list)} pages)...")
                    consecutive_failures = 0
                    max_consecutive_failures = 5
                    
                    for idx, page_id in enumerate(tqdm(page_list, desc=f"Space {space_key}", smoothing=0.05)):
                        try:
                            from confluence_markdown_exporter.confluence import Page
                            page = Page.from_id(page_id)
                            page.export()
                            pages_exported += 1
                            consecutive_failures = 0  # Reset on success
                            
                            # Add delay between requests to avoid rate limiting
                            if request_delay > 0 and idx < len(page_list) - 1:
                                time.sleep(request_delay)
                            
                            # Add longer pause every batch_size requests
                            if batch_size > 0 and (idx + 1) % batch_size == 0 and idx < len(page_list) - 1:
                                tqdm.write(f"Rate limit pause ({batch_pause}s) after {idx + 1} pages...")
                                time.sleep(batch_pause)
                                
                        except Exception as e:
                            error_msg = f"Failed to export page {page_id}: {str(e)}"
                            errors.append(error_msg)
                            consecutive_failures += 1
                            
                            # Log the error for visibility
                            tqdm.write(f"⚠️  {error_msg}")
                            
                            # If too many consecutive failures, try to reset the connection
                            if consecutive_failures >= max_consecutive_failures:
                                tqdm.write(f"❌ Too many consecutive failures ({consecutive_failures}). Attempting to reset connection...")
                                try:
                                    # Re-initialize the confluence connection
                                    from confluence_markdown_exporter.api_clients import get_confluence_instance
                                    confluence = get_confluence_instance()
                                    consecutive_failures = 0
                                    tqdm.write("✅ Connection reset successful, continuing...")
                                except Exception as reset_error:
                                    tqdm.write(f"❌ Failed to reset connection: {str(reset_error)}")
                                    break  # Stop processing this space
                            
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