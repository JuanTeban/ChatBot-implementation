import sqlite3
import re
from typing import List, Dict, Any
from langchain_core.tools import tool

class SQLSecurityError(Exception):
    pass

def query_sanity_check(query: str):
    query_upper = query.strip().upper()
    if not query_upper.startswith("SELECT"):
        raise SQLSecurityError("Operación no permitida. Solo se permiten consultas SELECT.")

    prohibited_keywords = ["DROP", "DELETE", "INSERT", "UPDATE", "ALTER", "CREATE", "ATTACH"]
    for keyword in prohibited_keywords:
        if keyword in query_upper:
            raise SQLSecurityError(f"Operación no permitida. La palabra clave '{keyword}' está prohibida.")

@tool
def get_db_schema(conn: sqlite3.Connection) -> str:
    """Devuelve el esquema (sentencias CREATE TABLE) de la base de datos."""
    cursor = conn.cursor()
    cursor.execute("SELECT sql FROM sqlite_master WHERE type='table';")
    return "\n".join([row[0] for row in cursor.fetchall()])

@tool
def execute_sql_query(conn: sqlite3.Connection, query: str) -> List[Dict[str, Any]]:
    """Ejecuta una consulta SQL SELECT validada y devuelve los resultados."""
    try:
        query_sanity_check(query)
        cursor = conn.cursor()
        cursor.execute(query)
        columns = [desc[0] for desc in cursor.description]
        results = [dict(zip(columns, row)) for row in cursor.fetchall()]
        return results
    except (sqlite3.Error, SQLSecurityError) as e:
        raise type(e)(f"Error al ejecutar la consulta: {e}")

@tool
def get_distinct_column_values(conn: sqlite3.Connection, column_name: str, table_name: str = "datos") -> List[str]:
    """Devuelve una lista de valores únicos para una columna específica de una tabla."""
    try:
        cursor = conn.cursor()
        # Usamos una consulta parametrizada para seguridad, aunque el riesgo es bajo aquí
        query = f"SELECT DISTINCT \"{column_name}\" FROM \"{table_name}\" WHERE \"{column_name}\" IS NOT NULL"
        cursor.execute(query)
        # Aplanamos la lista de tuplas a una lista de strings
        values = [str(row[0]) for row in cursor.fetchall()]
        return values
    except sqlite3.Error as e:
        print(f"Error al obtener valores distintos para la columna {column_name}: {e}")
        return []