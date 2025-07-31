import os
from typing import List
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from langchain_core.documents import Document
from langchain_core.prompts import PromptTemplate
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain.chat_models import init_chat_model
from langgraph.graph import START, StateGraph

# Import our new parent document system
from build_chunk_index_parent import SmartParentDocumentRAG, MARKDOWN_EXPORT_PATH

# Load environment variables
load_dotenv()

# Configuration
LLM_MODEL = "gemini-2.5-flash"
EMBEDDING_MODEL = "gemini-embedding-001"

class State(BaseModel):
    """State object for the RAG pipeline"""
    question: str
    context: List[Document] = Field(default_factory=list)
    answer: str = ""

class ParentDocumentRAGPipeline:
    """
    Enhanced RAG Pipeline using Parent Document Retriever for maximum context
    
    Key improvements:
    - Returns ENTIRE parent documents for maximum context
    - Child chunks for precise semantic search targeting  
    - Smart change tracking with incremental updates
    - No hypothetical question overhead
    """
    
    def __init__(self, processor: SmartParentDocumentRAG = None):
        """Initialize the parent document RAG pipeline"""
        self.processor = processor or self._initialize_processor()
        self.llm = init_chat_model(LLM_MODEL, model_provider="google_genai")
        self.prompt = self._setup_prompt()
        self.graph = self._build_graph()
    
    def _initialize_processor(self):
        """Initialize processor and load documents if needed"""
        processor = SmartParentDocumentRAG()        
        return processor
    
    def _setup_prompt(self):
        """Enhanced prompt for parent document context"""
        prompt_template = """You are an assistant for question-answering tasks. Use the following pieces of retrieved context to answer the question. The context includes both detailed information and broader document context to help you provide comprehensive answers.

If you don't know the answer, just say that you don't know. Use three sentences maximum and keep the answer concise.

Question: {question} 
Context: {context} 
Answer:"""
        return PromptTemplate.from_template(prompt_template)
    
    def retrieve(self, state: State):
        """
        Retrieve using parent document retriever
        
        Args:
            state: Current state containing the question
            
        Returns:
            Dictionary with retrieved ENTIRE parent documents
        """
        # Parent document retriever automatically:
        # 1. Searches child chunks for precise semantic matching
        # 2. Returns ENTIRE parent documents (full files) for maximum context
        retrieved_docs = self.processor.retriever.get_relevant_documents(state.question)
        
        # Limit to top 3 entire documents for manageable context
        return {"context": retrieved_docs[:3]}
    
    def generate(self, state: State):
        """
        Generate answer using parent document context
        
        Args:
            state: Current state containing question and context
            
        Returns:
            Dictionary with the generated answer
        """
        # Format parent documents with their metadata
        context_parts = []
        for doc in state.context:
            title = doc.metadata.get('title', 'Untitled Document')
            breadcrumb = doc.metadata.get('breadcrumb', 'Uncategorized')
            content = doc.page_content
            
            formatted_doc = (
                f"## Source: {title}\n"
                f"## Category: {breadcrumb}\n\n"
                f"{content}"
            )
            context_parts.append(formatted_doc)
        
        docs_content = "\n\n---\n\n".join(context_parts)
        
        messages = self.prompt.invoke({
            "question": state.question, 
            "context": docs_content
        })
        response = self.llm.invoke(messages)
        return {"answer": response.content}
    
    def _build_graph(self):
        """Build the LangGraph execution graph"""
        graph_builder = StateGraph(State).add_sequence([self.retrieve, self.generate])
        graph_builder.add_edge(START, "retrieve")
        return graph_builder.compile()
    
    def ask(self, question: str, stream_mode: str = "updates", format_output: bool = True):
        """
        Ask a question and get an answer from the RAG pipeline
        
        Args:
            question: The question to ask
            stream_mode: How to stream the results ("updates", "values", etc.)
            format_output: Whether to format the output nicely
            
        Returns:
            Generator yielding formatted results or raw results
        """
        if format_output:
            yield from self._ask_with_formatting(question, stream_mode)
        else:
            yield from self.graph.stream({"question": question}, stream_mode=stream_mode)
    
    def _ask_with_formatting(self, question: str, stream_mode: str):
        """Ask question with formatted output"""
        for step in self.graph.stream({"question": question}, stream_mode=stream_mode):
            for node_name, node_output in step.items():
                if node_name == "retrieve":
                    yield self._format_retrieval_results(node_output)
                elif node_name == "generate":
                    yield self._format_generation_results(node_output)
    
    def _format_retrieval_results(self, retrieval_output):
        """Format retrieval results for better readability"""
        retrieved_docs = retrieval_output.get('context', [])
        
        result = {
            "type": "retrieval",
            "formatted_output": f"🔍 ENTIRE DOCUMENT RETRIEVAL:\n{'=' * 60}\n"
        }
        
        formatted_docs = []
        for i, doc in enumerate(retrieved_docs, 1):
            title = doc.metadata.get('title', 'Untitled Document')
            breadcrumb = doc.metadata.get('breadcrumb', 'Uncategorized')
            content = doc.page_content
            
            formatted_doc = f"""
📄 Entire Document {i}:
  📖 Title: {title}
  📂 Category: {breadcrumb}
  📏 Full Document Length: {len(content)} characters
  📝 Content Preview: {content[:300]}{'...' if len(content) > 300 else ''}
"""
            formatted_docs.append(formatted_doc)
        
        result["formatted_output"] += '\n'.join(formatted_docs)
        result["formatted_output"] += f"\n{'=' * 60}\n"
        result["raw_data"] = retrieval_output
        
        return result
    
    def _format_generation_results(self, generation_output):
        """Format generation results for better readability"""
        answer = generation_output.get('answer', '')
        
        result = {
            "type": "generation",
            "formatted_output": f"\n💬 GENERATED ANSWER:\n{'-' * 40}\n{answer}\n{'-' * 40}\n",
            "raw_data": generation_output
        }
        
        return result

# Legacy compatibility - alias to maintain existing interface
RAGPipeline = ParentDocumentRAGPipeline

def format_documents(docs):
    """
    Standalone function to format documents for better readability
    (Kept for backward compatibility)
    """
    formatted_output = []
    for i, doc in enumerate(docs, 1):
        title = doc.metadata.get('title', 'Untitled Document')
        breadcrumb = doc.metadata.get('breadcrumb', 'Uncategorized')
        content = doc.page_content
        
        formatted_doc = f"""
📄 Document {i}:
  📖 Title: {title}
  📂 Category: {breadcrumb}
  📝 Content Preview: {content[:200]}{'...' if len(content) > 200 else ''}
"""
        formatted_output.append(formatted_doc)
    return '\n'.join(formatted_output)

def main():
    """Example usage of the enhanced RAG pipeline"""
    # Initialize the pipeline
    print("🚀 Initializing Enhanced Parent Document RAG Pipeline...")
    pipeline = ParentDocumentRAGPipeline()
    
    # Example questions
    questions = [
        # "How to change my account's password?",
        # "How do I register for two-step authentication?", 
        # "What are the requirements for course account passwords?",
        # "Why I cannot access my ETS account?",
       
        "I am installing Intune, but I cannot find Company Portal after installation?",
    ]
    
    for question in questions:
        print(f"\n🤔 Question: {question}")
        print("=" * 80)
        
        for result in pipeline.ask(question, format_output=True):
            print(result["formatted_output"])

if __name__ == "__main__":
    main()
