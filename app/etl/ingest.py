import asyncio
import polars as pl
import duckdb
import hashlib
import unicodedata
import re
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from datetime import datetime
import ftfy

from app.config.settings import (
    UPLOADS_DIR, 
    DUCKDB_PATH, 
    DUCKDB_LOG_TABLE
)

logger = logging.getLogger(__name__)

def get_file_hash(file_path: Path) -> str:
    """Genera hash MD5 del archivo para detectar cambios."""
    hasher = hashlib.md5()
    with open(file_path, 'rb') as f:
        buf = f.read()
        hasher.update(buf)
    return hasher.hexdigest()

def clean_dataframe_content(df: pl.DataFrame) -> pl.DataFrame:
    """
    Limpia y repara el contenido de texto de un DataFrame usando ftfy.
    Aplica la corrección a todas las columnas de tipo string (Utf8).
    """
    # Itera solo sobre las columnas que son de tipo texto.
    for col_name in df.select(pl.col(pl.Utf8)).columns:
        df = df.with_columns(
            pl.col(col_name).map_elements(
                # Usa ftfy.fix_text para reparar el texto.
                # Se añade una verificación para no procesar valores nulos.
                lambda text: ftfy.fix_text(text) if isinstance(text, str) else text,
                return_dtype=pl.Utf8
            )
        )
    return df

def normalize_text(text: str) -> str:
    """Normaliza texto removiendo acentos, tildes y caracteres especiales."""
    # Normalizar unicode (NFD) y remover diacríticos
    normalized = unicodedata.normalize('NFD', text)
    # Remover caracteres de combinación (acentos, tildes, etc.)
    ascii_text = ''.join(c for c in normalized if unicodedata.category(c) != 'Mn')
    # Convertir a minúsculas
    ascii_text = ascii_text.lower()
    # Reemplazar caracteres especiales por guiones bajos
    ascii_text = re.sub(r'[^a-z0-9_]', '_', ascii_text)
    # Remover múltiples guiones bajos consecutivos
    ascii_text = re.sub(r'_+', '_', ascii_text)
    # Remover guiones bajos al inicio y final
    ascii_text = ascii_text.strip('_')
    return ascii_text

def clean_column_names(df: pl.DataFrame) -> pl.DataFrame:
    """Limpia nombres de columnas para evitar conflictos SQL."""
    clean_names = {}
    for col in df.columns:
       
        clean_name = normalize_text(col)
        
        
        if not clean_name:
            clean_name = "columna_sin_nombre"
        
        # Evitar nombres duplicados
        counter = 1
        original_name = clean_name
        while clean_name in clean_names.values():
            clean_name = f"{original_name}_{counter}"
            counter += 1
        clean_names[col] = clean_name
    
    return df.rename(clean_names)

def safe_table_name(base_name: str, sheet_name: str) -> str:
    """Genera un nombre de tabla seguro para SQL."""
    safe_base = normalize_text(base_name)
    safe_sheet = normalize_text(sheet_name)
    
    if not safe_base:
        safe_base = "tabla"
    if not safe_sheet:
        safe_sheet = "hoja"
    
    return f"{safe_base}_{safe_sheet}"

def should_process_sheet(filename: str, sheet_name: str) -> bool:
    """
    Determina si una hoja debe ser procesada, basándose en una lista blanca de nombres
    de hojas normalizados. Esta regla se aplica a todos los archivos.
    """
    # Lista de nombres de hojas normalizados que se deben procesar.
    # Estos nombres son el resultado de aplicar `normalize_text` a los nombres
    # de las hojas de cálculo originales que nos interesan.
    allowed_normalized_sheets = {
        "seguimiento",
        "seguimiento_detalles_defecto",
    }
    
    # Normalizar el nombre de la hoja actual para realizar una comparación consistente.
    # Se eliminan espacios, acentos, y se convierte a minúsculas.
    normalized_sheet_name = normalize_text(sheet_name.strip())
    
    # La hoja se procesa solo si su nombre normalizado está en la lista blanca.
    return normalized_sheet_name in allowed_normalized_sheets

