import asyncio
import duckdb
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional
from pathlib import Path

from app.config.settings import (
    DUCKDB_PATH, 
    DUCKDB_LOG_TABLE, 
    KNOWLEDGE_BASE_DIR
)

logger = logging.getLogger(__name__)

def get_source_file(table_name: str, con: duckdb.DuckDBPyConnection) -> str:
    """Determina el archivo de origen de una tabla basándose en el nombre y el log de ingesta."""
    try:
        log_query = f"""
        SELECT source_file, table_name
        FROM {DUCKDB_LOG_TABLE}
        WHERE table_name = ?
        LIMIT 1
        """
        result = con.execute(log_query, [table_name]).fetchone()
        
        if result:
            file_name, table_name_from_log = result
            # Extraer el nombre de la hoja del nombre de la tabla
            if '_' in table_name:
                parts = table_name.split('_')
                sheet_name = '_'.join(parts[1:])  # Todo después del primer _
            else:
                sheet_name = "Sheet1"
            return f"{file_name} (Sheet: {sheet_name})"
        else:
            # Si no está en el log, inferir del nombre de la tabla
            if '_' in table_name:
                parts = table_name.split('_')
                base_name = parts[0]
                sheet_name = '_'.join(parts[1:])
                return f"{base_name}.xlsx (Sheet: {sheet_name})"
            else:
                return f"{table_name}.xlsx"
                
    except Exception:
        return "Unknown source"

def generate_table_context(table_name: str, con: duckdb.DuckDBPyConnection) -> Dict[str, Any]:
    """Genera contexto completo para una tabla y retorna un diccionario con la información."""
    context = {
        'table_name': table_name,
        'source_file': '',
        'ddl': '',
        'columns': [],
        'row_count': 0,
        'sample_data': None,
        'distinct_values': {},
        'error': None
    }
    
    try:
        # Obtener archivo de origen
        context['source_file'] = get_source_file(table_name, con)
        
        # Obtener DDL
        try:
            ddl_result = con.execute(f"SHOW CREATE TABLE {table_name}").fetchone()
            context['ddl'] = ddl_result[0] if ddl_result else f"CREATE TABLE {table_name} (...);"
        except Exception:
            context['ddl'] = f"CREATE TABLE {table_name} (...);"
        
        # Obtener información de columnas
        columns_info = con.execute(f"DESCRIBE {table_name}").fetchdf()
        context['columns'] = columns_info.to_dict('records')
        
        # Obtener conteo de filas
        count_result = con.execute(f"SELECT COUNT(*) as count FROM {table_name}").fetchone()
        context['row_count'] = count_result[0] if count_result else 0
        
        # Obtener datos de muestra
        if context['row_count'] > 0:
            sample_rows = con.execute(f"SELECT * FROM {table_name} LIMIT 5").fetchdf()
            context['sample_data'] = sample_rows
        
        # Obtener valores únicos para columnas de texto
        for col_info in context['columns']:
            col_name = col_info['column_name']
            col_type = col_info['column_type']
            
            if col_type in ('VARCHAR', 'TEXT'):
                try:
                    query = f'SELECT COUNT(DISTINCT "{col_name}") FROM {table_name}'
                    distinct_count_result = con.execute(query).fetchone()
                    distinct_count = distinct_count_result[0] if distinct_count_result else 0
                
                    if 1 < distinct_count <= 20:
                        values_query = f'SELECT DISTINCT "{col_name}" FROM {table_name} LIMIT 20'
                        values = con.execute(values_query).fetchall()
                        flat_values = [str(v[0]) for v in values if v[0] is not None]
                        context['distinct_values'][col_name] = flat_values
                except Exception:
                    continue
                    
    except Exception as e:
        context['error'] = str(e)

    return context

