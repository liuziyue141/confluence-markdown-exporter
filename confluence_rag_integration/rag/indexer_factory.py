"""Factory for creating indexers based on configuration."""

from typing import Dict, Any

from .base_indexer import BaseIndexer
from .simple_indexer import SimpleIndexer
from .parent_document_indexer import ParentDocumentIndexer
from ..shared.models import CustomerConfig


class IndexerFactory:
    """Factory to create indexers based on configuration."""
    
    # Available indexer types
    INDEXERS = {
        "simple": SimpleIndexer,
        "parent_document": ParentDocumentIndexer,
    }
    
    @classmethod
    def create_indexer(cls, customer_config: CustomerConfig) -> BaseIndexer:
        """
        Create an indexer based on customer configuration.
        
        Args:
            customer_config: Customer configuration containing indexer settings
            
        Returns:
            Configured indexer instance
        """
        # Get indexer type from config, default to simple
        indexer_type = getattr(customer_config, 'indexer_type', 'simple')
        
        if indexer_type not in cls.INDEXERS:
            raise ValueError(f"Unknown indexer type: {indexer_type}. Available types: {list(cls.INDEXERS.keys())}")
        
        indexer_class = cls.INDEXERS[indexer_type]
        return indexer_class(customer_config)