"""Unified RAG interface for multi-tenant Confluence RAG integration."""

from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path

from ..shared.models import CustomerConfig, QueryResult, RAGStatus
from ..customers.customer_manager import CustomerManager
from .customer_rag_manager import CustomerRAGManager
from .query_manager import CustomerQueryManager, RAGFactory


class MultiTenantRAGInterface:
    """
    Unified interface for multi-tenant RAG operations.
    
    This is the main entry point for all RAG operations across customers.
    It provides a clean, high-level API that handles customer isolation,
    state management, and operation coordination.
    
    Key Features:
    - Customer-isolated RAG operations
    - Integrated export + indexing workflows
    - Query management with source attribution
    - Performance monitoring and statistics
    - State management and error handling
    """
    
    def __init__(self, base_data_path: Optional[Path] = None):
        """
        Initialize the multi-tenant RAG interface.
        
        Args:
            base_data_path: Base directory for customer data (defaults to ./data/customers)
        """
        self.customer_manager = CustomerManager(base_data_path)
        self._export_managers: Dict[str, Any] = {}  # ExportManager instances
    
    def get_export_manager(self, customer_id: str):
        """Get or create export manager for customer (with caching)."""
        if customer_id not in self._export_managers:
            # Lazy import to avoid circular dependency
            from ..exporters.export_manager import ExportManager
            config = self.customer_manager.load_customer(customer_id)
            self._export_managers[customer_id] = ExportManager(config)
        return self._export_managers[customer_id]
    
    def export_and_index(self, customer_id: str, space_keys: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Complete workflow: Export customer's spaces and build RAG index.
        
        Args:
            customer_id: Customer identifier
            space_keys: Optional list of space keys to export
            
        Returns:
            Dict with combined export and indexing results
        """
        # Mark RAG as building
        self.customer_manager.mark_rag_building(customer_id)
        
        export_manager = None
        try:
            # Get export manager and run integrated workflow
            export_manager = self.get_export_manager(customer_id)
            result = export_manager.export_and_index(space_keys)
            
            # Update customer state based on results
            if result["overall_status"] == "completed":
                rag_result = result["rag_result"]
                self.customer_manager.update_rag_statistics(
                    customer_id,
                    documents_processed=rag_result.get("documents_processed", 0),
                    chunks_created=rag_result.get("chunks_created", 0)
                )
            elif result["overall_status"] == "failed":
                self.customer_manager.mark_rag_failed(customer_id)
            
            return result
            
        except Exception as e:
            # Mark RAG as failed
            self.customer_manager.mark_rag_failed(customer_id, str(e))
            raise
        finally:
            # Ensure proper cleanup of tenant context
            if export_manager and hasattr(export_manager, 'space_exporter'):
                export_manager.space_exporter.close()
    
    def query_customer(self, customer_id: str, question: str, top_k: int = 3) -> QueryResult:
        """
        Query a specific customer's knowledge base.
        
        Args:
            customer_id: Customer identifier
            question: Question to ask
            top_k: Number of documents to retrieve
            
        Returns:
            QueryResult with answer and source attribution
        """
        config = self.customer_manager.load_customer(customer_id)
        query_manager = RAGFactory.get_query_manager(config)
        return query_manager.query(question, top_k)
    
    def rebuild_customer_index(self, customer_id: str) -> Dict[str, Any]:
        """
        Rebuild RAG index for a specific customer.
        
        Args:
            customer_id: Customer identifier
            
        Returns:
            Dict with rebuild results
        """
        # Mark RAG as building
        self.customer_manager.mark_rag_building(customer_id)
        
        export_manager = None
        try:
            export_manager = self.get_export_manager(customer_id)
            result = export_manager.build_rag_index(force_rebuild=True)
            
            # Update customer state
            if result.get("status") == "success":
                self.customer_manager.update_rag_statistics(
                    customer_id,
                    documents_processed=result.get("documents_processed", 0),
                    chunks_created=result.get("chunks_created", 0)
                )
            else:
                self.customer_manager.mark_rag_failed(customer_id)
            
            return result
            
        except Exception as e:
            self.customer_manager.mark_rag_failed(customer_id, str(e))
            raise
        finally:
            # Ensure proper cleanup of tenant context
            if export_manager and hasattr(export_manager, 'space_exporter'):
                export_manager.space_exporter.close()
    
    def update_customer_index(self, customer_id: str) -> Dict[str, Any]:
        """
        Update RAG index incrementally for a specific customer.
        
        Args:
            customer_id: Customer identifier
            
        Returns:
            Dict with update results
        """
        # Mark RAG as updating
        self.customer_manager.update_rag_status(customer_id, RAGStatus.UPDATING)
        
        export_manager = None
        try:
            export_manager = self.get_export_manager(customer_id)
            result = export_manager.build_rag_index(force_rebuild=False)
            
            # Update customer state
            if result.get("status") == "success":
                self.customer_manager.update_rag_statistics(
                    customer_id,
                    documents_processed=result.get("documents_processed", 0),
                    chunks_created=result.get("chunks_created", 0)
                )
            else:
                self.customer_manager.mark_rag_failed(customer_id)
            
            return result
            
        except Exception as e:
            self.customer_manager.mark_rag_failed(customer_id, str(e))
            raise
        finally:
            # Ensure proper cleanup of tenant context
            if export_manager and hasattr(export_manager, 'space_exporter'):
                export_manager.space_exporter.close()
    
    def get_customer_rag_stats(self, customer_id: str) -> Dict[str, Any]:
        """
        Get RAG statistics for a specific customer.
        
        Args:
            customer_id: Customer identifier
            
        Returns:
            Dict with customer RAG statistics
        """
        try:
            export_manager = self.get_export_manager(customer_id)
            rag_stats = export_manager.get_rag_stats()
            
            # Add customer state information
            state = self.customer_manager.get_customer_state(customer_id)
            rag_stats.update({
                "rag_status": state.rag_status.value,
                "last_index_time": state.last_index_time.isoformat() if state.last_index_time else None,
                "total_indexed_documents": state.total_indexed_documents,
                "total_indexed_chunks": state.total_indexed_chunks,
                "is_ready_for_queries": state.is_ready_for_queries
            })
            
            return rag_stats
            
        except Exception as e:
            return {
                "customer_id": customer_id,
                "error": str(e),
                "rag_status": "error"
            }
    
    def get_all_customer_stats(self) -> Dict[str, Any]:
        """
        Get RAG statistics for all customers.
        
        Returns:
            Dict with all customer RAG statistics
        """
        all_stats = {}
        
        for customer_id in self.customer_manager.list_customers():
            try:
                all_stats[customer_id] = self.get_customer_rag_stats(customer_id)
            except Exception as e:
                all_stats[customer_id] = {
                    "error": str(e),
                    "rag_status": "error"
                }
        
        return all_stats
    
    def validate_customer_rag(self, customer_id: str) -> Dict[str, Any]:
        """
        Validate customer's RAG configuration and readiness.
        
        Args:
            customer_id: Customer identifier
            
        Returns:
            Dict with validation results
        """
        # Basic config validation
        config_validation = self.customer_manager.validate_rag_config(customer_id)
        
        # Test RAG system readiness
        try:
            config = self.customer_manager.load_customer(customer_id)
            query_manager = RAGFactory.get_query_manager(config)
            rag_ready = query_manager.is_ready()
        except Exception as e:
            rag_ready = False
            config_validation["rag_test_error"] = str(e)
        
        config_validation.update({
            "rag_system_ready": rag_ready,
            "validation_time": datetime.utcnow().isoformat()
        })
        
        return config_validation
    
    def cleanup_customer_rag(self, customer_id: str) -> bool:
        """
        Cleanup customer's RAG index and data.
        
        Args:
            customer_id: Customer identifier
            
        Returns:
            True if cleanup successful, False otherwise
        """
        try:
            config = self.customer_manager.load_customer(customer_id)
            rag_manager = RAGFactory.get_rag_manager(config)
            
            # Cleanup the index
            cleanup_successful = rag_manager.cleanup_index()
            
            if cleanup_successful:
                # Reset customer RAG state
                self.customer_manager.update_rag_status(
                    customer_id, 
                    RAGStatus.NEVER_BUILT,
                    last_index_time=None,
                    total_indexed_documents=0,
                    total_indexed_chunks=0
                )
            
            # Clear cached instances
            RAGFactory.clear_cache(customer_id)
            
            return cleanup_successful
            
        except Exception as e:
            print(f"Error cleaning up RAG for customer {customer_id}: {e}")
            return False
    
    def get_customer_manager(self) -> CustomerManager:
        """Get the customer manager instance."""
        return self.customer_manager
    
    def list_customers_by_rag_status(self, rag_status: RAGStatus) -> List[str]:
        """
        List customers by their RAG status.
        
        Args:
            rag_status: RAG status to filter by
            
        Returns:
            List of customer IDs with the specified RAG status
        """
        matching_customers = []
        
        for customer_id in self.customer_manager.list_customers():
            try:
                state = self.customer_manager.get_customer_state(customer_id)
                if state.rag_status == rag_status:
                    matching_customers.append(customer_id)
            except Exception:
                continue
        
        return matching_customers


# Convenience functions for common operations
def create_rag_interface(base_data_path: Optional[Path] = None) -> MultiTenantRAGInterface:
    """Create a new multi-tenant RAG interface."""
    return MultiTenantRAGInterface(base_data_path)


def quick_query(customer_id: str, question: str, base_data_path: Optional[Path] = None) -> QueryResult:
    """Quick query function for single customer queries."""
    interface = create_rag_interface(base_data_path)
    return interface.query_customer(customer_id, question)


def quick_export_and_index(customer_id: str, space_keys: Optional[List[str]] = None, base_data_path: Optional[Path] = None) -> Dict[str, Any]:
    """Quick export and index function for single customer operations."""
    interface = create_rag_interface(base_data_path)
    return interface.export_and_index(customer_id, space_keys) 