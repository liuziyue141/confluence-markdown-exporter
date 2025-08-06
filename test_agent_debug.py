#!/usr/bin/env python
"""Debug test script for Confluence RAG Agent."""

import os
import sys
import logging
from dotenv import load_dotenv
from pathlib import Path

# Set up comprehensive logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger()

# Load environment variables
load_dotenv()

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

def test_basic_llm():
    """Test basic LLM functionality."""
    print("\n=== Testing Basic LLM ===")
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        
        api_key = os.getenv('GOOGLE_API_KEY')
        print(f"✓ API key loaded: {api_key[:10] if api_key else 'NOT FOUND'}...")
        
        llm = ChatGoogleGenerativeAI(model='gemini-1.5-flash', temperature=0)
        response = llm.invoke("Say 'Hello, I am working!'")
        print(f"✓ LLM response: {response.content}")
        return True
    except Exception as e:
        print(f"✗ LLM test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_agent_creation():
    """Test agent creation."""
    print("\n=== Testing Agent Creation ===")
    try:
        from confluence_rag_integration.graphs.confluence_rag_agent import create_agent
        from confluence_rag_integration.graphs.memory_manager import create_memory_manager
        
        memory_manager = create_memory_manager(use_postgresql=False)
        print("✓ Memory manager created")
        
        agent = create_agent(use_persistent_memory=True)
        agent.checkpointer = memory_manager.get_checkpointer()
        print("✓ Agent created")
        
        return agent, memory_manager
    except Exception as e:
        print(f"✗ Agent creation failed: {e}")
        import traceback
        traceback.print_exc()
        return None, None

def test_simple_chat(agent, memory_manager):
    """Test simple chat without tool usage."""
    print("\n=== Testing Simple Chat (No Tools) ===")
    try:
        thread_id = memory_manager.create_thread_id("test_customer", "test_session_1")
        print(f"Thread ID: {thread_id}")
        
        response = agent.chat(
            message="Just say hello, don't search for anything",
            thread_id=thread_id,
            customer_id="test_customer",
            top_k=3
        )
        
        print(f"✓ Response: {response}")
        return True
    except Exception as e:
        print(f"✗ Simple chat failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_chat_with_search(agent, memory_manager):
    """Test chat with tool usage."""
    print("\n=== Testing Chat with Search (With Tools) ===")
    try:
        thread_id = memory_manager.create_thread_id("acme_corp", "test_session_2")
        print(f"Thread ID: {thread_id}")
        
        response = agent.chat(
            message="How do I reset my password?",
            thread_id=thread_id,
            customer_id="acme_corp",
            top_k=3
        )
        
        print(f"✓ Response length: {len(response)}")
        print(f"✓ Response preview: {response[:200]}...")
        return True
    except Exception as e:
        print(f"✗ Chat with search failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_conversation_history(agent, memory_manager):
    """Test conversation history."""
    print("\n=== Testing Conversation History ===")
    try:
        thread_id = memory_manager.create_thread_id("test_customer", "test_session_3")
        print(f"Thread ID: {thread_id}")
        
        # First message
        response1 = agent.chat(
            message="Remember my name is Bob",
            thread_id=thread_id,
            customer_id="test_customer",
            top_k=3
        )
        print(f"✓ First response: {response1[:100]}...")
        
        # Second message  
        response2 = agent.chat(
            message="What is my name?",
            thread_id=thread_id,
            customer_id="test_customer",
            top_k=3
        )
        print(f"✓ Second response: {response2[:100]}...")
        
        # Get history
        history = agent.get_conversation_history(thread_id)
        print(f"✓ Conversation history: {len(history)} messages")
        for i, msg in enumerate(history):
            print(f"  {i+1}. {msg['role']}: {msg['content'][:50]}...")
        
        return True
    except Exception as e:
        print(f"✗ Conversation history test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main test function."""
    print("=" * 60)
    print("Confluence RAG Agent Debug Test")
    print("=" * 60)
    
    # Test basic LLM
    if not test_basic_llm():
        print("\n❌ Basic LLM test failed. Check your GOOGLE_API_KEY.")
        return 1
    
    # Create agent
    agent, memory_manager = test_agent_creation()
    if not agent:
        print("\n❌ Agent creation failed.")
        return 1
    
    # Test simple chat
    if not test_simple_chat(agent, memory_manager):
        print("\n❌ Simple chat test failed.")
        return 1
    
    # Test chat with search
    if not test_chat_with_search(agent, memory_manager):
        print("\n❌ Chat with search test failed.")
        # Continue anyway to test history
    
    # Test conversation history
    if not test_conversation_history(agent, memory_manager):
        print("\n❌ Conversation history test failed.")
        return 1
    
    print("\n" + "=" * 60)
    print("✅ All tests completed!")
    print("=" * 60)
    return 0

if __name__ == "__main__":
    sys.exit(main())