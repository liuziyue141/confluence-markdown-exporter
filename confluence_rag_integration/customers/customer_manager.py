"""Simplified customer management for multi-tenant Confluence RAG integration."""

import json
import yaml
import os
import re
from pathlib import Path
from typing import Dict, Any

from ..shared.models import CustomerConfig, CustomerState


class CustomerManager:
    """Simple customer manager that only handles config and state management."""
    
    def __init__(self, base_path: Path = None):
        self.base_path = base_path or Path("data/customers")
        self.base_path.mkdir(parents=True, exist_ok=True)
    
    def _expand_env_vars(self, data: Any) -> Any:
        """Recursively expand environment variables in config data."""
        if isinstance(data, dict):
            return {key: self._expand_env_vars(value) for key, value in data.items()}
        elif isinstance(data, list):
            return [self._expand_env_vars(item) for item in data]
        elif isinstance(data, str):
            # Replace ${VAR_NAME} with environment variable value
            return re.sub(r'\$\{([^}]+)\}', lambda m: os.getenv(m.group(1), m.group(0)), data)
        else:
            return data
    
    def create_customer(self, config_file: Path) -> CustomerConfig:
        """Create customer from config file and save to customer directory."""
        with open(config_file, 'r') as f:
            config_data = yaml.safe_load(f)
        
        # Expand environment variables
        config_data = self._expand_env_vars(config_data)
        config = CustomerConfig(**config_data)
        
        # Create customer directory
        customer_dir = self.base_path / config.customer_id
        customer_dir.mkdir(parents=True, exist_ok=True)
        
        # Save config to customer directory
        customer_config_path = customer_dir / "config.yaml"
        with open(customer_config_path, 'w') as f:
            yaml.dump(config_data, f, default_flow_style=False)
        
        # Create empty state
        initial_state = CustomerState(customer_id=config.customer_id)
        state_path = customer_dir / "state.json"
        with open(state_path, 'w') as f:
            json.dump(initial_state.__dict__, f, indent=2, default=str)
        
        return config
    
    def load_customer(self, customer_id: str) -> CustomerConfig:
        """Load customer config from customer directory."""
        config_path = self.base_path / customer_id / "config.yaml"
        if not config_path.exists():
            raise ValueError(f"Customer {customer_id} not found")
        
        with open(config_path, 'r') as f:
            config_data = yaml.safe_load(f)
        
        # Expand environment variables
        config_data = self._expand_env_vars(config_data)
        return CustomerConfig(**config_data)
    
    def get_state(self, customer_id: str) -> CustomerState:
        """Load customer state from state.json."""
        state_path = self.base_path / customer_id / "state.json"
        if not state_path.exists():
            # Create default state if doesn't exist
            state = CustomerState(customer_id=customer_id)
            with open(state_path, 'w') as f:
                json.dump(state.__dict__, f, indent=2, default=str)
            return state
        
        with open(state_path, 'r') as f:
            state_data = json.load(f)
        
        return CustomerState(**state_data)
    
    def update_export_state(self, customer_id: str, result: Dict[str, Any]) -> None:
        """Update export state in state.json."""
        state = self.get_state(customer_id)
        state.last_export = result
        
        state_path = self.base_path / customer_id / "state.json"
        with open(state_path, 'w') as f:
            json.dump(state.__dict__, f, indent=2, default=str)
    
    def update_index_state(self, customer_id: str, result: Dict[str, Any]) -> None:
        """Update index state in state.json."""
        state = self.get_state(customer_id)
        state.last_index = result
        
        # Update RAG status based on result
        if result.get('status') == 'success':
            state.rag_status = 'ready'
        elif result.get('status') == 'failed':
            state.rag_status = 'failed'
        else:
            state.rag_status = 'building'
        
        state_path = self.base_path / customer_id / "state.json"
        with open(state_path, 'w') as f:
            json.dump(state.__dict__, f, indent=2, default=str)