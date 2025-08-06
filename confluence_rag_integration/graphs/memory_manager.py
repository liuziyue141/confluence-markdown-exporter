"""Memory management for persistent conversation storage."""

import json
import os
from pathlib import Path
from typing import Dict, Any, Optional, Iterator
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from langgraph.checkpoint.base import BaseCheckpointSaver, Checkpoint, CheckpointTuple
from langgraph.checkpoint.memory import MemorySaver
import logging

logger = logging.getLogger(__name__)


@dataclass
class SessionInfo:
    """Information about a chat session."""
    thread_id: str
    customer_id: str
    created_at: str
    last_updated: str
    message_count: int
    active: bool = True


class PostgreSQLCheckpointer(BaseCheckpointSaver):
    """PostgreSQL-based checkpointer for persistent memory.
    
    Note: This is a placeholder implementation. In production, you would:
    1. Use SQLAlchemy or psycopg2 to connect to PostgreSQL
    2. Store checkpoints in a proper table structure
    3. Implement proper transaction handling
    """
    
    def __init__(self, connection_string: str):
        """Initialize with PostgreSQL connection string."""
        self.connection_string = connection_string
        logger.info("PostgreSQL checkpointer initialized (placeholder)")
        # In production: Initialize database connection here
    
    def put(self, config: dict, checkpoint: Checkpoint) -> dict:
        """Store a checkpoint."""
        # Placeholder: In production, store in PostgreSQL
        logger.debug(f"Storing checkpoint for config: {config}")
        return config
    
    def get_tuple(self, config: dict) -> Optional[CheckpointTuple]:
        """Retrieve a checkpoint tuple."""
        # Placeholder: In production, retrieve from PostgreSQL
        logger.debug(f"Retrieving checkpoint for config: {config}")
        return None
    
    def list(self, config: Optional[dict] = None) -> Iterator[CheckpointTuple]:
        """List checkpoints."""
        # Placeholder: In production, query PostgreSQL
        logger.debug(f"Listing checkpoints for config: {config}")
        return iter([])
    
    def get(self, config: dict) -> Optional[Checkpoint]:
        """Retrieve a checkpoint."""
        tuple_result = self.get_tuple(config)
        if tuple_result:
            return tuple_result.checkpoint
        return None


class FileSystemCheckpointer(MemorySaver):
    """File system-based checkpointer with session management.
    
    Extends MemorySaver to add session tracking and management.
    """
    
    def __init__(self, checkpoint_dir: str = "data/checkpoints"):
        """Initialize with checkpoint directory."""
        super().__init__()
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self.sessions_file = self.checkpoint_dir / "sessions.json"
        self._load_sessions()
    
    def _load_sessions(self):
        """Load session information from file."""
        if self.sessions_file.exists():
            with open(self.sessions_file, 'r') as f:
                data = json.load(f)
                self.sessions = {
                    k: SessionInfo(**v) for k, v in data.items()
                }
        else:
            self.sessions = {}
    
    def _save_sessions(self):
        """Save session information to file."""
        data = {k: asdict(v) for k, v in self.sessions.items()}
        with open(self.sessions_file, 'w') as f:
            json.dump(data, f, indent=2)
    
    def create_session(self, thread_id: str, customer_id: str) -> SessionInfo:
        """Create a new session."""
        now = datetime.now().isoformat()
        session = SessionInfo(
            thread_id=thread_id,
            customer_id=customer_id,
            created_at=now,
            last_updated=now,
            message_count=0,
            active=True
        )
        self.sessions[thread_id] = session
        self._save_sessions()
        return session
    
    def update_session(self, thread_id: str, message_count: int = None):
        """Update session information."""
        if thread_id in self.sessions:
            session = self.sessions[thread_id]
            session.last_updated = datetime.now().isoformat()
            if message_count is not None:
                session.message_count = message_count
            self._save_sessions()
    
    def get_session(self, thread_id: str) -> Optional[SessionInfo]:
        """Get session information."""
        return self.sessions.get(thread_id)
    
    def list_sessions(
        self,
        customer_id: Optional[str] = None,
        active_only: bool = True
    ) -> Dict[str, SessionInfo]:
        """List sessions, optionally filtered by customer and active status."""
        sessions = self.sessions
        
        if customer_id:
            sessions = {
                k: v for k, v in sessions.items()
                if v.customer_id == customer_id
            }
        
        if active_only:
            sessions = {
                k: v for k, v in sessions.items()
                if v.active
            }
        
        return sessions
    
    def deactivate_session(self, thread_id: str):
        """Mark a session as inactive."""
        if thread_id in self.sessions:
            self.sessions[thread_id].active = False
            self._save_sessions()
    
    def cleanup_old_sessions(self, days: int = 30):
        """Clean up sessions older than specified days."""
        cutoff = datetime.now() - timedelta(days=days)
        
        for thread_id, session in list(self.sessions.items()):
            last_updated = datetime.fromisoformat(session.last_updated)
            if last_updated < cutoff:
                logger.info(f"Cleaning up old session: {thread_id}")
                del self.sessions[thread_id]
        
        self._save_sessions()
    
    def put(self, config: dict, checkpoint: Checkpoint) -> dict:
        """Override to track session updates."""
        result = super().put(config, checkpoint)
        
        # Update session tracking
        thread_id = config.get("configurable", {}).get("thread_id")
        if thread_id:
            # Count messages in checkpoint
            message_count = 0
            if checkpoint and "channel_values" in checkpoint:
                messages = checkpoint["channel_values"].get("messages", [])
                message_count = len(messages)
            
            self.update_session(thread_id, message_count)
        
        return result


