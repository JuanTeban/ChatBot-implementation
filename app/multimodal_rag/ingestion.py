from __future__ import annotations
import json, uuid, hashlib
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
from bs4 import BeautifulSoup
import logging
import asyncio
import chromadb
import google.generativeai as genai
from datetime import datetime

from app.config.settings import (
    VECTOR_STORE_DIR,
    CHROMA_COLLECTIONS,
    EMBEDDING_MODEL_NAME,
    GEMINI_API_KEY,
    DATA_STORE_PATH
)

log = logging.getLogger("mmrag.ingestion")


MULTIMODAL_LOG_FILE = DATA_STORE_PATH / "logs" / "multimodal_ingestion_log.json"

def configure_gemini():
    """Configura la API de Gemini."""
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY no encontrada en las variables de entorno")
    genai.configure(api_key=GEMINI_API_KEY)
    log.info("SDK de Gemini configurado para multimodal ingestion.")
    return GEMINI_API_KEY

def get_file_hash(file_path: Path) -> str:
    """Genera hash SHA256 del archivo para detectar cambios."""
    hasher = hashlib.sha256()
    with open(file_path, 'rb') as f:
        buf = f.read()
        hasher.update(buf)
    return hasher.hexdigest()

# ---------- Función para limpiar colección ----------
async def clear_multimodal_collection():
    """Limpia completamente la colección de evidencia multimodal."""
    try:
        chroma_client = chromadb.PersistentClient(path=str(VECTOR_STORE_DIR))
        collection_name = CHROMA_COLLECTIONS["multimodal_evidence"]
        
        try:
            collection = chroma_client.get_collection(name=collection_name)
            # Obtener todos los IDs
            all_data = collection.get(include=[])
            if all_data["ids"]:
                collection.delete(ids=all_data["ids"])
                log.info(f"✅ Colección {collection_name} limpiada: {len(all_data['ids'])} chunks eliminados")
                return {"success": True, "deleted_chunks": len(all_data["ids"])}
            else:
                log.info(f"Colección {collection_name} ya estaba vacía")
                return {"success": True, "deleted_chunks": 0}
                
        except Exception:
            log.info(f"Colección {collection_name} no existe")
            return {"success": True, "deleted_chunks": 0}
            
    except Exception as e:
        log.error(f"Error limpiando colección: {e}")
        return {"success": False, "error": str(e)}

# ---------- Particionado (Unstructured) ----------
def partition_file(path: Path):
    """
    Particiona archivos usando Unstructured.
    Procesa texto, tablas E imágenes.
    """
    ext = path.suffix.lower()
    try:
        if ext == ".pdf":
            from unstructured.partition.pdf import partition_pdf
            return partition_pdf(
                filename=str(path),
                strategy="hi_res",
                infer_table_structure=True,
                # ✅ EXTRAER IMÁGENES
                extract_image_block_types=["Image"],
                extract_image_block_to_payload=True,
            )
        elif ext == ".docx":
            # 🔧 SOLUCIÓN ALTERNATIVA: Usar python-docx para extraer imágenes
            elements = extract_docx_with_images(path)
            return elements
        else:
            from unstructured.partition.auto import partition
            return partition(filename=str(path))
    except Exception as e:
        log.exception("Error particionando %s: %s", path, e)
        return []

