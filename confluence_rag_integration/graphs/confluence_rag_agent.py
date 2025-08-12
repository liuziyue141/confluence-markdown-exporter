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
from typing import Union
from pathlib import Path
import re
from typing import Tuple

load_dotenv()

logger = logging.getLogger(__name__)



@tool
def get_full_document(
    document_title: Annotated[str, "The exact document title from search results - pay attention to titles as they indicate specific problems the article solves"],
    config: RunnableConfig,
) -> str:
    """
    Retrieve the complete content of a specific document.
    Use this when:
    - The article title strongly matches the user's issue but you need more context
    - The article title is referenced in the search results, and you need more context
    - You need complete procedures or configuration details  
    - The user is confused about a previous solution
    - Following up on a solution that needs more context
    The document_title should match exactly what was shown in the search results.
    """
    try:
        configurable = config.get("configurable", {})
        customer_id = configurable.get("customer_id", "acme_corp")
        
        # Get customer's export directory
        # customer_manager = CustomerManager()
        # customer = customer_manager.get_customer(customer_id)
        # if not customer:
        #     return f"Customer {customer_id} not found"
        
        # temporary solution for testing
        root_directory = "/Users/lindalee/desktop/confluence-markdown-exporter/data/customers/acme_corp/exports"
        
        # Try to find the file
        result = find_kb_file_simple(document_title, root_directory)
        
        if result:
            file_path, content = result
            
            return f"""### Complete Document Retrieved
**Title:** {document_title}
**File Path:** {file_path}
**Full Content ({len(content)} characters):**

{content}"""
        else:
            return f"Could not retrieve full document for: '{document_title}'. Please use the exact title from the search results."
            
    except Exception as e:
        logger.error(f"Error in get_full_document: {str(e)}")
        return f"Error retrieving full document: {str(e)}"


def get_file_content(source: Union[str, Path], encoding: str = 'utf-8') -> Optional[str]:
    """Read and return the content of a file given its path."""
    try:
        file_path = Path(source)
        
        if not file_path.exists():
            logger.debug(f"File not found: {source}")
            return None
        
        if not file_path.is_file():
            logger.debug(f"Path is not a file: {source}")
            return None
        
        with open(file_path, 'r', encoding=encoding) as f:
            content = f.read()
        
        logger.debug(f"Successfully read file: {file_path.name} ({len(content):,} characters)")
        return content
    except Exception as e:
        logger.error(f"Error reading file {source}: {e}")
        return None


def find_kb_file_simple(search_term: str, root_directory: Union[str, Path]) -> Optional[Tuple[str, str]]:
    """Find a KB file by search term in the given directory."""
    root_path = Path(root_directory)
    
    if not root_path.exists() or not root_path.is_dir():
        logger.error(f"Invalid directory: {root_directory}")
        return None
    
    # Clean the search term
    clean_term = search_term.strip()
    
    # Try exact match first
    matching_files = list(root_path.rglob(f'*{clean_term}*.md'))
    
    # If no exact match, try with simplified term
    if not matching_files:
        # Remove file extensions if present
        simplified_term = re.sub(r'\.md$', '', clean_term, flags=re.IGNORECASE)
        # Remove special characters but keep spaces
        simplified_term = re.sub(r'[^\w\s-]', '', simplified_term).strip()
        if simplified_term and simplified_term != clean_term:
            matching_files = list(root_path.rglob(f'*{simplified_term}*.md'))
    
    if matching_files:
        # Return the first match
        file_path = matching_files[0]
        content = get_file_content(file_path)
        if content:
            logger.info(f"Found document: {file_path}")
            return (str(file_path), content)
    
    logger.warning(f"No document found for search term: {search_term}")
    return None



@tool
def retrieve_knowledge(
    query: Annotated[str, "The search query or question to find relevant documents"],
    config: RunnableConfig,
    search_mode: Annotated[str, "Search mode: 'initial' for first exploration (returns more results with snippets), 'focused' for specific searches"] = "initial",
) -> str:
    """
    Search and retrieve relevant documentation from Confluence knowledge base.
    Use 'initial' mode for first search, 'focused' for follow-up specific searches.
    """

    try:
        # Extract configuration
        configurable = config.get("configurable", {})
        customer_id = configurable.get("customer_id", "acme_corp")
        if search_mode == "initial":
            top_k = 5  # Get more results for initial exploration
        else:
            top_k = 3


        # Initialize managers
        customer_manager = CustomerManager()
        query_manager = QueryManager(customer_manager)

        # Execute query
        result = query_manager.query(customer_id, query, top_k)

        if result.status == "error":
            return f"Error retrieving documents: {result.error}"

        if not result.documents:
            return "No relevant documents found for the query."

        # Format results with rich metadata
        formatted_results = []
        for i, doc in enumerate(result.documents, 1):
            # Extract all available metadata
            doc_metadata = doc.get("metadata", {})
            title = doc_metadata.get("title", "Untitled")
            url = doc_metadata.get("url")
            breadcrumb = doc_metadata.get("breadcrumb")
            tags = doc_metadata.get("tags", [])
            content = doc.get("content", "")

            # Build formatted result with metadata
            result_parts = [f"### Result {i}: {title}"]

            # Add breadcrumb if available
            if breadcrumb and breadcrumb != "Uncategorized":
                result_parts.append(f"**Navigation:** {breadcrumb}")

            # Add URL if available
            if url:
                result_parts.append(f"**URL:** {url}")

            # Add tags if available
            if tags:
                tags_str = ", ".join(tags) if isinstance(tags, list) else str(tags)
                result_parts.append(f"**Tags:** {tags_str}")

            # Add content
            result_parts.append(f"\n**Content:**\n{content}")

            formatted_results.append("\n".join(result_parts))

        return "\n\n---\n\n".join(formatted_results)

    except Exception as e:
        logger.error(f"Error in retrieve_knowledge: {str(e)}")
        return f"Error retrieving knowledge: {str(e)}"


