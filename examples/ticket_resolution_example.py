"""Example usage of the ticket resolution system with LangGraph."""

import os
from langchain.chat_models import init_chat_model
# from langchain_anthropic import ChatAnthropic  # Alternative LLM

from confluence_rag_integration.graphs import TicketResolutionGraph
from confluence_rag_integration.tools import create_retrieval_tool
from dotenv import load_dotenv
load_dotenv()

LLM_MODEL = "gemini-2.5-flash"
MODEL_PROVIDER = "google_genai"

def example_direct_tool_usage():
    """Example of using the retrieval tool directly."""
    print("=== Direct Tool Usage Example ===\n")
    
    # Create the tool
    tool = create_retrieval_tool()
    
    # Use the tool directly
    result = tool._run(
        query="How do I reset my password?",
        customer_id="acme_corp",
        top_k=3
    )
    
    print("Tool Result:")
    print(result)
    print("\n" + "="*50 + "\n")


def example_langgraph_pipeline():
    """Example of using the full LangGraph pipeline."""
    print("=== LangGraph Pipeline Example ===\n")
    
    # Initialize LLM (using OpenAI as example)
    llm = init_chat_model(LLM_MODEL, model_provider=MODEL_PROVIDER)
    
    # Alternative: Use Claude
    # llm = ChatAnthropic(model="claude-3-opus-20240229")
    
    # Create the graph
    graph = TicketResolutionGraph(
        llm=llm,
        customer_id="acme_corp"
    )
    
    # Example support tickets
    tickets = [
        "I can't log into the system. It says my account is locked.",
        "How do I export data from the dashboard?",
        "The API is returning 500 errors when I try to update user profiles"
    ]
    
    for ticket in tickets:
        print(f"Ticket: {ticket}")
        print("-" * 40)
        
        # Run the graph
        result = graph.run(ticket)
        
        print(f"Response: {result['response']}")
        print(f"Queries generated: {result['queries_used']}")
        print(f"Documents found: {result['documents_retrieved']}")
        print("\n" + "="*50 + "\n")


def example_integration_with_agent():
    """Example of integrating the tool with a LangChain agent."""
    from langchain.agents import create_openai_tools_agent, AgentExecutor
    from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
    
    print("=== Agent Integration Example ===\n")
    
    # Initialize components
    from langchain_openai import ChatOpenAI
    llm = ChatOpenAI(model="gpt-4", temperature=0)
    tool = create_retrieval_tool()
    
    # Create prompt
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a helpful support agent. Use the knowledge retrieval tool to find relevant documentation before answering support tickets."),
        ("user", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ])
    
    # Create agent
    agent = create_openai_tools_agent(llm, [tool], prompt)
    agent_executor = AgentExecutor(agent=agent, tools=[tool], verbose=True)
    
    # Run agent
    response = agent_executor.invoke({
        "input": "A customer is having trouble with SSO integration. They get a SAML error."
    })
    
    print(f"Agent Response: {response['output']}")


if __name__ == "__main__":
    # Check for API key
    if MODEL_PROVIDER == "google_genai" and not os.getenv("GOOGLE_API_KEY"):
        print("Error: GOOGLE_API_KEY environment variable not set.")
        print("Please set it with: export GOOGLE_API_KEY=your-api-key")
        print("\nAlternatively, you can:")
        print("1. Use OpenAI by changing MODEL_PROVIDER to 'openai' and setting OPENAI_API_KEY")
        print("2. Use Anthropic by uncommenting the ChatAnthropic import and using it directly")
        exit(1)
    
    # Run examples
    example_direct_tool_usage()
    example_langgraph_pipeline()
    # example_integration_with_agent()  # Uncomment to run agent example