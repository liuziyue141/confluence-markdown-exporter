"""Customer management system for multi-tenant Confluence RAG integration."""

import json
import os
import yaml
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Union, Any

from ..shared.models import (
    CustomerConfig,
    CustomerState,
    ExportStatus,
    ConfluenceAuthConfig,
    ExportConfig,
    RAGConfig,
    RAGStatus,
    SpaceConfig,
    generate_collection_name,
)
from ..shared.utils import (
    sanitize_customer_id,
    ensure_customer_directory,
    get_customer_config_path,
    create_customer_id_from_url,
)


class CustomerManager:
    """
    Central manager for customer configurations and operations.
    
    Handles customer lifecycle, configuration management, and state tracking.
    """
    
    def __init__(self, base_data_path: Optional[Path] = None):
        """
        Initialize the customer manager.
        
        Args:
            base_data_path: Base directory for all customer data (defaults to ./data/customers)
        """
        self.base_data_path = base_data_path or Path("./data/customers")
        self.base_data_path.mkdir(parents=True, exist_ok=True)
        
        # Cache for loaded customer configurations
        self._customer_cache: Dict[str, CustomerConfig] = {}
        self._state_cache: Dict[str, CustomerState] = {}
        
    def create_customer(
        self,
        customer_id: str,
        name: str,
        confluence_url: str,
        username: str,
        api_token: str,
        spaces: Optional[List[Dict]] = None,
        **kwargs
    ) -> CustomerConfig:
        """
        Create a new customer configuration.
        
        Args:
            customer_id: Unique customer identifier
            name: Customer display name
            confluence_url: Confluence instance URL
            username: Confluence username/email
            api_token: Confluence API token
            spaces: List of space configurations
            **kwargs: Additional configuration parameters
            
        Returns:
            Created customer configuration
            
        Raises:
            ValueError: If customer already exists or configuration is invalid
        """
        customer_id = sanitize_customer_id(customer_id)
        
        if self.customer_exists(customer_id):
            raise ValueError(f"Customer '{customer_id}' already exists")
        
        # Create customer directory structure
        customer_path = ensure_customer_directory(customer_id, self.base_data_path)
        
        # Set up default paths
        export_path = customer_path / "exports"
        vector_store_path = customer_path / "vector_store"
        
        # Create configuration
        config = CustomerConfig(
            customer_id=customer_id,
            name=name,
            confluence=ConfluenceAuthConfig(
                url=confluence_url,
                username=username,
                api_token=api_token,
            ),
            spaces=[SpaceConfig(**space) for space in (spaces or [])],
            export=ExportConfig(
                output_path=export_path,
                **kwargs.get('export', {})
            ),
            rag=RAGConfig(
                vector_store_path=vector_store_path,
                collection_name=generate_collection_name(customer_id),
                **kwargs.get('rag', {})
            ),
        )
        
        # Save configuration
        self.save_customer_config(config)
        
        # Initialize customer state
        state = CustomerState(
            customer_id=customer_id,
            data_path=customer_path,
            config_path=get_customer_config_path(customer_id, self.base_data_path),
            rag_collection_name=generate_collection_name(customer_id),
        )
        self.save_customer_state(state)
        
        # Cache the configuration
        self._customer_cache[customer_id] = config
        self._state_cache[customer_id] = state
        
        return config
    
    def load_customer(self, customer_id: str) -> CustomerConfig:
        """
        Load customer configuration from storage.
        
        Args:
            customer_id: Customer identifier
            
        Returns:
            Customer configuration
            
        Raises:
            ValueError: If customer doesn't exist
        """
        customer_id = sanitize_customer_id(customer_id)
        
        # Check cache first
        if customer_id in self._customer_cache:
            return self._customer_cache[customer_id]
        
        config_path = get_customer_config_path(customer_id, self.base_data_path)
        
        if not config_path.exists():
            raise ValueError(f"Customer '{customer_id}' not found")
        
        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = yaml.safe_load(f)
        
        # Convert string paths back to Path objects and handle datetime strings
        def convert_from_yaml(obj):
            if isinstance(obj, dict):
                converted = {}
                for k, v in obj.items():
                    # Only convert specific path fields, not template strings
                    if k in ['output_path', 'vector_store_path', 'data_path', 'config_path'] and isinstance(v, str):
                        converted[k] = Path(v)
                    elif k in ['created_at', 'updated_at'] and isinstance(v, str):
                        from datetime import datetime
                        converted[k] = datetime.fromisoformat(v)
                    else:
                        converted[k] = convert_from_yaml(v)
                return converted
            elif isinstance(obj, list):
                return [convert_from_yaml(item) for item in obj]
            else:
                return obj
        
        processed_data = convert_from_yaml(config_data)
        config = CustomerConfig(**processed_data)
        
        # Cache the configuration
        self._customer_cache[customer_id] = config
        
        return config
    
    def save_customer_config(self, config: CustomerConfig) -> None:
        """
        Save customer configuration to storage.
        
        Args:
            config: Customer configuration to save
        """
        config.update_timestamp()
        config_path = get_customer_config_path(config.customer_id, self.base_data_path)
        
        # Convert to dict and handle special types
        config_data = config.dict()
        
        # Convert paths and special types to strings for YAML serialization
        def convert_paths(obj):
            if isinstance(obj, dict):
                return {k: convert_paths(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_paths(item) for item in obj]
            elif isinstance(obj, Path):
                return str(obj)
            elif hasattr(obj, 'get_secret_value'):  # SecretStr
                return obj.get_secret_value()
            elif hasattr(obj, '__str__') and type(obj).__name__ in ['AnyHttpUrl', 'HttpUrl']:  # Pydantic URLs
                return str(obj)
            elif hasattr(obj, 'isoformat'):  # datetime objects
                return obj.isoformat()
            else:
                return obj
        
        serializable_data = convert_paths(config_data)
        
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(serializable_data, f, default_flow_style=False, allow_unicode=True)
        
        # Update cache
        self._customer_cache[config.customer_id] = config
    
    def get_customer_state(self, customer_id: str) -> CustomerState:
        """
        Get current state of a customer.
        
        Args:
            customer_id: Customer identifier
            
        Returns:
            Customer state
        """
        customer_id = sanitize_customer_id(customer_id)
        
        # Check cache first
        if customer_id in self._state_cache:
            return self._state_cache[customer_id]
        
        customer_path = ensure_customer_directory(customer_id, self.base_data_path)
        state_path = customer_path / "state.json"
        
        if state_path.exists():
            with open(state_path, 'r', encoding='utf-8') as f:
                state_data = json.load(f)
            
            # Convert string paths back to Path objects
            if 'data_path' in state_data:
                state_data['data_path'] = Path(state_data['data_path'])
            if 'config_path' in state_data:
                state_data['config_path'] = Path(state_data['config_path'])
            
            state = CustomerState(**state_data)
        else:
            # Create default state
            state = CustomerState(
                customer_id=customer_id,
                data_path=customer_path,
                config_path=get_customer_config_path(customer_id, self.base_data_path),
            )
        
        # Cache the state
        self._state_cache[customer_id] = state
        
        return state
    
    def save_customer_state(self, state: CustomerState) -> None:
        """
        Save customer state to storage.
        
        Args:
            state: Customer state to save
        """
        customer_path = ensure_customer_directory(state.customer_id, self.base_data_path)
        state_path = customer_path / "state.json"
        
        # Convert to dict and handle special types
        state_data = state.dict()
        
        # Convert paths to strings for JSON serialization
        if 'data_path' in state_data:
            state_data['data_path'] = str(state_data['data_path'])
        if 'config_path' in state_data:
            state_data['config_path'] = str(state_data['config_path'])
        
        with open(state_path, 'w', encoding='utf-8') as f:
            json.dump(state_data, f, indent=2, default=str)
        
        # Update cache
        self._state_cache[state.customer_id] = state
    
    def list_customers(self) -> List[str]:
        """
        List all customer IDs.
        
        Returns:
            List of customer identifiers
        """
        customers = []
        
        if not self.base_data_path.exists():
            return customers
        
        for item in self.base_data_path.iterdir():
            if item.is_dir():
                config_path = item / "config.yaml"
                if config_path.exists():
                    customers.append(item.name)
        
        return sorted(customers)
    
    def customer_exists(self, customer_id: str) -> bool:
        """
        Check if a customer exists.
        
        Args:
            customer_id: Customer identifier
            
        Returns:
            True if customer exists, False otherwise
        """
        customer_id = sanitize_customer_id(customer_id)
        config_path = get_customer_config_path(customer_id, self.base_data_path)
        return config_path.exists()
    
    def delete_customer(self, customer_id: str, confirm: bool = False) -> bool:
        """
        Delete a customer and all associated data.
        
        Args:
            customer_id: Customer identifier
            confirm: Confirmation flag to prevent accidental deletion
            
        Returns:
            True if deleted successfully, False otherwise
            
        Raises:
            ValueError: If customer doesn't exist or confirmation not provided
        """
        if not confirm:
            raise ValueError("Deletion requires explicit confirmation (confirm=True)")
        
        customer_id = sanitize_customer_id(customer_id)
        
        if not self.customer_exists(customer_id):
            raise ValueError(f"Customer '{customer_id}' not found")
        
        customer_path = ensure_customer_directory(customer_id, self.base_data_path)
        
        try:
            import shutil
            shutil.rmtree(customer_path)
            
            # Remove from cache
            self._customer_cache.pop(customer_id, None)
            self._state_cache.pop(customer_id, None)
            
            return True
        except Exception as e:
            print(f"Error deleting customer '{customer_id}': {e}")
            return False
    
    def update_customer_export_status(self, customer_id: str, status: ExportStatus) -> None:
        """
        Update customer's export status.
        
        Args:
            customer_id: Customer identifier
            status: New export status
        """
        state = self.get_customer_state(customer_id)
        state.export_status = status
        
        if status == ExportStatus.COMPLETED:
            state.last_export = datetime.utcnow()
        
        self.save_customer_state(state)
    
    def update_customer_index_status(self, customer_id: str, total_documents: int, total_chunks: int) -> None:
        """
        Update customer's indexing status.
        
        Args:
            customer_id: Customer identifier
            total_documents: Total number of documents indexed
            total_chunks: Total number of chunks created
        """
        state = self.get_customer_state(customer_id)
        state.total_documents = total_documents
        state.total_chunks = total_chunks
        state.last_index = datetime.utcnow()
        
        self.save_customer_state(state)
    
    def get_customer_summary(self) -> Dict[str, Dict]:
        """
        Get a summary of all customers and their status.
        
        Returns:
            Dictionary mapping customer IDs to their summary information
        """
        summary = {}
        
        for customer_id in self.list_customers():
            try:
                config = self.load_customer(customer_id)
                state = self.get_customer_state(customer_id)
                
                summary[customer_id] = {
                    'name': config.name,
                    'confluence_url': str(config.confluence.url),
                    'spaces': len(config.spaces),
                    'active': config.active,
                    'export_status': state.export_status.value,
                    'last_export': state.last_export.isoformat() if state.last_export else None,
                    'last_index': state.last_index.isoformat() if state.last_index else None,
                    'total_documents': state.total_documents,
                    'ready_for_queries': state.is_ready_for_queries,
                }
            except Exception as e:
                summary[customer_id] = {'error': str(e)}
        
        return summary
    
    def update_rag_status(self, customer_id: str, rag_status: RAGStatus, **kwargs) -> bool:
        """
        Update RAG status for a customer.
        
        Args:
            customer_id: Customer identifier
            rag_status: New RAG status
            **kwargs: Additional RAG state fields to update
            
        Returns:
            True if update successful, False otherwise
        """
        try:
            state = self.get_customer_state(customer_id)
            
            # Update RAG status
            state.rag_status = rag_status
            
            # Update additional fields if provided
            if 'last_index_time' in kwargs:
                state.last_index_time = kwargs['last_index_time']
            if 'total_indexed_documents' in kwargs:
                state.total_indexed_documents = kwargs['total_indexed_documents']
            if 'total_indexed_chunks' in kwargs:
                state.total_indexed_chunks = kwargs['total_indexed_chunks']
            
            # Save updated state
            self.save_customer_state(state)
            
            # Update cache
            self._state_cache[customer_id] = state
            
            return True
        except Exception as e:
            print(f"Error updating RAG status for customer {customer_id}: {e}")
            return False
    
    def update_rag_statistics(self, customer_id: str, documents_processed: int, chunks_created: int, index_time: datetime = None) -> bool:
        """
        Update RAG indexing statistics for a customer.
        
        Args:
            customer_id: Customer identifier
            documents_processed: Number of documents processed
            chunks_created: Number of chunks created
            index_time: Indexing completion time (defaults to now)
            
        Returns:
            True if update successful, False otherwise
        """
        index_time = index_time or datetime.utcnow()
        
        return self.update_rag_status(
            customer_id,
            RAGStatus.READY,
            last_index_time=index_time,
            total_indexed_documents=documents_processed,
            total_indexed_chunks=chunks_created
        )
    
    def mark_rag_building(self, customer_id: str) -> bool:
        """
        Mark customer's RAG as currently building.
        
        Args:
            customer_id: Customer identifier
            
        Returns:
            True if update successful, False otherwise
        """
        return self.update_rag_status(customer_id, RAGStatus.BUILDING)
    
    def mark_rag_failed(self, customer_id: str, error_message: str = None) -> bool:
        """
        Mark customer's RAG as failed.
        
        Args:
            customer_id: Customer identifier
            error_message: Optional error message
            
        Returns:
            True if update successful, False otherwise
        """
        # For now, just update the status. Could extend to store error messages.
        return self.update_rag_status(customer_id, RAGStatus.FAILED)
    
    def validate_rag_config(self, customer_id: str) -> Dict[str, Any]:
        """
        Validate customer's RAG configuration.
        
        Args:
            customer_id: Customer identifier
            
        Returns:
            Dict with validation results
        """
        try:
            config = self.load_customer(customer_id)
            rag_config = config.rag
            
            validation_results = {
                "customer_id": customer_id,
                "collection_name": rag_config.collection_name,
                "vector_store_path_exists": rag_config.vector_store_path.exists(),
                "vector_store_path_writable": True,  # Would need to test this
                "connection_string_valid": bool(rag_config.connection_string),
                "embedding_model": rag_config.embedding_model,
                "chunk_size": rag_config.chunk_size,
                "parent_retriever_enabled": rag_config.enable_parent_retriever,
                "valid": True
            }
            
            # Try to create the vector store path if it doesn't exist
            try:
                rag_config.vector_store_path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                validation_results["vector_store_path_writable"] = False
                validation_results["vector_store_error"] = str(e)
                validation_results["valid"] = False
            
            return validation_results
            
        except Exception as e:
            return {
                "customer_id": customer_id,
                "valid": False,
                "error": str(e)
            }
    
    def create_from_url(self, confluence_url: str, username: str, api_token: str, customer_name: Optional[str] = None) -> CustomerConfig:
        """
        Create a customer configuration from a Confluence URL.
        
        Args:
            confluence_url: Confluence instance URL
            username: Confluence username/email
            api_token: Confluence API token
            customer_name: Optional customer name (derived from URL if not provided)
            
        Returns:
            Created customer configuration
        """
        customer_id = create_customer_id_from_url(confluence_url)
        
        if customer_name is None:
            customer_name = customer_id.replace('_', ' ').title()
        
        return self.create_customer(
            customer_id=customer_id,
            name=customer_name,
            confluence_url=confluence_url,
            username=username,
            api_token=api_token,
        ) 