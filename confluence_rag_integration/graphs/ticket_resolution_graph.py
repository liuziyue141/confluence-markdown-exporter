"""LangGraph pipeline for ticket resolution with knowledge retrieval."""

from typing import Dict, Any, List, TypedDict
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_core.language_models import BaseLLM
import json

from ..tools import create_retrieval_tool


class GraphState(TypedDict):
    """State for the ticket resolution graph."""
    messages: List[BaseMessage]
    customer_id: str
    preprocessed_queries: List[str]
    retrieved_documents: List[Dict[str, Any]]
    final_response: str

from pydantic import BaseModel
class QueryVariations(BaseModel):
    queries: List[str]

class TicketResolutionGraph:
    """LangGraph pipeline for ticket resolution with knowledge retrieval."""
    
    def __init__(self, llm: BaseLLM, customer_id: str):
        self.llm = llm
        self.customer_id = customer_id
        self.retrieval_tool = create_retrieval_tool()
        # Tool will be executed directly
        
        # Build the graph
        self.graph = self._build_graph()
    
    def _build_graph(self) -> StateGraph:
        """Build the ticket resolution graph."""
        workflow = StateGraph(GraphState)
        
        # Add nodes
        workflow.add_node("preprocess_query", self._preprocess_query_node)
        workflow.add_node("retrieve_knowledge", self._retrieve_knowledge_node)
        workflow.add_node("synthesize_response", self._synthesize_response_node)
        
        # Add edges
        workflow.set_entry_point("preprocess_query")
        workflow.add_edge("preprocess_query", "retrieve_knowledge")
        workflow.add_edge("retrieve_knowledge", "synthesize_response")
        workflow.add_edge("synthesize_response", END)
        
        return workflow.compile()
    
    def _preprocess_query_node(self, state: GraphState) -> GraphState:
        """Preprocess the query to generate multiple search variations."""
        last_message = state["messages"][-1].content
        
        # Use LLM to generate query variations
        prompt = f"""Given this support ticket query, generate 3 different search queries that would help find relevant documentation.
        
        Original query: {last_message}
        
        Generate queries that:
        1. Extract key technical terms and product names
        2. Rephrase as a statement or different question form
        3. Include related terms or synonyms
        
        Return as JSON array of strings."""

        # Try structured output if available, otherwise parse JSON
        try:
            if hasattr(self.llm, 'with_structured_output'):
                structured_llm = self.llm.with_structured_output(QueryVariations)
                response = structured_llm.invoke(prompt)
                queries = response.queries
            else:
                response = self.llm.invoke(prompt)
                # Parse the LLM response
                queries = json.loads(response.content)
                if not isinstance(queries, list):
                    queries = [last_message]
        except:
            # Fallback to original query if parsing fails
            queries = [last_message]
        
        state["preprocessed_queries"] = queries
        return state
    
    def _retrieve_knowledge_node(self, state: GraphState) -> GraphState:
        """Retrieve knowledge for all preprocessed queries."""
        all_documents = []
        seen_sources = set()
        
        # Retrieve for each query variation
        for query in state["preprocessed_queries"]:
            tool_input = {
                "query": query,
                "customer_id": self.customer_id,
                "top_k": 3  # Get top 3 for each variation  
            }
            # top_k should be configurable TODO
            
            # Execute the tool directly
            result = self.retrieval_tool._run(**tool_input)
            
            # Parse results and deduplicate
            if isinstance(result, str) and "Document" in result:
                # Extract documents from formatted string
                docs = result.split("\n\n---\n\n")
                for doc in docs:
                    if doc.strip() and "Source:" in doc:
                        # Extract source to check for duplicates
                        source_line = [l for l in doc.split("\n") if "Source:" in l][0]
                        source = source_line.split("Source:")[1].strip().rstrip("):") 
                        
                        if source not in seen_sources:
                            seen_sources.add(source)
                            all_documents.append({
                                "content": doc,
                                "query": query,
                                "source": source
                            })
        
        state["retrieved_documents"] = all_documents
        return state
    
    def _synthesize_response_node(self, state: GraphState) -> GraphState:
        """Synthesize final response using retrieved documents."""
        original_query = state["messages"][-1].content
        documents = state["retrieved_documents"]
        
        if not documents:
            state["final_response"] = "I couldn't find any relevant documentation for your query. Please provide more details or try rephrasing your question."
            return state
        
        # Prepare context from documents
        context = "\n\n".join([doc["content"] for doc in documents[:5]])  # Use top 5 documents
        
        # Generate response
        prompt = f"""Based on the following documentation, provide a helpful response to resolve this support ticket.
        
        Original Query: {original_query}
        
        Relevant Documentation:
        {context}
        
        Provide a clear, step-by-step response that directly addresses the user's issue. If the documentation doesn't fully answer the question, acknowledge what information is missing."""
        
        response = self.llm.invoke(prompt)
        state["final_response"] = response.content
        
        # Add AI message to state
        state["messages"].append(AIMessage(content=state["final_response"]))
        
        return state
    
    def run(self, query: str) -> Dict[str, Any]:
        """Run the graph with a query."""
        initial_state = {
            "messages": [HumanMessage(content=query)],
            "customer_id": self.customer_id,
            "preprocessed_queries": [],
            "retrieved_documents": [],
            "final_response": ""
        }
        
        result = self.graph.invoke(initial_state)
        return {
            "response": result["final_response"],
            "queries_used": result["preprocessed_queries"],
            "documents_retrieved": len(result["retrieved_documents"])
        }