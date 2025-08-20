import asyncio
import hashlib
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
import json

# Imports para unstructured y procesamiento
try:
    from unstructured.partition.pdf import partition_pdf
    from unstructured.documents.elements import Table, Image, Text
except ImportError:
    partition_pdf = None
    Table = Image = Text = None

import google.generativeai as genai
from PIL import Image as PILImage
import base64
import io

from app.config.settings import (
    UPLOADS_DIR,
    DOCSTORE_PATH,
    ENABLE_MULTIMODAL,
    VISION_MODEL,
    GEMINI_API_KEY,
    LOGS_DIR
)
from app.etl.vectorize import vectorize_multimodal_documents

logger = logging.getLogger(__name__)

def configure_gemini_vision():
    """Configura Gemini para procesamiento de imágenes."""
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY no encontrada")
    genai.configure(api_key=GEMINI_API_KEY)
    return True

def get_file_hash(file_path: Path) -> str:
    """Genera hash MD5 del archivo para evitar reprocesamiento."""
    hasher = hashlib.md5()
    with open(file_path, 'rb') as f:
        hasher.update(f.read())
    return hasher.hexdigest()

def save_table_to_docstore(table_element, doc_id: str) -> str:
    """Guarda tabla como Markdown en el docstore."""
    try:
        table_dir = DOCSTORE_PATH / "tables"
        table_dir.mkdir(parents=True, exist_ok=True)
        
        # Estrategia mejorada para convertir tabla a Markdown
        if hasattr(table_element, 'metadata') and hasattr(table_element.metadata, 'text_as_html') and table_element.metadata.text_as_html:
            # Opción 1: Si tenemos HTML, convertir a Markdown
            try:
                import html2text
                h = html2text.HTML2Text()
                h.ignore_links = True
                h.ignore_images = True
                h.body_width = 0  # No wrap text
                markdown_content = h.handle(table_element.metadata.text_as_html)
            except ImportError:
                # Fallback si no hay html2text
                markdown_content = f"```\n{table_element.text}\n```"
        else:
            # Opción 2: Procesar texto plano de manera inteligente
            text_content = table_element.text
            lines = text_content.split('\n')
            
            # Intentar detectar si parece una tabla
            if len(lines) > 1:
                # Buscar patrones comunes de tabla
                table_lines = []
                for line in lines:
                    line = line.strip()
                    if line:  # Solo líneas no vacías
                        # Reemplazar múltiples espacios con separador de tabla
                        cleaned_line = ' | '.join(line.split())
                        table_lines.append(f"| {cleaned_line} |")
                
                if table_lines:
                    # Añadir header separator para Markdown
                    if len(table_lines) > 1:
                        header_sep = "|" + "|".join([" --- " for _ in table_lines[0].split('|')[1:-1]]) + "|"
                        markdown_content = f"{table_lines[0]}\n{header_sep}\n" + "\n".join(table_lines[1:])
                    else:
                        markdown_content = "\n".join(table_lines)
                else:
                    markdown_content = f"```\n{text_content}\n```"
            else:
                markdown_content = f"```\n{text_content}\n```"
        
        table_file = table_dir / f"table_{doc_id}.md"
        table_file.write_text(markdown_content, encoding='utf-8')
        
        logger.info(f"Tabla guardada: {table_file}")
        return f"tables/table_{doc_id}.md"
        
    except Exception as e:
        logger.error(f"Error guardando tabla {doc_id}: {e}")
        return ""

def save_image_to_docstore(image_element, doc_id: str) -> str:
    """Guarda imagen en el docstore."""
    try:
        image_dir = DOCSTORE_PATH / "images"
        image_dir.mkdir(parents=True, exist_ok=True)
        
        # Obtener datos de la imagen
        if hasattr(image_element, 'metadata') and hasattr(image_element.metadata, 'image_base64'):
            image_data = base64.b64decode(image_element.metadata.image_base64)
            image_file = image_dir / f"image_{doc_id}.png"
            
            with open(image_file, 'wb') as f:
                f.write(image_data)
                
            logger.info(f"Imagen guardada: {image_file}")
            return f"images/image_{doc_id}.png"
            
    except Exception as e:
        logger.error(f"Error guardando imagen {doc_id}: {e}")
        
    return ""

async def summarize_table_with_llm(table_text: str) -> str:
    """Genera resumen de tabla usando el LLM."""
    try:
        from app.agent.shared import answer_llm
        
        prompt = f"""Analiza la siguiente tabla y genera un resumen conciso describiendo:
1. Qué tipo de datos contiene
2. Información clave o patrones relevantes
3. Posibles insights para análisis de negocio

Tabla:
{table_text[:1000]}...

Resumen:"""
        
        response = await answer_llm.ainvoke(prompt)
        return response.content.strip()
        
    except Exception as e:
        logger.error(f"Error generando resumen de tabla: {e}")
        return f"Tabla con datos tabulares: {table_text[:200]}..."

