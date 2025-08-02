"""Simple entry point functions for the multi-tenant Confluence RAG integration."""

from typing import List, Optional
from .customers.customer_manager import CustomerManager
from .exporters.space_exporter import SpaceExporter
from .rag.query_manager import QueryManager

__version__ = "0.1.0"
__author__ = "Confluence RAG Integration Team"


def export_customer(customer_id: str, space_keys: Optional[List[str]] = None):
    """Export spaces for a customer."""
    manager = CustomerManager()
    exporter = SpaceExporter(manager)
    return exporter.export_spaces(customer_id, space_keys)


def index_customer(customer_id: str, clear_existing: bool = False):
    """Build RAG index for a customer."""
    from .rag.index_manager import IndexManager
    from .rag.indexer_factory import IndexerFactory
    
    manager = CustomerManager()
    index_mgr = IndexManager(manager)
    
    if clear_existing:
        # Clear existing index before building
        config = manager.load_customer(customer_id)
        indexer = IndexerFactory.create_indexer(config)
        indexer.clear_index()
    
    return index_mgr.build_index(customer_id)


def query_customer(customer_id: str, question: str):
    """Query documents for a customer."""
    manager = CustomerManager()
    query_mgr = QueryManager(manager)
    return query_mgr.query(customer_id, question)