async def ingest_excel_files() -> Dict[str, any]:
    """
    Procesa archivos Excel de la carpeta uploads y los ingesta en DuckDB.
    
    Returns:
        Dict con el resultado del proceso (éxito, errores, estadísticas)
    """
    result = {
        "success": True,
        "processed_count": 0,
        "errors": [],
        "start_time": datetime.now().isoformat(),
        "end_time": None
    }
    
    logger.info("Iniciando proceso de ingesta de archivos Excel...")
    
    con = None
    try:
        con = duckdb.connect(database=str(DUCKDB_PATH), read_only=False)
        
        # Crear tabla de log si no existe
        await asyncio.to_thread(con.execute, f"""
        CREATE TABLE IF NOT EXISTS {DUCKDB_LOG_TABLE} (
            table_name VARCHAR PRIMARY KEY,
            source_file VARCHAR,
            file_hash VARCHAR,
            last_processed TIMESTAMP
        )
        """)
        
        # Cargar log existente
        log_data = await asyncio.to_thread(
            lambda: con.execute(f"SELECT table_name, file_hash FROM {DUCKDB_LOG_TABLE}").fetchdf()
        )
        ingestion_log: Dict[str, str] = dict(zip(log_data['table_name'], log_data['file_hash']))
        logger.info(f"Registro de ingesta cargado. Se conocen {len(ingestion_log)} tablas.")
        
        # Iniciar transacción
        await asyncio.to_thread(con.execute, "BEGIN TRANSACTION")
        
        # Procesar archivos Excel
        excel_files = [f for f in UPLOADS_DIR.iterdir() if f.suffix.lower() in ['.xlsx', '.xls']]
        
        if not excel_files:
            logger.warning("No se encontraron archivos Excel en la carpeta uploads.")
            result["success"] = False
            result["errors"].append("No se encontraron archivos Excel para procesar")
            return result
        
        for file_path in excel_files:
            try:
                filename = file_path.name
                current_hash = get_file_hash(file_path)
                
                logger.info(f"Procesando archivo: {filename}")
                
                # Leer todas las hojas del Excel
                excel_sheets = await asyncio.to_thread(
                    pl.read_excel, file_path, sheet_id=0
                )
                
                for sheet_name, df in excel_sheets.items():
                    # Verificar si esta hoja debe ser procesada
                    if not should_process_sheet(filename, sheet_name):
                        logger.info(f"Omitiendo: {filename} / {sheet_name} (regla especial)")
                        continue
                    
                    base_name = file_path.stem
                    table_name = safe_table_name(base_name, sheet_name)
                    
                    is_new = table_name not in ingestion_log
                    is_modified = not is_new and ingestion_log.get(table_name) != current_hash
                    
                    if not (is_new or is_modified):
                        logger.info(f"Sin cambios: {filename} / {sheet_name}")
                        continue
                    
                    action = "NUEVO" if is_new else "ACTUALIZACIÓN"
                    logger.info(f"{action}: {filename} / {sheet_name}")
                    
                    if df.is_empty():
                        logger.warning(f"Hoja vacía, omitiendo: {sheet_name}")
                        continue
                    
                    # Limpiar datos
                    df = df.filter(pl.any_horizontal(pl.all().is_not_null()))
                    df = clean_dataframe_content(df) # <-- ¡NUEVO! Limpia el contenido
                    df = clean_column_names(df)      # Limpia los nombres de columna
                    
                    # Crear tabla en DuckDB
                    try:
                        # Registrar el DataFrame de Polars en DuckDB
                        await asyncio.to_thread(con.register, "df", df)
                        
                        # Crear la tabla usando el DataFrame registrado
                        await asyncio.to_thread(
                            con.execute, 
                            f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM df"
                        )
                        
                        # Limpiar el registro temporal
                        await asyncio.to_thread(con.unregister, "df")
                        
                        # Actualizar log
                        update_query = f"""
                        INSERT INTO {DUCKDB_LOG_TABLE} (table_name, source_file, file_hash, last_processed)
                        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                        ON CONFLICT (table_name) DO UPDATE SET
                            source_file = EXCLUDED.source_file,
                            file_hash = EXCLUDED.file_hash,
                            last_processed = EXCLUDED.last_processed;
                        """
                        await asyncio.to_thread(
                            con.execute, update_query, [table_name, filename, current_hash]
                        )
                        
                        logger.info(f"✅ Tabla '{table_name}' creada exitosamente.")
                        result["processed_count"] += 1
                        
                    except Exception as table_error:
                        error_msg = f"Error al crear tabla {table_name}: {table_error}"
                        logger.error(error_msg)
                        result["errors"].append(error_msg)
                        
                        # Limpiar registro en caso de error
                        try:
                            await asyncio.to_thread(con.unregister, "df")
                        except:
                            pass  # Ignorar si ya no existe
                        
            except Exception as e:
                error_msg = f"Error al procesar archivo {filename}: {e}"
                logger.error(error_msg)
                result["errors"].append(error_msg)
        
        # Confirmar o revertir transacción
        if not result["errors"]:
            await asyncio.to_thread(con.execute, "COMMIT")
            logger.info(f"Proceso finalizado exitosamente. Se procesaron {result['processed_count']} tablas.")
        else:
            await asyncio.to_thread(con.execute, "ROLLBACK")
            logger.error("Proceso falló. Se revirtieron todos los cambios.")
            result["success"] = False
            
    except Exception as e:
        if con:
            try:
                await asyncio.to_thread(con.execute, "ROLLBACK")
            except:
                pass
        error_msg = f"Error crítico: {e}"
        logger.error(error_msg)
        result["errors"].append(error_msg)
        result["success"] = False
        
    finally:
        if con:
            con.close()
        result["end_time"] = datetime.now().isoformat()
        logger.info("Proceso de ingesta completado.")
    
    return result