async def summarize_image_with_vision(image_path: str) -> str:
    """Genera resumen de imagen usando Gemini Vision."""
    try:
        configure_gemini_vision()
        
        # Cargar imagen
        with open(DOCSTORE_PATH / image_path, 'rb') as f:
            image_data = f.read()
        
        # Preparar para Gemini
        image = PILImage.open(io.BytesIO(image_data))
        
        prompt = """Analiza esta imagen y describe:
1. Qué tipo de contenido muestra (gráfico, diagrama, foto, etc.)
2. Elementos clave visibles
3. Información relevante para análisis de negocio o reportes

Descripción:"""
        
        model = genai.GenerativeModel(VISION_MODEL)
        response = await asyncio.to_thread(
            model.generate_content, 
            [prompt, image]
        )
        
        return response.text.strip()
        
    except Exception as e:
        logger.error(f"Error generando resumen de imagen: {e}")
        return f"Imagen del documento (ubicada en {image_path})"

async def process_pdf_with_strategy(pdf_path: Path, strategy: str) -> List:
    """Procesa PDF con una estrategia específica."""
    logger.info(f"Intentando estrategia '{strategy}' para {pdf_path.name}")
    
    strategy_config = {
        "hi_res": {
            "strategy": "hi_res",
            "infer_table_structure": True,
            "chunking_strategy": "by_title",
            "languages": ['spa', 'eng']
        },
        "ocr_only": {
            "strategy": "ocr_only",
            "infer_table_structure": True,
            "languages": ['spa', 'eng']
        }
    }
    
    config = strategy_config.get(strategy, strategy_config["hi_res"])
    
    elements = await asyncio.to_thread(
        partition_pdf,
        str(pdf_path),
        **config
    )
    
    logger.info(f"Estrategia '{strategy}': {len(elements)} elementos extraídos")
    return elements

async def analyze_elements(elements: List) -> Dict[str, int]:
    """Analiza los tipos de elementos encontrados."""
    analysis = {"Table": 0, "Image": 0, "Text": 0, "Other": 0}
    
    for element in elements:
        if isinstance(element, Table):
            analysis["Table"] += 1
        elif isinstance(element, Image):
            analysis["Image"] += 1
        elif hasattr(element, 'text') and element.text.strip():
            analysis["Text"] += 1
        else:
            analysis["Other"] += 1
    
    return analysis