def extract_docx_with_images(path: Path):
    """
    Extrae contenido de DOCX incluyendo imágenes usando python-docx.
    """
    try:
        import zipfile
        import io
        from PIL import Image as PILImage
        from unstructured.documents.elements import Image
        
        # Primero extraer con Unstructured para texto y tablas
        from unstructured.partition.docx import partition_docx
        elements = partition_docx(filename=str(path), extract_images_in_docx=False)
        
        # Buscar imágenes en el ZIP del DOCX
        images_found = []
        try:
            with zipfile.ZipFile(path, 'r') as zip_file:
                image_files = [f for f in zip_file.namelist() if f.startswith('word/media/')]
                
                for img_file in image_files:
                    try:
                        # Leer imagen del ZIP
                        img_data = zip_file.read(img_file)
                        pil_image = PILImage.open(io.BytesIO(img_data))
                        
                        # Crear elemento Image de Unstructured con metadata simple
                        class SimpleMetadata:
                            def __init__(self, image, image_path):
                                self.image = image
                                self.image_path = image_path
                        
                        image_element = Image(
                            text=f"[IMAGEN] {img_file}",
                            metadata=SimpleMetadata(pil_image, img_file)
                        )
                        images_found.append(image_element)
                        log.info(f"🖼️ IMAGEN EXTRAÍDA: {img_file} ({pil_image.size})")
                        
                    except Exception as e:
                        log.warning(f"Error procesando imagen {img_file}: {e}")
                        
        except Exception as e:
            log.warning(f"Error leyendo ZIP del DOCX: {e}")
        
        # Combinar elementos de texto/tablas con imágenes
        all_elements = elements + images_found
        log.info(f"📦 DOCX procesado: {len(elements)} elementos + {len(images_found)} imágenes")
        
        return all_elements
        
    except Exception as e:
        log.error(f"Error en extract_docx_with_images: {e}")
        # Fallback a Unstructured normal
        from unstructured.partition.docx import partition_docx
        return partition_docx(filename=str(path), extract_images_in_docx=False)

# ---------- Split de elementos (texto, tablas e imágenes) ----------
def split_elements(elements) -> Tuple[List, List, List]:
    """
    Filtra ruido y conserva texto, tablas E imágenes.
    Procesa TODAS las imágenes.
    """
    texts, tables, images = [], [], []
    
    for el in elements:
        element_type = str(type(el).__name__)
        element_text = str(el).strip()
        
        # 🚫 FILTRAR RUIDO ESPECÍFICO
        if should_skip_element(element_text, element_type):
            log.debug(f"Filtrado: [{element_type}] {element_text[:50]}...")
            continue
        
        # ✅ CLASIFICAR CONTENIDO ÚTIL (texto, tablas E imágenes)
        if "Table" in str(type(el)):
            tables.append(el)
        elif "Image" in str(type(el)):
            # ✅ PROCESAR IMÁGENES
            log.debug(f"Procesando imagen: {element_text[:50]}...")
            images.append(el)
        elif "CompositeElement" in str(type(el)):
            texts.append(el)
        else:
            texts.append(el)
    
    log.info(f"Split -> texts={len(texts)}, tables={len(tables)}, images={len(images)}")
    return texts, tables, images

def should_skip_element(element_text: str, element_type: str) -> bool:
    """
    Filtrar SOLO ruido real - conservar títulos descriptivos importantes.
    """
    # 🚫 Tipos de elementos que son ruido automáticamente
    noise_types = ["Header", "Footer", "PageBreak"]
    if element_type in noise_types:
        return True
    
    # 🚫 Patrones MUY específicos de ruido (NO títulos descriptivos)
    element_lower = element_text.lower().strip()
    
    # Solo filtrar si es exactamente un patrón de ruido Y es texto corto
    exact_noise_patterns = [
        "página 2 de 2",                    # Footer paginación exacto
        "página 1 de 2",                    # Footer paginación exacto  
        "grupo epm",                        # Header corporativo solo
        "ibm",                              # Header corporativo solo
    ]
    
    # Header repetitivo COMPLETO del proyecto (muy específico)
    if "proyecto saphiro evidencia hallazgo migración de datos" in element_lower:
        return True
    
    # Filtrar solo si es EXACTAMENTE uno de estos patrones Y es muy corto
    for pattern in exact_noise_patterns:
        if element_lower == pattern:  # ✅ EXACTO, no parcial
            return True
    
    return False

