"""Config adapter to bridge our simple config to the original exporter format."""

from pathlib import Path

from .models import CustomerConfig


class ConfigAdapter:
    """Converts our simple CustomerConfig to original exporter format."""
    
    @staticmethod
    def setup_global_config(customer_config: CustomerConfig, base_path: Path):
        """Set up global configuration for original exporter (monkey-patch globals)."""
        from confluence_markdown_exporter.utils.app_data_store import set_setting
        from confluence_markdown_exporter.api_clients import get_confluence_instance
                
        # Set up global settings using the configuration system
        export_path = str(base_path / customer_config.customer_id / "exports")
        
        # Set auth settings
        set_setting("auth.confluence.url", customer_config.confluence_url)
        set_setting("auth.confluence.username", customer_config.confluence_username)
        set_setting("auth.confluence.api_token", customer_config.confluence_api_token)
        
        # Set export settings
        set_setting("export.output_path", export_path)
        set_setting("export.page_breadcrumbs", True)
        set_setting("export.include_document_title", True)
        set_setting("export.download_external_images", True)
        
        # Get Confluence client using the global configuration
        confluence = get_confluence_instance()
        
        return confluence