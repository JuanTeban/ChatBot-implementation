"""
Orquestador de retrieval multi-colección.
Maneja la consulta a diferentes dominios según la tarea.
"""
import logging
from typing import List, Dict, Any, Literal
from langchain_chroma import Chroma
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from app.config.settings import (
    VECTOR_STORE_DIR, 
    CHROMA_COLLECTIONS,
    EMBEDDING_MODEL_NAME, 
    GEMINI_API_KEY,
    RETRIEVAL_CONFIG,
    ENABLE_MULTIMODAL,
    DOCSTORE_PATH
)

logger = logging.getLogger(__name__)

TaskType = Literal["sql_generation", "business_text", "mixed"]

class RetrievalOrchestrator:
    """Orquesta el retrieval desde múltiples colecciones según la tarea."""
    
    def __init__(self):
        self.embeddings = GoogleGenerativeAIEmbeddings(
            model=EMBEDDING_MODEL_NAME,
            google_api_key=GEMINI_API_KEY
        )
        self._retrievers = {}
    
    def _get_retriever(self, collection_name: str, k: int = 3):
        """Obtiene o crea un retriever para una colección específica."""
        key = f"{collection_name}_{k}"
        if key not in self._retrievers:
            try:
                vectorstore = Chroma(
                    persist_directory=str(VECTOR_STORE_DIR),
                    embedding_function=self.embeddings,
                    collection_name=collection_name
                )
                self._retrievers[key] = vectorstore.as_retriever(
                    search_kwargs={"k": k}
                )
                logger.info(f"Retriever creado para colección '{collection_name}' con k={k}")
            except Exception as e:
                logger.error(f"Error creando retriever para '{collection_name}': {e}")
                return None
        return self._retrievers[key]
    
    def retrieve_for_sql(self, query: str) -> str:
        """
        Recupera contexto SOLO para generación de SQL.
        Usa únicamente schema_knowledge.
        """
        logger.info(f"🔍 [SQL] Buscando contexto para: '{query[:50]}...'")
        
        retriever = self._get_retriever(
            CHROMA_COLLECTIONS["schema_knowledge"], 
            k=RETRIEVAL_CONFIG["sql_k"]
        )
        
        if not retriever:
            return "SQL_ERROR::No se pudo acceder a la base de conocimiento de esquemas."
        
        try:
            docs = retriever.invoke(query)
            if not docs:
                return "SQL_ERROR::No se encontraron tablas relevantes para la consulta."
            
            # Formato igual al actual para mantener compatibilidad
            formatted_context = []
            for i, doc in enumerate(docs, 1):
                table_name = doc.metadata.get('table_name', f'table_{i}')
                formatted_context.append(f"=== TABLE CONTEXT {i}: {table_name} ===\n{doc.page_content}")
            
            result = "\n\n".join(formatted_context)
            logger.info(f"✅ [SQL] Encontradas {len(docs)} tablas relevantes")
            return result
            
        except Exception as e:
            logger.error(f"❌ [SQL] Error en retrieval: {e}")
            return f"SQL_ERROR::Error al recuperar contexto de esquemas: {str(e)}"
    
    def retrieve_for_business(self, query: str, include_external: bool = False) -> List[Dict]:
        """
        Recupera snippets para redacción de negocio.
        Usa business_rules + opcionalmente external_docs.
        """
        logger.info(f"📝 [BUSINESS] Buscando snippets para: '{query[:50]}...'")
        
        all_snippets = []
        
        # 1. Buscar en business_rules (principal)
        business_retriever = self._get_retriever(
            CHROMA_COLLECTIONS["business_rules"], 
            k=RETRIEVAL_CONFIG["business_k"]
        )
        
        if business_retriever:
            try:
                business_docs = business_retriever.invoke(query)
                for i, doc in enumerate(business_docs):
                    all_snippets.append({
                        "id": f"business_{doc.metadata.get('table_name', i)}",
                        "text": doc.page_content,
                        "source": "business_rules",
                        "metadata": doc.metadata
                    })
                logger.info(f"✅ [BUSINESS] {len(business_docs)} snippets de business_rules")
            except Exception as e:
                logger.warning(f"⚠️ [BUSINESS] Error en business_rules: {e}")
        
        # 2. Buscar en external_docs si se solicita
        if include_external:
            external_retriever = self._get_retriever(
                CHROMA_COLLECTIONS["external_docs"], 
                k=RETRIEVAL_CONFIG["docs_k"]
            )
            
            if external_retriever:
                try:
                    external_docs = external_retriever.invoke(query)
                    for i, doc in enumerate(external_docs):
                        all_snippets.append({
                            "id": f"external_{doc.metadata.get('source_id', i)}",
                            "text": doc.page_content,
                            "source": "external_docs", 
                            "metadata": doc.metadata
                        })
                    logger.info(f"✅ [BUSINESS] {len(external_docs)} snippets de external_docs")
                except Exception as e:
                    logger.warning(f"⚠️ [BUSINESS] Error en external_docs: {e}")
        
        # 3. Limitar total de snippets
        max_snippets = RETRIEVAL_CONFIG["max_chunks_per_collection"]
        if len(all_snippets) > max_snippets:
            all_snippets = all_snippets[:max_snippets]
            logger.info(f"🔄 [BUSINESS] Limitado a {max_snippets} snippets totales")
        
        logger.info(f"📋 [BUSINESS] Total: {len(all_snippets)} snippets recuperados")
        return all_snippets

    def retrieve_for_multimodal_report(self, query: str) -> Dict[str, Any]:
        """
        Recupera contexto multimodal para reportes.
        Solo se ejecuta si ENABLE_MULTIMODAL=True.
        """
        
        if not ENABLE_MULTIMODAL:
            return {"texts": [], "tables": [], "images": []}
        
        logger.info(f"🖼️ [MULTIMODAL] Buscando contexto para: '{query[:50]}...'")
        
        # Usar el retriever existente de external_docs
        docs = self.retrieve_for_business(query, include_external=True)
        
        # Separar por tipo y resolver rutas del docstore
        result = {"texts": [], "tables": [], "images": []}
        
        for doc in docs:
            metadata = doc.get("metadata", {})
            doc_type = metadata.get("doc_type", "text")
            docstore_path = metadata.get("docstore_path", "")
            
            if doc_type == "Table" and docstore_path:
                try:
                    table_file = DOCSTORE_PATH / docstore_path
                    if table_file.exists():
                        table_content = table_file.read_text(encoding='utf-8')
                        result["tables"].append({
                            "content": table_content,
                            "source": metadata.get("source_file", "Unknown")
                        })
                except Exception as e:
                    logger.warning(f"No se pudo cargar tabla {docstore_path}: {e}")
                    
            elif doc_type == "Image" and docstore_path:
                try:
                    image_file = DOCSTORE_PATH / docstore_path
                    if image_file.exists():
                        result["images"].append({
                            "path": str(image_file),
                            "summary": doc["text"],
                            "source": metadata.get("source_file", "Unknown")
                        })
                except Exception as e:
                    logger.warning(f"No se pudo cargar imagen {docstore_path}: {e}")
            else:
                result["texts"].append(doc)
        
        logger.info(f"📋 [MULTIMODAL] Recuperado: {len(result['texts'])} textos, {len(result['tables'])} tablas, {len(result['images'])} imágenes")
        return result

# Instancia global para reutilizar conexiones
_orchestrator = None

def get_orchestrator() -> RetrievalOrchestrator:
    """Obtiene la instancia global del orquestador."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = RetrievalOrchestrator()
    return _orchestrator