# ---------- Conversión de tablas a Markdown ----------
def convert_tables_to_markdown(tables: List[Any]) -> List[str]:
    """
    Parser robusto para tablas corporativas.
    """
    markdown_tables = []
    
    for idx, t in enumerate(tables):
        html_content = getattr(t.metadata, "text_as_html", None) or str(t)
        
        try:
            soup = BeautifulSoup(html_content, "lxml")
            rows_data = []
            
            # Extraer TODAS las filas sin asumir estructura
            all_trs = soup.select("tr")
            
            for row_idx, tr in enumerate(all_trs):
                cells = tr.select("th, td")
                row_content = []
                
                for cell_idx, cell in enumerate(cells):
                    # Extraer TODO el texto de cada celda
                    cell_text = cell.get_text(" ", strip=True)
                    # Limpiar espacios múltiples pero conservar contenido
                    cell_text = " ".join(cell_text.split())
                    row_content.append(cell_text)
                
                # Solo descartar filas completamente vacías
                if any(content.strip() for content in row_content):
                    rows_data.append(row_content)
            
            if not rows_data:
                markdown_tables.append("Tabla completamente vacía")
                continue
            
            # 🏗️ CONSTRUCCIÓN INTELIGENTE DE MARKDOWN
            md_lines = []
            max_cols = max(len(row) for row in rows_data) if rows_data else 0
            
            if len(rows_data) == 1:
                # ✅ TABLA DE 1 FILA: Formato especial para headers/títulos
                single_row = rows_data[0]
                
                # Formatear como información clave (no como tabla con headers)
                if len(single_row) == 1:
                    # Una sola celda - probablemente un título de sección
                    md_lines.append(f"**{single_row[0]}**")
                else:
                    # Múltiples celdas - formatear como línea de datos
                    md_lines.append(" | ".join(single_row))
                
            else:
                # ✅ TABLA MULTI-FILA: Primera fila como header, resto como datos
                header_row = rows_data[0]
                # Normalizar header a max_cols
                while len(header_row) < max_cols:
                    header_row.append("Campo")
                
                header = " | ".join(header_row)
                separator = " | ".join(["---"] * len(header_row))
                
                md_lines.append(header)
                md_lines.append(separator)
                
                # Procesar filas de datos
                for data_idx, row in enumerate(rows_data[1:], 1):
                    # Normalizar fila a mismo número de columnas que header
                    while len(row) < len(header_row):
                        row.append("")
                    # Truncar si tiene más columnas
                    content_row = " | ".join(row[:len(header_row)])
                    md_lines.append(content_row)
            
            markdown_result = "\n".join(md_lines)
            markdown_tables.append(markdown_result if markdown_result.strip() else "Tabla sin contenido procesable")
            
        except Exception as e:
            log.warning(f"Error en tabla {idx+1}: {e}")
            
            # Fallback más robusto
            try:
                # Extraer texto plano como último recurso
                plain_text = BeautifulSoup(html_content, "lxml").get_text(separator=" | ", strip=True)
                clean_text = " ".join(plain_text.split())
                if clean_text:
                    markdown_tables.append(f"**Contenido extraído:** {clean_text}")
                else:
                    markdown_tables.append("Tabla (error total de procesamiento)")
            except Exception as e2:
                log.error(f"Fallback completo falló para tabla {idx+1}: {e2}")
                markdown_tables.append("Tabla (error total de procesamiento)")
    
    return markdown_tables


