from typing import List
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from langchain_core.documents import Document
from langchain_core.prompts import PromptTemplate
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain.chat_models import init_chat_model
from langchain_postgres import PGVector
from langgraph.graph import START, StateGraph

# Load environment variables
load_dotenv()

# Configuration
LLM_MODEL = "gemini-2.5-flash"
EMBEDDING_MODEL = "gemini-embedding-001"
COLLECTION_NAME = "confluence_background_knowledge_structure_simple"
CONNECTION_STRING = "postgresql+psycopg://tim_itagent:Apple3344!@localhost:5432/confluence_exp"

class State(BaseModel):
    """State object for the RAG pipeline"""
    question: str
    context: List[Document] = Field(default_factory=list)
    answer: str = ""

class SimpleRAGInference:
    """Simple RAG Inference Pipeline"""
    
    def __init__(self):
        """Initialize the RAG pipeline with models and vector store"""
        self.llm = init_chat_model(LLM_MODEL, model_provider="google_genai")
        self.embeddings = GoogleGenerativeAIEmbeddings(model=EMBEDDING_MODEL)
        self.vector_store = self._setup_vector_store()
        self.prompt = self._setup_prompt()
        self.graph = self._build_graph()
    
    def _setup_vector_store(self):
        """Initialize the vector store connection"""
        vector_store = PGVector(
            embeddings=self.embeddings,
            collection_name=COLLECTION_NAME,
            connection=CONNECTION_STRING,
        )
        return vector_store
    
    def _setup_prompt(self):
        """Setup the generation prompt template"""
        retrieve_prompt = """You are an assistant for question-answering tasks. Use the following pieces of retrieved context to answer the question. If you don't know the answer, just say that you don't know. Use three sentences maximum and keep the answer concise.
Question: {question} 
Context: {context} 
Answer:"""
        return PromptTemplate.from_template(retrieve_prompt)
    
    def retrieve(self, state: State):
        """
        Retrieve relevant documents from the vector store
        
        Args:
            state: Current state containing the question
            
        Returns:
            Dictionary with retrieved context documents
        """
        retrieved_docs = self.vector_store.similarity_search(state.question, k=5)
        return {"context": retrieved_docs}
    
    def generate(self, state: State):
        """
        Generate an answer using the retrieved context
        
        Args:
            state: Current state containing question and context
            
        Returns:
            Dictionary with the generated answer
        """
        context_parts = []
        # Retrieve the documents from the state
        retrieved_docs = state.context

        for doc in retrieved_docs:
            # Extract metadata safely, providing defaults if keys are missing
            title = doc.metadata.get('title', 'Untitled Document')
            breadcrumb = doc.metadata.get('breadcrumb', 'Uncategorized')
            content = doc.page_content # The actual text chunk

            # Format the chunk in a way that's easy for the LLM to understand
            formatted_chunk = (
                f"## Source: {title}\n"
                f"## Category: {breadcrumb}\n\n"
                f"{content}"
            )
            context_parts.append(formatted_chunk)

        # Join the formatted parts with a clear separator
        docs_content = "\n\n---\n\n".join(context_parts)

        messages = self.prompt.invoke({"question": state.question, "context": docs_content})
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
            "formatted_output": f"🔍 RETRIEVAL RESULTS:\n{'=' * 60}\n"
        }
        
        formatted_docs = []
        for i, doc in enumerate(retrieved_docs, 1):
            title = doc.metadata.get('title', 'Untitled Document')
            breadcrumb = doc.metadata.get('breadcrumb', 'Uncategorized')
            source = doc.metadata.get('source', 'Unknown source')
            content = doc.page_content
            
            formatted_doc = f"""
📄 Document {i}:
  📖 Title: {title}
  📂 Category: {breadcrumb}
  📍 Source: {source}
  📝 Content Preview: {content[:200]}{'...' if len(content) > 200 else ''}
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
    
    def check_index_status(self):
        """Check the status of the vector store index"""
        try:
            # Perform a simple search to verify connection
            test_results = self.vector_store.similarity_search("test", k=1)
            
            # Get approximate document count
            # Note: This is a simple check, actual count may vary
            print("✅ Vector store connection successful")
            
            if test_results:
                print(f"📊 Index appears to contain documents")
                sample_doc = test_results[0]
                print(f"   Sample document title: {sample_doc.metadata.get('title', 'Unknown')}")
            else:
                print("⚠️  No documents found in index. Run build_simple_index_with_recorder.py first.")
                
        except Exception as e:
            print(f"❌ Error connecting to vector store: {e}")
            print("   Make sure PostgreSQL is running and the database is accessible.")

def main():
    """Example usage of the simple RAG inference"""
    print("🚀 Initializing Simple RAG Inference...")
    
    # Initialize the inference pipeline
    inference = SimpleRAGInference()
    
    # Check index status
    print("\n📊 Checking index status...")
    inference.check_index_status()
    
    # Interactive mode
    print("\n💬 Interactive Q&A Mode (type 'quit' to exit)")
    print("=" * 60)
    
    while True:
        question = input("\n🤔 Your question: ").strip()
        
        if question.lower() in ['quit', 'exit', 'q']:
            print("👋 Goodbye!")
            break
        
        if not question:
            print("⚠️  Please enter a question.")
            continue
        
        print("\n" + "=" * 80)
        
        for result in inference.ask(question, format_output=True):
            print(result["formatted_output"])

if __name__ == "__main__":
    main()