class ConfluenceRAGAgent:
    """RAG Agent with persistent memory for Confluence knowledge retrieval."""

    def __init__(
        self, model_name: str = "gemini-2.5-flash", temperature: float = 0, checkpointer=None
    ):
        """
        Initialize the RAG agent.

        Args:
            model_name: LLM model to use
            temperature: Temperature for LLM responses
            checkpointer: Checkpointer for persistent memory (defaults to MemorySaver)
        """
        self.llm = ChatGoogleGenerativeAI(model=model_name, temperature=temperature)
        self.llm_with_tools = self.llm.bind_tools([retrieve_knowledge, get_full_document])
        self.checkpointer = checkpointer or MemorySaver()
        self.system_prompt = """You are a technical support expert with access to a comprehensive Confluence knowledge base.

**YOUR APPROACH:**

**IMPORTANT: Always search the knowledge base FIRST before responding to the user's technical question. This ensures your responses are grounded in actual documentation and helps you ask better follow-up questions.**


1. **Start with Search**:
   - Begin with an 'initial' mode search using terms from the user's query
   - This gives you 5 documents with content snippets to assess the situation

2. **After Initial Search, Decide**:
   - **If you can answer confidently** → Provide a clear, actionable solution
   - **If you need clarification** → Ask specific questions to narrow down the issue
   - **If you need more context** → Use get_full_document for promising articles

3. **Using Full Documents**:
   - Pay close attention to article titles - they usually indicate the specific problem the article solves
   - Retrieve full documents when:
     * The title strongly matches the user's issue but the snippet isn't enough
     * You need complete procedures or configuration details
     * The user is confused about a previous solution
     * Following up on a solution that needs more context

4. **Intelligent Response Strategy**:
   - Synthesize information from multiple sources when needed
   - Provide step-by-step solutions when you have enough information
   - Ask for clarification when it would significantly improve your ability to help
   - Reference document titles and URLs so users can explore further

5. **Follow-up Support**:
   - When users are confused about a solution, retrieve the full document for complete context
   - Use focused searches to address specific follow-up questions
   - Be ready to provide alternative approaches if the first solution doesn't work

**Key Principle**: Balance being helpful with being accurate. It's okay to ask for clarification when it would lead to a much better solution."""
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
            "agent_node", self._should_continue, {"continue": "tool_node", END: END}
        )

        # Add edge from tool back to agent
        builder.add_edge("tool_node", "agent_node")

        # Compile with checkpointer
        return builder.compile(checkpointer=self.checkpointer)
    from langsmith import traceable

    @traceable
    def _agent_node(self, state: MessagesState, config: RunnableConfig) -> dict:  # noqa: ARG002
        """Agent node that decides whether to search or respond."""
        messages = state["messages"]

        logger.debug(f"Agent node - incoming messages count: {len(messages)}")

        # Invoke LLM with tools
        try:
            response = self.llm_with_tools.invoke(messages)
            logger.debug(
                f"LLM response type: {type(response)}, has tool_calls: {hasattr(response, 'tool_calls')}"
            )
            if hasattr(response, "tool_calls"):
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
            elif tool_name == "get_full_document":
                tool_result = get_full_document.invoke(tool_args, config)
            else:
                tool_result = f"Error: Unknown tool {tool_name}"

            logger.debug(f"Tool result length: {len(tool_result)}")

            # Create tool message
            tool_message = ToolMessage(
                content=tool_result, tool_call_id=tool_call["id"], name=tool_name
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
        self, message: str, thread_id: str, customer_id: str = "acme_corp", top_k: int = 3
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
            "configurable": {"thread_id": thread_id, "customer_id": customer_id, "top_k": top_k}
        }

        try:
            logger.info(
                f"Chat invoked - thread_id: {thread_id}, customer_id: {customer_id}, top_k: {top_k}"
            )
            logger.debug(f"User message: {message}")

            # Check if this is a new conversation
            state = self.app.get_state({"configurable": {"thread_id": thread_id}})
            
            # Prepare messages based on whether it's a new conversation
            if not state.values:  # New conversation
                messages = [SystemMessage(content=self.system_prompt), HumanMessage(content=message)]
                logger.debug("New conversation - adding system prompt")
            else:  # Existing conversation
                messages = [HumanMessage(content=message)]
                logger.debug("Existing conversation - no system prompt needed")

            # Invoke the agent
            result = self.app.invoke({"messages": messages}, config)

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
                if isinstance(msg, AIMessage) and not (
                    hasattr(msg, "tool_calls") and msg.tool_calls
                ):
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
                elif msg.type == "ai" and not msg.tool_calls:
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
    model_name: str = "gemini-2.5-flash", temperature: float = 0, use_persistent_memory: bool = True
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
        model_name=model_name, temperature=temperature, checkpointer=checkpointer
    )