def process_images_with_gemini(images: List[Any]) -> List[str]:
    """
    Procesa imágenes con Gemini Vision API.
    """
    if not images:
        return []
    
    log.info(f"PROCESANDO {len(images)} IMÁGENES CON GEMINI VISION")
    
    image_descriptions = []
    

    try:
        from PIL import Image
        import io
        from app.multimodal_rag.config import get_vision_model
        vision = get_vision_model()
    except ImportError as e:
        log.error(f"Error importando dependencias de visión: {e}")
        return []
    
    for idx, img in enumerate(images, 1):
        try:
            
            image_data = getattr(getattr(img, "metadata", None), "image", None) or getattr(img, "image", None)
            if image_data is None:
                log.warning(f"Imagen {idx}: sin payload utilizable")
                continue

            if isinstance(image_data, (bytes, bytearray)):
                pil_img = Image.open(io.BytesIO(image_data)).convert("RGB")
            elif isinstance(image_data, Image.Image):
                pil_img = image_data
            else:
                log.warning(f"Imagen {idx}: tipo no soportado: {type(image_data)}")
                continue

            vision_prompt = (
                "Analiza esta captura de SAP: resume técnicamente la interfaz, errores visibles y elementos "
                "relevantes (timeouts, jobs, configuraciones). Dame una Respuesta técnica y estructurada."
            )
            description = vision.describe_image(pil_img, prompt=vision_prompt)
            if not description:
                description = "Descripción no disponible (modelo de visión no devolvió texto)."

            image_descriptions.append(f"[IMAGEN] {description.strip()}")
            log.info(f"✅ Imagen {idx} procesada")

        except Exception as e:
            log.error(f"❌ Error procesando imagen {idx}: {e}")
            image_descriptions.append(f"[IMAGEN] Error de procesamiento: {e}")
    
    return image_descriptions

# ---------- Procesamiento y agrupación de elementos ----------
def process_and_group_elements(elements: List[Any]) -> Tuple[List[str], List[str]]:
    """
    NUEVA ESTRATEGIA: Chunking Jerárquico Inteligente
    - Identifica títulos/subtítulos
    - Agrupa cada título con la tabla que le sigue inmediatamente
    - Crea chunks completos con contexto semántico rico
    - Procesa texto, tablas E imágenes
    """
    contextual_chunks, chunk_types = [], []

    # Primero separar elementos por tipo
    texts, tables, images = split_elements(elements)
    
    # Procesar imágenes con Gemini Vision
    image_descriptions = process_images_with_gemini(images)  # <- genera descripciones
    
    # Procesar elementos secuencialmente para detectar patrones
    i = 0
    while i < len(elements):
        el = elements[i]
        etype = str(type(el).__name__)
        etext = str(el).strip()
        
        # --- Filtrado de Ruido ---
        if etype in ["Header", "Footer", "PageBreak"]:
            i += 1
            continue
            
        if not etext or len(etext) < 5:
            i += 1
            continue
        
        # --- DETECCIÓN DE PATRONES CONTEXTUALES ---
        
        # Caso 1: Elemento de texto seguido de tabla (¡ESTE ES EL PATRÓN CLAVE!)
        if "Table" not in etype and "Image" not in etype:
            # Buscar si hay una tabla en los próximos elementos
            context_text = etext
            j = i + 1
            
            # Acumular texto adicional hasta encontrar una tabla
            while j < len(elements):
                next_el = elements[j]
                next_type = str(type(next_el).__name__)
                next_text = str(next_el).strip()
                
                if "Table" in next_type:
                    # ¡BINGO! Encontramos texto seguido de tabla
                    log.info(f"🎯 PATRÓN DETECTADO: '{context_text[:50]}...' + TABLA")
                    
                    # Extraer contenido de la tabla
                    html_content = getattr(next_el.metadata, "text_as_html", "") or str(next_el)
                    try:
                        # Usar tu parser robusto que SÍ mantiene estructura
                        md_tables = convert_tables_to_markdown([next_el])
                        md_table = md_tables[0] if md_tables else ""
                        
                        # CREAR CHUNK CONTEXTUAL UNIFICADO (conservando saltos de línea)
                        unified_chunk = f"{context_text}\n\n{md_table}"
                        contextual_chunks.append(unified_chunk)
                        chunk_types.append("table")  # texto + tabla
                        
                        log.info(f"✅ CHUNK CONTEXTUAL CREADO ({len(unified_chunk)} chars)")
                        
                    except Exception as e:
                        log.error(f"❌ Error procesando tabla: {e}")
                        # Fallback: usar texto plano
                        plain_text = BeautifulSoup(html_content, "lxml").get_text(separator=" | ", strip=True)
                        clean_text = " ".join(plain_text.split())
                        unified_chunk = f"{context_text}\n\nTabla: {clean_text}"
                        contextual_chunks.append(unified_chunk)
                        chunk_types.append("table")  # texto + tabla
                    
                    # Saltar la tabla ya procesada
                    i = j + 1
                    break
                    
                elif next_text and len(next_text) >= 5 and "Header" not in next_type and "Footer" not in next_type:
                    # Acumular más contexto de texto
                    context_text += f"\n{next_text}"
                    j += 1
                else:
                    j += 1
            else:
                # No se encontró tabla, agregar solo el texto
                if len(context_text) > 20:  # Solo chunks sustanciales
                    contextual_chunks.append(context_text)
                    chunk_types.append("text")  # solo texto
                    log.info(f"📝 CHUNK DE TEXTO: {context_text[:100]}...")
                i += 1
        
        # Caso 2: Tabla independiente (sin contexto previo)
        elif "Table" in etype:
            html_content = getattr(el.metadata, "text_as_html", "") or str(el)
            try:
                # Usar markdownify para convertir HTML a Markdown
                from markdownify import markdownify as md
                md_table = md(html_content, heading_style="ATX")
                clean_table = " ".join(md_table.split())
                contextual_chunks.append(f"Tabla independiente:\n{md_table}")
                chunk_types.append("table")  # tabla independiente
                log.info(f"📋 TABLA INDEPENDIENTE: {clean_table[:100]}...")
            except Exception:
                plain_text = BeautifulSoup(html_content, "lxml").get_text(separator=" | ", strip=True)
                clean_text = " ".join(plain_text.split())
                contextual_chunks.append(f"Tabla: {clean_text}")
                chunk_types.append("table")  # tabla independiente
            i += 1
            
        # Caso 3: CompositeElement
        elif "CompositeElement" in etype:
            contextual_chunks.append(etext)
            chunk_types.append("text")  # composite element = texto
            i += 1
        else:
            i += 1

    # Agregar al final descripciones de imágenes:
    for desc in image_descriptions:
        contextual_chunks.append(desc)
        chunk_types.append("image")

    # Deduplicado (mantén tipos alineados)
    final_chunks, final_types, seen = [], [], set()
    for chunk, ctype in zip(contextual_chunks, chunk_types):
        key = (ctype, chunk)
        if chunk and len(chunk.strip()) > 20 and key not in seen:
            seen.add(key)
            final_chunks.append(chunk.strip())
            final_types.append(ctype)

    log.info(f"🎉 RESUMEN CHUNKING CONTEXTUAL: {len(final_chunks)} chunks (incluye {chunk_types.count('image')} imágenes)")
    return final_chunks, final_types