async def process_pdf_document(pdf_path: Path) -> Dict[str, Any]:
    """Procesa un documento PDF con estrategias múltiples para mejor extracción."""
    result = {
        "success": False,
        "file_path": str(pdf_path),
        "documents": [],
        "elements_processed": 0,
        "errors": [],
        "strategies_tried": []
    }
    
    if not partition_pdf:
        result["errors"].append("Librería 'unstructured' no instalada")
        return result
    
    try:
        logger.info(f"Procesando PDF: {pdf_path}")
        
        # Estrategia 1: hi_res (rápida, buena para imágenes)
        try:
            elements_hi_res = await process_pdf_with_strategy(pdf_path, "hi_res")
            analysis_hi_res = await analyze_elements(elements_hi_res)
            result["strategies_tried"].append({"strategy": "hi_res", "analysis": analysis_hi_res})
            
            # Si hi_res encuentra tablas o tenemos suficientes elementos, usarla
            if analysis_hi_res["Table"] > 0 or analysis_hi_res["Image"] > 0:
                logger.info("Estrategia hi_res exitosa, usando esos elementos")
                elements = elements_hi_res
            else:
                # Estrategia 2: ocr_only (más lenta, mejor para tablas complejas)
                logger.info("hi_res no encontró tablas, intentando ocr_only...")
                elements_ocr = await process_pdf_with_strategy(pdf_path, "ocr_only")
                analysis_ocr = await analyze_elements(elements_ocr)
                result["strategies_tried"].append({"strategy": "ocr_only", "analysis": analysis_ocr})
                
                # Usar la estrategia que encontró más elementos estructurados
                if analysis_ocr["Table"] > analysis_hi_res["Table"]:
                    logger.info("ocr_only encontró más tablas, usando esos elementos")
                    elements = elements_ocr
                else:
                    logger.info("Manteniendo elementos de hi_res")
                    elements = elements_hi_res
                    
        except Exception as e:
            logger.warning(f"Error en estrategias múltiples: {e}, usando hi_res básico")
            elements = await process_pdf_with_strategy(pdf_path, "hi_res")
        
        logger.info(f"Elementos finales: {len(elements)}")
        
        # Procesar cada elemento
        for i, element in enumerate(elements):
            doc_id = f"{pdf_path.stem}_{uuid.uuid4().hex[:8]}"
            
            try:
                if isinstance(element, Table):
                    # Procesar tabla
                    docstore_path = save_table_to_docstore(element, doc_id)
                    summary = await summarize_table_with_llm(element.text)
                    
                    doc = {
                        "content": summary,
                        "source_id": doc_id,
                        "doc_type": "Table",
                        "source_file": pdf_path.name,
                        "docstore_path": docstore_path,
                        "element_index": i,
                        "created_at": datetime.now().isoformat()
                    }
                    
                elif isinstance(element, Image):
                    # Procesar imagen
                    docstore_path = save_image_to_docstore(element, doc_id)
                    if docstore_path:
                        summary = await summarize_image_with_vision(docstore_path)
                    else:
                        summary = "Imagen extraída del documento"
                    
                    doc = {
                        "content": summary,
                        "source_id": doc_id,
                        "doc_type": "Image", 
                        "source_file": pdf_path.name,
                        "docstore_path": docstore_path,
                        "element_index": i,
                        "created_at": datetime.now().isoformat()
                    }
                    
                else:
                    # Elemento de texto - filtrar para evitar duplicados
                    text_content = element.text.strip()
                    
                    # Solo procesar textos sustanciales y no duplicados
                    if len(text_content) > 50:  # Mínimo 50 caracteres
                        # Verificar si ya tenemos texto similar
                        is_duplicate = False
                        for existing_doc in result["documents"]:
                            if existing_doc["doc_type"] == "Text":
                                # Comparación simple de similitud
                                existing_text = existing_doc["content"][:100]
                                new_text = text_content[:100]
                                if existing_text == new_text:
                                    is_duplicate = True
                                    break
                        
                        if not is_duplicate:
                            doc = {
                                "content": text_content,
                                "source_id": doc_id,
                                "doc_type": "Text",
                                "source_file": pdf_path.name,
                                "docstore_path": "",
                                "element_index": i,
                                "created_at": datetime.now().isoformat()
                            }
                        else:
                            logger.debug(f"Texto duplicado omitido en elemento {i}")
                            continue
                    else:
                        logger.debug(f"Texto muy corto omitido en elemento {i}: {len(text_content)} chars")
                        continue
                
                result["documents"].append(doc)
                result["elements_processed"] += 1
                
                logger.info(f"Procesado elemento {i+1}/{len(elements)}: {doc['doc_type']}")
                
            except Exception as e:
                error_msg = f"Error procesando elemento {i}: {e}"
                logger.error(error_msg)
                result["errors"].append(error_msg)
        
        result["success"] = True
        logger.info(f"PDF procesado exitosamente: {result['elements_processed']} elementos")
        
    except Exception as e:
        error_msg = f"Error crítico procesando PDF {pdf_path}: {e}"
        logger.error(error_msg)
        result["errors"].append(error_msg)
    
    return result

async def process_pdf_documents() -> Dict[str, Any]:
    """Procesa todos los PDFs en la carpeta uploads y los vectoriza."""
    result = {
        "success": True,
        "processed_count": 0,
        "vectorized_count": 0,
        "errors": [],
        "start_time": datetime.now().isoformat(),
        "end_time": None
    }
    
    if not ENABLE_MULTIMODAL:
        result["errors"].append("Funcionalidad multimodal deshabilitada")
        result["success"] = False
        return result
    
    logger.info("Iniciando procesamiento de documentos PDF...")
    
    try:
        # Buscar archivos PDF
        pdf_files = list(UPLOADS_DIR.glob("*.pdf"))
        
        if not pdf_files:
            logger.warning("No se encontraron archivos PDF")
            result["errors"].append("No se encontraron archivos PDF para procesar")
            return result
        
        all_documents = []
        
        # Procesar cada PDF
        for pdf_file in pdf_files:
            pdf_result = await process_pdf_document(pdf_file)
            
            if pdf_result["success"]:
                all_documents.extend(pdf_result["documents"])
                result["processed_count"] += 1
                logger.info(f"PDF procesado: {pdf_file.name}")
            else:
                result["errors"].extend(pdf_result["errors"])
        
        # Vectorizar todos los documentos
        if all_documents:
            logger.info(f"Vectorizando {len(all_documents)} documentos...")
            
            vectorize_result = await vectorize_multimodal_documents(all_documents)
            
            if vectorize_result["success"]:
                result["vectorized_count"] = vectorize_result["vectorized_count"]
                logger.info(f"Vectorización exitosa: {result['vectorized_count']} documentos")
            else:
                result["errors"].extend(vectorize_result["errors"])
                result["success"] = False
        
        # Guardar log del procesamiento
        log_file = LOGS_DIR / f"multimodal_processing_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Log guardado en: {log_file}")
        
    except Exception as e:
        error_msg = f"Error crítico en procesamiento multimodal: {e}"
        logger.error(error_msg)
        result["errors"].append(error_msg)
        result["success"] = False
    
    finally:
        result["end_time"] = datetime.now().isoformat()
    
    return result