class MemoryManager:
    """High-level memory management interface."""
    
    def __init__(
        self,
        use_postgresql: bool = False,
        connection_string: Optional[str] = None,
        checkpoint_dir: str = "data/checkpoints"
    ):
        """
        Initialize memory manager.
        
        Args:
            use_postgresql: Whether to use PostgreSQL for storage
            connection_string: PostgreSQL connection string
            checkpoint_dir: Directory for file-based storage
        """
        if use_postgresql and connection_string:
            self.checkpointer = PostgreSQLCheckpointer(connection_string)
            self.session_manager = None  # PostgreSQL handles sessions
        else:
            self.checkpointer = FileSystemCheckpointer(checkpoint_dir)
            self.session_manager = self.checkpointer
    
    def create_thread_id(self, customer_id: str, session_id: str) -> str:
        """
        Create a unique thread ID.
        
        Args:
            customer_id: Customer identifier
            session_id: Session identifier
            
        Returns:
            Unique thread ID
        """
        return f"{customer_id}::{session_id}"
    
    def parse_thread_id(self, thread_id: str) -> tuple[str, str]:
        """
        Parse thread ID into components.
        
        Args:
            thread_id: Thread ID to parse
            
        Returns:
            Tuple of (customer_id, session_id)
        """
        if "::" in thread_id:
            parts = thread_id.split("::", 1)
            return parts[0], parts[1]
        # Fallback for old format with underscore
        parts = thread_id.rsplit("_", 1)
        if len(parts) == 2:
            return parts[0], parts[1]
        return "unknown", thread_id
    
    def create_session(
        self,
        customer_id: str,
        session_id: str
    ) -> Dict[str, Any]:
        """
        Create a new chat session.
        
        Args:
            customer_id: Customer identifier
            session_id: Session identifier
            
        Returns:
            Session information
        """
        thread_id = self.create_thread_id(customer_id, session_id)
        
        if self.session_manager:
            session = self.session_manager.create_session(thread_id, customer_id)
            return asdict(session)
        
        return {
            "thread_id": thread_id,
            "customer_id": customer_id,
            "created_at": datetime.now().isoformat()
        }
    
    def list_sessions(
        self,
        customer_id: Optional[str] = None
    ) -> Dict[str, Dict[str, Any]]:
        """
        List active sessions.
        
        Args:
            customer_id: Optional customer filter
            
        Returns:
            Dictionary of sessions
        """
        if self.session_manager:
            sessions = self.session_manager.list_sessions(customer_id)
            return {k: asdict(v) for k, v in sessions.items()}
        
        return {}
    
    def get_checkpointer(self):
        """Get the underlying checkpointer."""
        return self.checkpointer
    
    def cleanup_old_sessions(self, days: int = 30):
        """Clean up old sessions."""
        if self.session_manager and hasattr(self.session_manager, 'cleanup_old_sessions'):
            self.session_manager.cleanup_old_sessions(days)


def create_memory_manager(
    use_postgresql: bool = False,
    connection_string: Optional[str] = None
) -> MemoryManager:
    """
    Factory function to create a memory manager.
    
    Args:
        use_postgresql: Whether to use PostgreSQL
        connection_string: PostgreSQL connection string
        
    Returns:
        Configured memory manager
    """
    # Get connection from environment if not provided
    if use_postgresql and not connection_string:
        connection_string = os.getenv("POSTGRES_CONNECTION_STRING")
    
    return MemoryManager(
        use_postgresql=use_postgresql,
        connection_string=connection_string
    )