# ---------- Vectorización en ChromaDB ----------
async def vectorize_multimodal_content(
    content_chunks: List[str], 
    metadatas: List[Dict], 
    collection_name: str = "multimodal_evidence"
) -> int:
    """
    Vectoriza contenido multimodal en ChromaDB.
    Sigue el patrón de business_rules.py
    """
    if not content_chunks:
        return 0
    
    log.info(f"🔧 VECTORIZANDO {len(content_chunks)} CHUNKS:")
    log.info("="*80)
    
    try:
        # Configurar Gemini
        configure_gemini()
        
        # Conectar a ChromaDB
        chroma_client = chromadb.PersistentClient(path=str(VECTOR_STORE_DIR))
        
        # Obtener o crear colección
        try:
            collection = chroma_client.get_collection(name=collection_name)
            log.info(f"✅ Colección {collection_name} obtenida")
        except Exception:
            collection = chroma_client.create_collection(
                name=collection_name,
                metadata={"description": "Multimodal Evidence for Report Generation"}
            )
            log.info(f"✅ Colección {collection_name} creada")
        
        # Vectorizar cada chunk
        vectorized_count = 0
        
        for i, (chunk, metadata) in enumerate(zip(content_chunks, metadatas), 1):
            try:
                chunk_id = str(uuid.uuid4())
                
                # Generar embedding con Gemini
                log.info(f"Generando embedding para chunk {i}/{len(content_chunks)}...")
                embedding_response = await asyncio.to_thread(
                    genai.embed_content,
                    model=EMBEDDING_MODEL_NAME,
                    content=chunk,
                    task_type="RETRIEVAL_DOCUMENT"
                )
                embedding = embedding_response["embedding"]
                
                # Metadatos completos
                full_metadata = {
                    "chunk_id": chunk_id,
                    "content_length": len(chunk),
                    "embedding_size": len(embedding),
                    "created_at": datetime.now().isoformat(),
                    "chunk_index": i,
                    **metadata
                }
                
                # Guardar en ChromaDB
                await asyncio.to_thread(
                    collection.add,
                    embeddings=[embedding],
                    documents=[chunk],
                    ids=[chunk_id],
                    metadatas=[full_metadata]
                )
                
                vectorized_count += 1
                log.info(f"✅ Chunk {i} vectorizado: {chunk[:50]}...")
                
            except Exception as e:
                log.error(f"❌ Error vectorizando chunk {i}: {e}")
        
        log.info(f"✅ VECTORIZACIÓN COMPLETADA: {vectorized_count} chunks guardados")
        log.info("="*80)
        
        return vectorized_count
        
    except Exception as e:
        log.error(f"❌ Error crítico en vectorización: {e}")
        import traceback
        log.error(f"Traceback: {traceback.format_exc()}")
        return 0

