from langchain_tavily import TavilySearch
from langchain_core.tools import tool
from langchain_chroma import Chroma
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from app.utils.chroma_utils import vectorstore
from app.config.settings import (
    VECTOR_STORE_DIR, 
    CHROMA_COLLECTION_NAME, 
    DUCKDB_PATH, 
    GEMINI_API_KEY,
    EMBEDDING_MODEL_NAME
)
import os
import duckdb
import logging

logger = logging.getLogger(__name__)

# Initialize Tavily search
tavily = TavilySearch(max_results=3, topic="general")

# Create retriever from vectorstore (existing RAG)
retriever = vectorstore.as_retriever(search_kwargs={"k": 3})

# Se elimina la inicialización global del sql_retriever de aquí.

@tool
def web_search_tool(query: str) -> str:
    """Up-to-date web info via Tavily"""
    try:
        result = tavily.invoke({"query": query})

        # Extract and format the results from Tavily response
        if isinstance(result, dict) and 'results' in result:
            formatted_results = []
            for item in result['results']:
                title = item.get('title', 'No title')
                content = item.get('content', 'No content')
                url = item.get('url', '')
                formatted_results.append(f"Title: {title}\nContent: {content}\nURL: {url}")

            return "\n\n".join(formatted_results) if formatted_results else "No results found"
        else:
            return str(result)
    except Exception as e:
        return f"WEB_ERROR::{e}"

@tool
def rag_search_tool(query: str) -> str:
    """Top-3 chunks from KB (empty string if none)"""
    try:
        docs = retriever.invoke(query)
        logger.debug(f"RAG DEBUG: Query: {query} | Docs: {[d.page_content for d in docs]}")
        return "\n\n".join(d.page_content for d in docs) if docs else ""
    except Exception as e:
        return f"RAG_ERROR::{e}"

@tool
def sql_context_retriever(query: str) -> str:
    """
    Retrieves relevant database table context for SQL generation.
    Returns detailed schema information, sample data, and table descriptions.
    """
    try:
        # Se inicializa el retriever aquí para obtener siempre la versión más reciente.
        sql_embeddings = GoogleGenerativeAIEmbeddings(
            model=EMBEDDING_MODEL_NAME,
            google_api_key=GEMINI_API_KEY
        )
        sql_vectorstore = Chroma(
            persist_directory=str(VECTOR_STORE_DIR),
            embedding_function=sql_embeddings,
            collection_name=CHROMA_COLLECTION_NAME
        )
        sql_retriever = sql_vectorstore.as_retriever(search_kwargs={"k": 1})
        
        # Retrieve relevant table contexts
        docs = sql_retriever.invoke(query)
        
        if not docs:
            return "SQL_ERROR::No relevant tables found for your query. Please check if the ETL pipeline has been executed."
        
        # Format the retrieved contexts
        formatted_context = []
        for i, doc in enumerate(docs, 1):
            table_name = doc.metadata.get('table_name', f'table_{i}')
            formatted_context.append(f"=== TABLE CONTEXT {i}: {table_name} ===\n{doc.page_content}")
        
        logger.info(f"SQL Context Retrieved: Found {len(docs)} relevant tables for query: {query}")
        return "\n\n".join(formatted_context)
        
    except Exception as e:
        # Captura de error mejorada para ser más claro con el usuario.
        error_str = str(e).lower()
        if "does not exist" in error_str or "not found" in error_str:
            logger.error(f"Error retrieving SQL context: Collection '{CHROMA_COLLECTION_NAME}' not found. Please run the ETL pipeline.")
            return f"SQL_ERROR::Collection '{CHROMA_COLLECTION_NAME}' not found. The ETL process needs to be run to create the knowledge base."

        logger.error(f"Error retrieving SQL context: {e}")
        return f"SQL_ERROR::Error retrieving database context: {str(e)}"

@tool 
def execute_duckdb_query(sql_query: str) -> str:
    """
    Executes a SQL query against the DuckDB database and returns the results.
    Only SELECT queries are allowed for security.
    """
    try:
        # Security check: only allow SELECT queries
        cleaned_query = sql_query.strip().upper()
        if not cleaned_query.startswith('SELECT'):
            return "SQL_ERROR::Only SELECT queries are allowed for security reasons."
        
        # Connect to DuckDB
        con = duckdb.connect(database=str(DUCKDB_PATH), read_only=True)
        
        try:
            # Execute the query
            result = con.execute(sql_query).fetchdf()
            
            # Format results
            if result.empty:
                return "QUERY_RESULT::No data returned by the query."
            
            # Limit result size for performance
            if len(result) > 100:
                logger.warning(f"Query returned {len(result)} rows, limiting to first 100")
                result = result.head(100)
                note = f"\n\nNote: Results limited to first 100 rows out of {len(result)} total."
            else:
                note = ""
            
            # Convert to string with nice formatting
            result_str = result.to_string(index=False, max_rows=100)
            
            logger.info(f"SQL Query executed successfully: {len(result)} rows returned")
            return f"QUERY_RESULT::\n{result_str}{note}"
            
        finally:
            con.close()
            
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error executing SQL query: {error_msg}")
        return f"SQL_ERROR::{error_msg}"

@tool
def get_available_tables() -> str:
    """
    Returns a list of all available tables in the DuckDB database.
    """
    try:
        con = duckdb.connect(database=str(DUCKDB_PATH), read_only=True)
        
        try:
            tables = con.execute("SHOW TABLES").fetchdf()
            
            if tables.empty:
                return "No tables available. Please run the ETL pipeline first."
            
            table_list = tables['name'].tolist()
            # Filter out system tables
            user_tables = [t for t in table_list if not t.startswith('_')]
            
            logger.info(f"Available tables retrieved: {len(user_tables)} tables")
            return f"AVAILABLE_TABLES::\n" + "\n".join([f"- {table}" for table in user_tables])
            
        finally:
            con.close()
            
    except Exception as e:
        logger.error(f"Error getting available tables: {e}")
        return f"SQL_ERROR::Error retrieving table list: {str(e)}"