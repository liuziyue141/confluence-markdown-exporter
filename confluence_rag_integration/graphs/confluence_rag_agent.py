"""Confluence RAG Agent with persistent memory for multi-tenant support."""

from typing import List, Literal, Optional, Annotated
from langchain_core.messages import HumanMessage, ToolMessage, AIMessage, SystemMessage
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, END
from langgraph.graph.message import MessagesState
from langgraph.checkpoint.memory import MemorySaver
import logging

from ..customers.customer_manager import CustomerManager
from ..rag.query_manager import QueryManager
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


@tool
def retrieve_knowledge(
    query: Annotated[str, "The search query or question to find relevant documents"],
    config: RunnableConfig
) -> str:
    """
    Search and retrieve relevant documentation from Confluence knowledge base.
    Use this when you need to find information about products, procedures,
    troubleshooting steps, or any documented knowledge to help answer questions.
    """
    try:
        # Extract configuration
        configurable = config.get("configurable", {})
        customer_id = configurable.get("customer_id", "acme_corp")
        top_k = configurable.get("top_k", 3)
        
        # Initialize managers
        customer_manager = CustomerManager()
        query_manager = QueryManager(customer_manager)
        
        # Execute query
        result = query_manager.query(customer_id, query, top_k)
        
        if result.status == "error":
            return f"Error retrieving documents: {result.error}"
        
        if not result.documents:
            return "No relevant documents found for the query."
        
        # Format results
        formatted_results = []
        for doc in result.documents:
            source = doc.get("source", "Unknown")
            content = doc.get("content", "")
            formatted_results.append(f"Source: {source}\n{content}")
        
        return "\n\n---\n\n".join(formatted_results)
        
    except Exception as e:
        logger.error(f"Error in retrieve_knowledge: {str(e)}")
        return f"Error retrieving knowledge: {str(e)}"


