"""FastAPI application for Confluence RAG Agent."""

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import uuid
import logging
from pathlib import Path

from ..graphs.confluence_rag_agent import create_agent
from ..graphs.memory_manager import create_memory_manager
from ..customers.customer_manager import CustomerManager
from dotenv import load_dotenv

load_dotenv()


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Confluence RAG Agent API",
    description="API for multi-tenant Confluence knowledge retrieval with conversation memory",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify actual origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize components
memory_manager = create_memory_manager(use_postgresql=False)
agent = create_agent(use_persistent_memory=True)
agent.checkpointer = memory_manager.get_checkpointer()
customer_manager = CustomerManager()


# Request/Response models
class ChatRequest(BaseModel):
    """Chat request model."""
    message: str
    session_id: Optional[str] = None
    customer_id: str = "acme_corp"
    top_k: int = 3


class ChatResponse(BaseModel):
    """Chat response model."""
    response: str
    session_id: str
    thread_id: str


class SessionRequest(BaseModel):
    """Session creation request."""
    customer_id: str = "acme_corp"


class SessionInfo(BaseModel):
    """Session information."""
    session_id: str
    thread_id: str
    customer_id: str
    created_at: str
    message_count: int = 0


# API Endpoints
@app.get("/")
async def root():
    """Root endpoint - serve the frontend."""
    frontend_path = Path(__file__).parent / "frontend" / "index.html"
    if frontend_path.exists():
        return FileResponse(frontend_path)
    return {"message": "Confluence RAG Agent API", "docs": "/docs"}


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "Confluence RAG Agent"}


@app.get("/customers")
async def list_customers():
    """List available customers."""
    try:
        customers = customer_manager.list_customers()
        return {"customers": customers}
    except Exception as e:
        logger.error(f"Error listing customers: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat")
async def chat(request: ChatRequest) -> ChatResponse:
    """
    Send a message to the agent and get a response.
    """
    try:
        # Generate session ID if not provided
        if not request.session_id:
            request.session_id = str(uuid.uuid4())
        
        # Create thread ID
        thread_id = memory_manager.create_thread_id(
            request.customer_id,
            request.session_id
        )
        
        # Check if this is a new session
        session_info = memory_manager.session_manager.get_session(thread_id) if memory_manager.session_manager else None
        if not session_info:
            memory_manager.create_session(request.customer_id, request.session_id)
        
        # Send message to agent
        response = agent.chat(
            message=request.message,
            thread_id=thread_id,
            customer_id=request.customer_id,
            top_k=request.top_k
        )
        
        return ChatResponse(
            response=response,
            session_id=request.session_id,
            thread_id=thread_id
        )
        
    except Exception as e:
        logger.error(f"Error in chat endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/sessions")
async def create_session(request: SessionRequest) -> SessionInfo:
    """
    Create a new chat session.
    """
    try:
        session_id = str(uuid.uuid4())
        session_data = memory_manager.create_session(
            request.customer_id,
            session_id
        )
        
        return SessionInfo(
            session_id=session_id,
            thread_id=session_data["thread_id"],
            customer_id=request.customer_id,
            created_at=session_data["created_at"],
            message_count=0
        )
        
    except Exception as e:
        logger.error(f"Error creating session: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/sessions")
async def list_sessions(customer_id: Optional[str] = None) -> Dict[str, Any]:
    """
    List active sessions, optionally filtered by customer.
    """
    try:
        sessions = memory_manager.list_sessions(customer_id)
        
        # Convert to list format
        session_list = []
        for thread_id, session_data in sessions.items():
            customer_id, session_id = memory_manager.parse_thread_id(thread_id)
            session_list.append({
                "session_id": session_id,
                "thread_id": thread_id,
                "customer_id": customer_id,
                **session_data
            })
        
        return {"sessions": session_list}
        
    except Exception as e:
        logger.error(f"Error listing sessions: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/sessions/{session_id}/history")
async def get_session_history(session_id: str, customer_id: str = "acme_corp") -> Dict[str, Any]:
    """
    Get conversation history for a session.
    """
    try:
        thread_id = memory_manager.create_thread_id(customer_id, session_id)
        history = agent.get_conversation_history(thread_id)
        
        return {
            "session_id": session_id,
            "thread_id": thread_id,
            "history": history
        }
        
    except Exception as e:
        logger.error(f"Error getting history: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/sessions/{session_id}")
async def clear_session(session_id: str, customer_id: str = "acme_corp"):
    """
    Clear a session's conversation history.
    """
    try:
        thread_id = memory_manager.create_thread_id(customer_id, session_id)
        
        # Deactivate the session
        if memory_manager.session_manager:
            memory_manager.session_manager.deactivate_session(thread_id)
        
        # Clear conversation
        success = agent.clear_conversation(thread_id)
        
        if success:
            return {"message": "Session cleared successfully", "session_id": session_id}
        else:
            raise HTTPException(status_code=500, detail="Failed to clear session")
            
    except Exception as e:
        logger.error(f"Error clearing session: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# WebSocket for real-time chat
@app.websocket("/ws/{session_id}")
async def websocket_chat(websocket: WebSocket, session_id: str, customer_id: str = "acme_corp"):
    """
    WebSocket endpoint for real-time chat.
    """
    await websocket.accept()
    
    # Create thread ID
    thread_id = memory_manager.create_thread_id(customer_id, session_id)
    
    # Check/create session
    session_info = memory_manager.session_manager.get_session(thread_id) if memory_manager.session_manager else None
    if not session_info:
        memory_manager.create_session(customer_id, session_id)
    
    try:
        while True:
            # Receive message from client
            data = await websocket.receive_json()
            
            message = data.get("message", "")
            top_k = data.get("top_k", 3)
            
            if not message:
                continue
            
            # Send typing indicator
            await websocket.send_json({"type": "typing", "status": "start"})
            
            # Get response from agent
            response = agent.chat(
                message=message,
                thread_id=thread_id,
                customer_id=customer_id,
                top_k=top_k
            )
            
            # Send response
            await websocket.send_json({
                "type": "message",
                "response": response,
                "session_id": session_id
            })
            
            # Stop typing indicator
            await websocket.send_json({"type": "typing", "status": "stop"})
            
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for session: {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {str(e)}")
        await websocket.close()


# Mount static files for frontend
frontend_dir = Path(__file__).parent / "frontend"
if frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)