def generate_embedding_markdown(tables_context: List[Dict[str, Any]]) -> str:
    """Genera documento Markdown optimizado para embeddings con formato de tablas."""
    
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    total_tables = len(tables_context)
    total_rows = sum(ctx.get('row_count', 0) for ctx in tables_context)

    md_content = f"""# DATABASE KNOWLEDGE BASE
Generated: {timestamp}

## DATABASE OVERVIEW
- **Total Tables:** {total_tables}
- **Total Rows:** {total_rows}

---

## TABLE DOCUMENTATION
"""

    for i, context in enumerate(tables_context, 1):
        table_name = context.get('table_name', f'unknown_table_{i}')
        source_file = context.get('source_file', 'Unknown source')
        row_count = context.get('row_count', 0)
        columns = context.get('columns', [])
        ddl = context.get('ddl', f'CREATE TABLE {table_name} (...);')
        sample_data = context.get('sample_data', None)
        distinct_values = context.get('distinct_values', {})

        md_content += f"""
### TABLE {i}: {table_name}

- **SOURCE FILE:** {source_file}
- **ROW COUNT:** {row_count}
- **COLUMN COUNT:** {len(columns)}

#### TABLE STRUCTURE:
```sql
{ddl}
```

#### COLUMN DEFINITIONS:
| Column Name | Data Type | Nullable | Default Value |
|-------------|-----------|----------|---------------|
"""
        for col in columns:
            md_content += f"| {col.get('column_name', '')} | {col.get('column_type', '')} | {col.get('null', '')} | {col.get('column_default', 'None')} |\n"

        if distinct_values:
            md_content += "\n#### UNIQUE VALUES:\n"
            for col_name, values in distinct_values.items():
                # Limitar la cantidad de valores mostrados para no hacer el archivo muy grande
                values_str = ", ".join(values[:15])
                if len(values) > 15:
                    values_str += f" (and {len(values) - 15} more)"
                md_content += f"- **{col_name}:** {values_str}\n"

        md_content += "\n#### SAMPLE DATA (First 5 Records):\n"
        if sample_data is not None and not sample_data.empty:
            # Usar to_markdown() para un formato perfecto
            md_content += sample_data.to_markdown(index=False)
        else:
            md_content += "No sample data available."

        md_content += "\n\n---\n"

    return md_content


async def build_knowledge_base() -> Dict[str, any]:
    """
    Genera la base de conocimiento a partir de las tablas en DuckDB.
    
    Returns:
        Dict con el resultado del proceso
    """
    result = {
        "success": True,
        "tables_processed": 0,
        "markdown_file": None,
        "errors": [],
        "start_time": datetime.now().isoformat(),
        "end_time": None
    }
    
    logger.info("Iniciando construcción de base de conocimiento...")
    
    con = None
    try:
        con = duckdb.connect(database=str(DUCKDB_PATH), read_only=True)
        
        # Obtener lista de tablas
        tables_df = await asyncio.to_thread(con.execute, "SHOW TABLES")
        tables_df = tables_df.fetchdf()
        
        logger.info("Generando documentación de la base de datos...")
        
        tables_context = []
        for row in tables_df.itertuples():
            table_name = row.name
            if table_name == DUCKDB_LOG_TABLE:
                continue
            
            logger.info(f"Procesando tabla: {table_name}")
            table_context = await asyncio.to_thread(generate_table_context, table_name, con)
            tables_context.append(table_context)
            result["tables_processed"] += 1
        
        # Generar Markdown para embeddings
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        embedding_md_content = generate_embedding_markdown(tables_context)
        
        # Guardar archivo
        embedding_md_file = KNOWLEDGE_BASE_DIR / f'database_embedding_{timestamp}.md'
        
        await asyncio.to_thread(
            lambda: embedding_md_file.write_text(embedding_md_content, encoding='utf-8')
        )
        
        result["markdown_file"] = str(embedding_md_file)
        logger.info(f"Base de conocimiento generada: {embedding_md_file}")
        
    except Exception as e:
        error_msg = f"Error al construir base de conocimiento: {e}"
        logger.error(error_msg)
        result["errors"].append(error_msg)
        result["success"] = False
        
    finally:
        if con:
            con.close()
        result["end_time"] = datetime.now().isoformat()
    
    return result