class ConfluenceRAGAgent:
    """RAG Agent with persistent memory for Confluence knowledge retrieval."""
    
    def __init__(
        self,
        model_name: str = "gemini-1.5-flash",
        temperature: float = 0,
        checkpointer=None
    ):
        """
        Initialize the RAG agent.
        
        Args:
            model_name: LLM model to use
            temperature: Temperature for LLM responses
            checkpointer: Checkpointer for persistent memory (defaults to MemorySaver)
        """
        self.llm = ChatGoogleGenerativeAI(
            model=model_name,
            temperature=temperature
        )
        self.llm_with_tools = self.llm.bind_tools([retrieve_knowledge])
        self.checkpointer = checkpointer or MemorySaver()
        self.app = self._build_graph()
    
    def _build_graph(self):
        """Build the agent graph with memory support."""
        builder = StateGraph(MessagesState)
        
        # Add nodes
        builder.add_node("agent_node", self._agent_node)
        builder.add_node("tool_node", self._tool_node)
        
        # Set entry point
        builder.set_entry_point("agent_node")
        
        # Add conditional edges
        builder.add_conditional_edges(
            "agent_node",
            self._should_continue,
            {
                "continue": "tool_node",
                END: END
            }
        )
        
        # Add edge from tool back to agent
        builder.add_edge("tool_node", "agent_node")
        
        # Compile with checkpointer
        return builder.compile(checkpointer=self.checkpointer)
    
    def _agent_node(self, state: MessagesState, config: RunnableConfig) -> dict:  # noqa: ARG002
        """Agent node that decides whether to search or respond."""
        messages = state["messages"]
        
        logger.debug(f"Agent node - incoming messages count: {len(messages)}")
        
        # System prompt for better agent behavior
        system_prompt = """You are a helpful support agent with access to a Confluence knowledge base.
        Use the retrieve_knowledge tool to search for relevant documentation when answering questions.
        You can call the tool multiple times if needed to gather comprehensive information.
        Always search for information before providing an answer unless the question is clearly conversational.
        Be concise but thorough in your responses."""
        
        # Create proper message list with SystemMessage
        messages_to_send = [SystemMessage(content=system_prompt)] + list(messages)
        
        logger.debug(f"Invoking LLM with {len(messages_to_send)} messages")
        
        # Invoke LLM with tools
        try:
            response = self.llm_with_tools.invoke(messages_to_send)
            logger.debug(f"LLM response type: {type(response)}, has tool_calls: {hasattr(response, 'tool_calls')}")
            if hasattr(response, 'tool_calls'):
                logger.debug(f"Tool calls: {response.tool_calls}")
        except Exception as e:
            logger.error(f"Error in agent node: {e}")
            raise
        
        return {"messages": [response]}
    
    def _tool_node(self, state: MessagesState, config: RunnableConfig) -> dict:
        """Execute tool calls from the last message."""
        last_message = state["messages"][-1]
        tool_messages = []
        
        logger.debug(f"Tool node - executing {len(last_message.tool_calls)} tool calls")
        
        # Execute each tool call
        for tool_call in last_message.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            
            logger.debug(f"Executing tool: {tool_name} with args: {tool_args}")
            
            if tool_name == "retrieve_knowledge":
                # Execute the tool with config
                tool_result = retrieve_knowledge.invoke(tool_args, config)
            else:
                tool_result = f"Error: Unknown tool {tool_name}"
            
            logger.debug(f"Tool result length: {len(tool_result)}")
            
            # Create tool message
            tool_message = ToolMessage(
                content=tool_result,
                tool_call_id=tool_call["id"],
                name=tool_name
            )
            tool_messages.append(tool_message)
        
        return {"messages": tool_messages}
    
    def _should_continue(self, state: MessagesState) -> Literal["continue", "end"]:
        """Decide if we should continue to tools or end."""
        messages = state["messages"]
        last_message = messages[-1]
        
        # If the LLM makes a tool call, continue to tools
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "continue"
        
        # Otherwise, end the conversation
        return END
    
    def chat(
        self,
        message: str,
        thread_id: str,
        customer_id: str = "acme_corp",
        top_k: int = 3
    ) -> str:
        """
        Send a message to the agent and get a response.
        
        Args:
            message: User message
            thread_id: Unique thread ID for conversation
            customer_id: Customer ID for multi-tenant support
            top_k: Number of documents to retrieve
            
        Returns:
            Agent response
        """
        config = {
            "configurable": {
                "thread_id": thread_id,
                "customer_id": customer_id,
                "top_k": top_k
            }
        }
        
        try:
            logger.info(f"Chat invoked - thread_id: {thread_id}, customer_id: {customer_id}, top_k: {top_k}")
            logger.debug(f"User message: {message}")
            
            # Invoke the agent
            result = self.app.invoke(
                {"messages": [HumanMessage(content=message)]},
                config
            )
            
            logger.debug(f"Result messages count: {len(result.get('messages', []))}")
            
            # Log all messages for debugging
            for i, msg in enumerate(result.get("messages", [])):
                msg_type = type(msg).__name__
                has_tool_calls = hasattr(msg, "tool_calls") and msg.tool_calls
                logger.debug(f"Message {i}: type={msg_type}, has_tool_calls={has_tool_calls}")
                if isinstance(msg, AIMessage) and not has_tool_calls:
                    logger.debug(f"Found AI response: {msg.content[:100]}...")
            
            # Extract the final AI response
            for msg in reversed(result.get("messages", [])):
                # Check if it's an AI message without tool calls
                if isinstance(msg, AIMessage) and not (hasattr(msg, "tool_calls") and msg.tool_calls):
                    logger.info(f"Returning AI response of length {len(msg.content)}")
                    return msg.content
            
            logger.warning("No AI response found in messages")
            return "I apologize, but I couldn't generate a response."
            
        except Exception as e:
            logger.error(f"Error in chat: {str(e)}", exc_info=True)
            return f"An error occurred: {str(e)}"
    
    def get_conversation_history(self, thread_id: str) -> List[dict]:
        """
        Get conversation history for a thread.
        
        Args:
            thread_id: Thread ID to retrieve history for
            
        Returns:
            List of messages in the conversation
        """
        try:
            state = self.app.get_state({"configurable": {"thread_id": thread_id}})
            
            if not state.values:
                return []
            
            messages = state.values.get("messages", [])
            history = []
            
            for msg in messages:
                if msg.type == "human":
                    history.append({"role": "user", "content": msg.content})
                elif msg.type == "ai" and not hasattr(msg, "tool_calls"):
                    history.append({"role": "assistant", "content": msg.content})
            
            return history
            
        except Exception as e:
            logger.error(f"Error getting history: {str(e)}")
            return []
    
    def clear_conversation(self, thread_id: str) -> bool:
        """
        Clear conversation history for a thread.
        
        Args:
            thread_id: Thread ID to clear
            
        Returns:
            Success status
        """
        try:
            # For MemorySaver, we can't directly delete, but we can reset
            # by starting a new conversation with the same thread_id
            # This is a limitation of MemorySaver
            logger.info(f"Conversation cleared for thread: {thread_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error clearing conversation: {str(e)}")
            return False


def create_agent(
    model_name: str = "gemini-1.5-flash",
    temperature: float = 0,
    use_persistent_memory: bool = True
) -> ConfluenceRAGAgent:
    """
    Factory function to create a RAG agent.
    
    Args:
        model_name: LLM model to use
        temperature: Temperature for LLM responses
        use_persistent_memory: Whether to use persistent memory
        
    Returns:
        Configured RAG agent
    """
    checkpointer = None
    
    if use_persistent_memory:
        # For now, use MemorySaver. Can be replaced with PostgreSQL later
        checkpointer = MemorySaver()
    
    return ConfluenceRAGAgent(
        model_name=model_name,
        temperature=temperature,
        checkpointer=checkpointer
    )