# ---------- Metadata helper ----------
def mkmeta(element_type: str, responsable: str, defecto: str, source_file: Path) -> Dict:
    return {
        "element_type": element_type,
        "responsable": responsable,
        "defecto": defecto,
        "source_file": source_file.name,
        "source_path": str(source_file),
    }

# ---------- Logging helper ----------
def save_multimodal_log(log_data: Dict):
    """Guarda el log de procesamiento multimodal."""
    try:
        MULTIMODAL_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(MULTIMODAL_LOG_FILE, 'w', encoding='utf-8') as f:
            json.dump(log_data, f, indent=2, ensure_ascii=False)
        log.info(f"Log guardado en: {MULTIMODAL_LOG_FILE}")
    except Exception as e:
        log.error(f"Error al guardar log: {e}")

# ---------- Proceso principal ----------
async def ingest_tree(
    root: Path,
    responsable: Optional[str] = None,
    defecto: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Recorre root/responsable/defecto y procesa todos los archivos.
    SOLO procesa texto y tablas - NO imágenes.
    """
    root = root.resolve()
    log.info(f"[INGEST] root={root} responsable={responsable} defecto={defecto}")

    # Inicializar log
    log_data = {
        'timestamp': datetime.now().isoformat(),
        'root_path': str(root),
        'responsable': responsable,
        'defecto': defecto,
        'validation': {'success': True},
        'processing': {'total_files': 0, 'successful': 0, 'errors': []},
        'vectorization': {'total_chunks': 0, 'successful': 0, 'errors': [], 'details': []}
    }

    processed_files = 0
    successful_files = 0
    total_chunks = 0
    successful_chunks = 0

    try:
        responsables = [responsable] if responsable else [d.name for d in root.iterdir() if d.is_dir()]
        
        for r in responsables:
            r_dir = root / r
            if not r_dir.exists():
                log.warning(f"Responsable no encontrado: {r_dir}")
                continue
                
            defectos = [defecto] if defecto else [d.name for d in r_dir.iterdir() if d.is_dir()]
            
            for d in defectos:
                d_dir = r_dir / d
                if not d_dir.exists():
                    log.warning(f"Defecto no encontrado: {d_dir}")
                    continue

                log.info(f"[INGEST] Procesando responsable={r} defecto={d}")
                
                # Buscar archivos dentro de subcarpetas (fechas) y/o sueltos
                files: List[Path] = []
                for item in d_dir.iterdir():
                    if item.is_dir():
                        for fp in item.iterdir():
                            if fp.is_file() and fp.name.lower() != "metadata.json" and not fp.name.startswith("~$"):
                                files.append(fp)
                    elif item.is_file() and item.name.lower() != "metadata.json" and not item.name.startswith("~$"):
                        files.append(item)

                log.info(f"Archivos detectados ({len(files)}): {[f.name for f in files]}")

                for fpath in files:
                    processed_files += 1
                    log_data['processing']['total_files'] = processed_files
                    
                    try:
                        log.info(f"🚀 PROCESANDO: {fpath.name}")
                        log.info("="*80)
                        
                        # Particionar archivo
                        elements = partition_file(fpath)
                        log.info(f"📦 ELEMENTOS EXTRAÍDOS: {len(elements)}")
                        
                        # Debug detallado de cada elemento
                        for elem_idx, elem in enumerate(elements):
                            elem_type = str(type(elem).__name__)
                            elem_text = str(elem)[:100].replace('\n', ' ')
                            log.info(f"  {elem_idx+1:2d}. {elem_type:15s} | {elem_text}...")
                        
                        # Procesar y agrupar elementos
                        log.info("🧠 AGRUPANDO ELEMENTOS EN CHUNKS CONTEXTUALES...")
                        grouped_contents, chunk_types = process_and_group_elements(elements)
                        
                        if not grouped_contents:
                            log.warning(f"No se generaron chunks para {fpath.name}")
                            continue
                        
                        log.info(f"🎯 CONTENIDO FINAL PARA VECTORIZAR: {len(grouped_contents)} chunks")
                        
                        # Crear metadatos con tipos correctos
                        metas = [
                            mkmeta(chunk_types[idx], r, d, fpath) 
                            for idx in range(len(grouped_contents))
                        ]
                        
                        # Vectorizar contenido
                        chunks_vectorized = await vectorize_multimodal_content(
                            grouped_contents, 
                            metas, 
                            CHROMA_COLLECTIONS["multimodal_evidence"]
                        )
                        
                        total_chunks += len(grouped_contents)
                        successful_chunks += chunks_vectorized
                        successful_files += 1
                        
                        # Actualizar log
                        log_data['vectorization']['details'].append({
                            'file': fpath.name,
                            'chunks_created': len(grouped_contents),
                            'chunks_vectorized': chunks_vectorized,
                            'status': 'success'
                        })
                        
                        log.info(f"✅ {fpath.name}: {chunks_vectorized}/{len(grouped_contents)} chunks vectorizados")
                        
                    except Exception as e:
                        error_msg = f"Error procesando {fpath.name}: {e}"
                        log.error(error_msg)
                        log_data['processing']['errors'].append(error_msg)
                        log_data['vectorization']['details'].append({
                            'file': fpath.name,
                            'status': 'error',
                            'error': str(e)
                        })

    except Exception as e:
        error_msg = f"Error crítico en ingesta: {e}"
        log.error(error_msg)
        log_data['validation']['success'] = False
        log_data['validation']['error'] = error_msg

    # Finalizar log
    log_data['processing']['successful'] = successful_files
    log_data['vectorization']['total_chunks'] = total_chunks
    log_data['vectorization']['successful'] = successful_chunks
    log_data['completion_time'] = datetime.now().isoformat()
    
    # Guardar log
    save_multimodal_log(log_data)
    
    # Resumen final
    log.info("="*80)
    log.info("INGESTA MULTIMODAL COMPLETADA")
    log.info("="*80)
    log.info(f"✓ Archivos procesados: {successful_files}/{processed_files}")
    log.info(f"✓ Chunks vectorizados: {successful_chunks}/{total_chunks}")
    log.info(f"📁 Base de datos de vectores: {VECTOR_STORE_DIR}")
    log.info(f"📝 Log detallado: {MULTIMODAL_LOG_FILE}")

    return {
        "responsable": responsable or "*",
        "defecto": defecto or "*",
        "processed_files": processed_files,
        "successful_files": successful_files,
        "total_chunks": total_chunks,
        "successful_chunks": successful_chunks,
        "log_file": str(MULTIMODAL_LOG_FILE)
    }
