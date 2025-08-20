from langchain_tavily import TavilySearch
from langchain_core.tools import tool
from langchain_chroma import Chroma
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from app.utils.chroma_utils import vectorstore
from app.config.settings import (
    VECTOR_STORE_DIR, 
    CHROMA_COLLECTIONS,
    DUCKDB_PATH, 
    GEMINI_API_KEY,
    EMBEDDING_MODEL_NAME
)
from app.etl.retrieval_orchestrator import get_orchestrator
import duckdb
import logging
import json

logger = logging.getLogger(__name__)

# Initialize Tavily search
tavily = TavilySearch(max_results=3, topic="general")

# Create retriever from vectorstore (existing RAG para compatibilidad)
retriever = vectorstore.as_retriever(search_kwargs={"k": 3})

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
    """
    DEPRECADO: Usa retrieval por dominio específico.
    Mantenido para compatibilidad hacia atrás.
    """
    try:
        # Por compatibilidad, usar business snippets como fallback
        orchestrator = get_orchestrator()
        snippets = orchestrator.retrieve_for_business(query, include_external=False)
        return "\n\n".join(s["text"] for s in snippets) if snippets else ""
    except Exception as e:
        logger.warning(f"rag_search_tool fallback error: {e}")
        # Fallback al retriever original
        try:
            docs = retriever.invoke(query)
            return "\n\n".join(d.page_content for d in docs) if docs else ""
        except Exception as e2:
            return f"RAG_ERROR::{e2}"

@tool
def sql_context_retriever(query: str) -> str:
    """
    Retrieves relevant database table context for SQL generation.
    ACTUALIZADO: Usa el orquestador multi-colección.
    """
    try:
        orchestrator = get_orchestrator()
        return orchestrator.retrieve_for_sql(query)
    except Exception as e:
        logger.error(f"Error en sql_context_retriever: {e}")
        return f"SQL_ERROR::Error al recuperar contexto de esquemas: {str(e)}"

@tool 
def execute_duckdb_query(sql_query: str) -> str:
    """
    Executes a SQL query against the DuckDB database and returns the results
    in a structured JSON format containing both a string table and JSON data.
    Only SELECT queries are allowed for security.
    """
    try:
        # Security check: only allow SELECT queries
        cleaned_query = sql_query.strip().upper()
        if not cleaned_query.startswith('SELECT'):
            # Return error in the expected JSON format
            return json.dumps({
                "table_str": "SQL_ERROR::Only SELECT queries are allowed for security reasons.",
                "json_data": None
            })
        
        # Connect to DuckDB
        con = duckdb.connect(database=str(DUCKDB_PATH), read_only=True)
        
        try:
            result = con.execute(sql_query).fetchdf()
            
            # Format results
            if result.empty:
                return json.dumps({
                    "table_str": "QUERY_RESULT::No results found.",
                    "json_data": []
                })
            
            # Convert to string format for the LLM and JSON for tools
            table_str = result.to_string(index=False, max_rows=1000)
            json_data = result.to_dict(orient='records')

            response_payload = {
                "table_str": f"QUERY_RESULT::\n{table_str}",
                "json_data": json_data
            }
            
            logger.info(f"SQL Query executed successfully: {len(result)} rows returned")
            return json.dumps(response_payload, ensure_ascii=False)
            
        finally:
            con.close()
            
    except Exception as e:
        error_payload = {
            "table_str": f"SQL_ERROR::{str(e)}",
            "json_data": None
        }
        logger.error(f"Error executing SQL query: {e}")
        return json.dumps(error_payload)

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