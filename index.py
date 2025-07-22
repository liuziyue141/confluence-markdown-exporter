import os
# LangChain and Community Document Loaders
from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain.text_splitter import MarkdownHeaderTextSplitter

# LangChain integrations for Google AI and Vector Stores
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_community.vectorstores import Chroma

# LangChain Core components
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableParallel, RunnablePassthrough
from dotenv import load_dotenv
from langchain_core.documents import Document

# Pydantic - Corrected Import
from pydantic import BaseModel, Field

load_dotenv()

# --- CONFIGURATION ---
# Make sure your GOOGLE_API_KEY is set as an environment variable
MARKDOWN_EXPORT_PATH = "/Users/lindalee/confluence_exp"  # The folder where your markdown files are
CHROMA_DB_PATH = "./chroma_db"    # Where the vector database will be stored
LLM_MODEL = "gemini-1.5-flash"
EMBEDDING_MODEL = "models/embedding-001"

# --- 1. LOAD AND CHUNK DOCUMENTS ---

# Use a loader to handle all markdown files in the directory
loader = DirectoryLoader(
    MARKDOWN_EXPORT_PATH,
    glob="**/*.md",
    loader_cls=TextLoader,
    show_progress=True,
)
docs = loader.load()

# Define how to split markdown files based on headers
headers_to_split_on = [("#", "Header 1"), ("##", "Header 2"), ("###", "Header 3")]
markdown_splitter = MarkdownHeaderTextSplitter(
    headers_to_split_on=headers_to_split_on, strip_headers=False
)

# A simple check to avoid errors on empty directories
if not docs:
    print("No markdown documents found. Please run the exporter first.")
    exit()

all_splits = []
for doc in docs:
    all_splits.extend(markdown_splitter.split_text(doc.page_content))

print(f"Loaded {len(docs)} documents and split them into {len(all_splits)} chunks.")

# --- 2. DEFINE THE QUESTION GENERATION LOGIC WITH PYDANTIC ---

# Define the Pydantic data structure for the generated question
class HypotheticalQuestion(BaseModel):
    question: str = Field(
        ...,
        description="A specific and concise question that the provided text chunk can answer.",
    )

# Set up the Gemini LLM and the prompt for generating questions
llm = ChatGoogleGenerativeAI(model=LLM_MODEL, temperature=0, convert_system_message_to_human=True)
prompt = ChatPromptTemplate.from_template(
    "You are an expert at creating training data. Based on the following document chunk, "
    "generate a single, specific, and concise question that this chunk would be the perfect answer to.\n\n"
    "Chunk:\n{chunk_text}"
)

# Create the chain that will call the LLM and parse the output into our Pydantic model
generate_question_chain = prompt | llm.with_structured_output(HypotheticalQuestion)


# --- 3. PROCESS AND STORE IN VECTOR DATABASE ---

# This function will process each chunk to generate and store the data
def process_and_store_chunk(chunk):
    """
    Takes a document chunk, generates a hypothetical question for it,
    and returns a new document dictionary ready for the vector store.
    """
    # 1. Generate the question from the chunk's content
    hypothetical_question = generate_question_chain.invoke(
        {"chunk_text": chunk.page_content}
    )

    # 2. Construct the new document for the vector store
    new_doc = Document(
        page_content=hypothetical_question.question,
        metadata={
            "original_content": chunk.page_content,
            **chunk.metadata,
        }
    )
    return new_doc


# --- MAIN EXECUTION ---
if __name__ == "__main__":
    print("Generating hypothetical questions for each chunk using Gemini...")

    # Process all chunks (you might add a progress bar here for large datasets)
    processed_documents = [process_and_store_chunk(chunk) for chunk in all_splits]

    print(f"Initializing vector store with Google Embeddings ({EMBEDDING_MODEL})...")

    # Initialize the vector store with the Google embedding function
    vectorstore = Chroma.from_documents(
        documents=processed_documents,
        embedding=GoogleGenerativeAIEmbeddings(model=EMBEDDING_MODEL),
        persist_directory=CHROMA_DB_PATH,
    )

    print("\n✅ RAG index has been successfully built!")
    print(f"Vector store is persisted at: {CHROMA_DB_PATH}")