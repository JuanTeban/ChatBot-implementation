from typing import List, Dict, Any
import chromadb
import logging
from app.utils.chroma_utils import vectorstore
from app.utils.report_logger import report_flow_logger
from app.config.settings import VECTOR_STORE_DIR, CHROMA_COLLECTIONS
import google.generativeai as genai
from app.config.settings import VECTOR_STORE_DIR, CHROMA_COLLECTIONS, GEMINI_API_KEY, EMBEDDING_MODEL_NAME
import unicodedata

logger = logging.getLogger(__name__)

def get_schema_context(goal: str) -> str:
    """
    RAG de esquema para guiar NL→SQL.
    Recupera dinámicamente el contexto de esquemas del vectorstore usando la colección schema_knowledge.
    Usa query_embeddings con el mismo modelo de embeddings usado al vectorizar (Gemini),
    para evitar desajustes de dimensiones (p.ej., 768 vs 384).
    """
    context_obtained = ""
    context_source = ""

    try:
        # 🔍 LOG: Inicio de recuperación de esquemas
        logger.info(f"🔍 SCHEMA_CONTEXT - INICIO")
        logger.info(f"   Goal: '{goal}'")
        logger.info(f"   VECTOR_STORE_DIR: {VECTOR_STORE_DIR}")
        logger.info(f"   CHROMA_COLLECTIONS: {CHROMA_COLLECTIONS}")

        # 🔗 CONECTAR A CHROMADB SCHEMA KNOWLEDGE
        logger.info(f"   Conectando a ChromaDB...")
        chroma_client = chromadb.PersistentClient(path=str(VECTOR_STORE_DIR))
        collection_name = CHROMA_COLLECTIONS["schema_knowledge"]
        logger.info(f"   Collection name: {collection_name}")

        try:
            logger.info(f"   Obteniendo colección schema_knowledge...")
            collection = chroma_client.get_collection(name=collection_name)
            logger.info(f"   ✅ Colección obtenida")

            # Verificar si la colección tiene datos
            count = collection.count()
            logger.info(f"   📊 Elementos en colección: {count}")

            if count == 0:
                logger.warning(f"   ⚠️ Colección schema_knowledge está vacía")
                raise Exception("Colección schema_knowledge está vacía")

            # 🔍 REALIZAR BÚSQUEDA SEMÁNTICA usando EL MISMO MODELO (Gemini)
            logger.info(f"   Preparando embedding de la query con Gemini...")
            genai.configure(api_key=GEMINI_API_KEY)
            q_emb = genai.embed_content(
                model=EMBEDDING_MODEL_NAME,            # p.ej. "models/embedding-001"
                content=f"database schema table {goal}",
                task_type="RETRIEVAL_QUERY"
            )["embedding"]

            # (Opcional) Log de dimensiones para diagnóstico; no interrumpe el flujo
            try:
                sample = collection.get(include=["embeddings"], limit=1)
                stored_dim = len(sample["embeddings"][0]) if sample.get("embeddings") else None
                query_dim = len(q_emb) if q_emb else None
                logger.info(f"   🔎 Dimensiones -> stored={stored_dim}, query={query_dim}")
            except Exception as dim_e:
                logger.debug(f"   (Aviso) No se pudo inspeccionar dimensiones de la colección: {dim_e}")

            logger.info(f"   Ejecutando query por embedding...")
            results = collection.query(
                query_embeddings=[q_emb],
                n_results=5
            )
            logger.info(f"   ✅ Query ejecutada")

            # 📋 PROCESAR RESULTADOS
            documents_list = results.get("documents", [])
            documents = documents_list[0] if documents_list and len(documents_list) > 0 else []

            logger.info(f"   📄 Documentos encontrados: {len(documents)}")

            if documents and any((doc or "").strip() for doc in documents):
                # Unimos los documentos en un único contexto
                context_obtained = "\n\n".join(doc for doc in documents if (doc or "").strip())
                context_source = "schema_knowledge_collection"
                logger.info(f"   ✅ Contexto recuperado de schema_knowledge: {len(documents)} documentos")
            else:
                raise Exception("No se encontraron documentos relevantes en schema_knowledge")

        except Exception as e:
            logger.warning(f"   ⚠️ Error con colección schema_knowledge: {e}")
            raise Exception(f"Colección schema_knowledge no disponible: {e}")

    except Exception as e:
        logger.warning(f"   ⚠️ Error en vectorstore: {e}")

        # FALLBACK 1: herramienta dinámica de tablas
        try:
            logger.info(f"   🔄 Intentando fallback con get_available_tables...")
            from app.tools.tools import get_available_tables
            tables_info = get_available_tables.invoke({})

            if tables_info and tables_info.strip() and not tables_info.startswith("SQL_ERROR"):
                context_obtained = tables_info
                context_source = "tools_fallback"
                logger.info(f"   ✅ Fallback exitoso: información de tablas obtenida")
            else:
                raise Exception("No se pudo obtener información de tablas")

        except Exception as e2:
            logger.error(f"   ❌ Fallback get_available_tables falló: {e2}")

            # FALLBACK 2: vectorstore genérico
            try:
                logger.info(f"   🔄 Intentando fallback con vectorstore genérico...")
                retriever = vectorstore.as_retriever(search_kwargs={"k": 3})
                docs = retriever.invoke(f"database schema table {goal}")

                if docs and any((d.page_content or "").strip() for d in docs):
                    context_obtained = "\n\n".join(d.page_content for d in docs if (d.page_content or "").strip())
                    context_source = "vectorstore_generic_fallback"
                    logger.info(f"   ✅ Fallback vectorstore genérico exitoso: {len(docs)} documentos")
                else:
                    raise Exception("No se encontraron documentos en vectorstore genérico")

            except Exception as e3:
                logger.error(f"   ❌ Todos los fallbacks fallaron: {e3}")

                # Último recurso: información mínima pero útil
                context_obtained = """
INFORMACIÓN MÍNIMA DE ESQUEMA:
- La base de datos contiene tablas relacionadas con seguimiento de hallazgos y defectos.
- Use get_available_tables() para obtener la lista completa de tablas disponibles.
- Ejecute el pipeline ETL para regenerar el esquema completo.
""".strip()
                context_source = "minimal_fallback"
                logger.info(f"   ⚠️ Usando fallback mínimo")

    # 🔍 LOG: Final de recuperación de esquemas
    logger.info(f"🔍 SCHEMA_CONTEXT - FINAL")
    logger.info(f"   Fuente: {context_source}")
    logger.info(f"   Contexto obtenido: {len(context_obtained)} caracteres")

    return context_obtained


def get_business_snippets(query: str, k: int = 6, include_external: bool = False) -> List[Dict[str, Any]]:
    """
    RAG de negocio para redactar con reglas/definiciones.
    Corrección: evitar 'truth value is ambiguous' filtrando rule_type en cliente.
    """
    snippets: List[Dict[str, Any]] = []
    retrieval_success = False
    error_message = None
    rule_type_detected = None

    logger.info(f"🔍 BUSINESS_SNIPPETS - INICIO")
    logger.info(f"   Query: '{query}'")
    logger.info(f"   k: {k}")
    logger.info(f"   VECTOR_STORE_DIR: {VECTOR_STORE_DIR}")
    logger.info(f"   CHROMA_COLLECTIONS: {CHROMA_COLLECTIONS}")

    def norm(s: str) -> str:
        if s is None:
            return ""
        s = str(s)
        return ''.join(c for c in unicodedata.normalize('NFD', s.lower()) if unicodedata.category(c) != 'Mn')

    def flatten_meta_value(v):
        """Devuelve valor escalar (string) desde posibles listas/ndarrays/tuplas."""
        try:
            # ndarray -> list
            if hasattr(v, "tolist"):
                v = v.tolist()
        except Exception:
            pass
        # lista/tupla/conjuntos -> primer elemento si existe
        if isinstance(v, (list, tuple, set)):
            v = next(iter(v), "")
        return "" if v is None else str(v)

    try:
        qn = norm(query)
        if any(kw in qn for kw in ["resumen", "ejecutivo", "kpi", "metricas", "definiciones", "calidad"]):
            rule_type_detected = "summary"
        elif any(kw in qn for kw in ["plan", "accion", "priorizacion", "recomendaciones", "sla", "acción"]):
            rule_type_detected = "recommendations"
        else:
            rule_type_detected = None
        logger.info(f"   Tipo detectado: {rule_type_detected}")

        logger.info(f"   Conectando a ChromaDB...")
        chroma_client = chromadb.PersistentClient(path=str(VECTOR_STORE_DIR))
        collection_name = CHROMA_COLLECTIONS["business_rules"]
        logger.info(f"   Collection name: {collection_name}")

        try:
            logger.info(f"   Obteniendo colección...")
            collection = chroma_client.get_collection(name=collection_name)
            logger.info(f"   ✅ Colección obtenida")

            count = collection.count()
            logger.info(f"   📊 Elementos en colección: {count}")
            if count == 0:
                raise Exception("Colección business_rules está vacía")

            # Embedding con el MISMO modelo usado al vectorizar
            genai.configure(api_key=GEMINI_API_KEY)
            q_emb = genai.embed_content(
                model=EMBEDDING_MODEL_NAME,
                content=query,
                task_type="RETRIEVAL_QUERY"
            )["embedding"]

            # Log de dimensiones para diagnóstico
            try:
                sample = collection.get(include=["embeddings"], limit=1)
                stored_dim = len(sample["embeddings"][0]) if sample.get("embeddings") else None
                query_dim = len(q_emb) if q_emb else None
                logger.info(f"   🔎 Dimensiones -> stored={stored_dim}, query={query_dim}")
                if stored_dim and query_dim and stored_dim != query_dim:
                    raise RuntimeError(
                        f"BUSINESS_RULES_EMBEDDING_DIM_MISMATCH: stored={stored_dim}, query={query_dim}. "
                        f"Alinea EMBEDDING_MODEL_NAME y revectoriza si es necesario."
                    )
            except Exception as dim_e:
                logger.debug(f"   (Aviso) Inspección de dimensiones no disponible: {dim_e}")

            # ❗ Sin 'where' (evitamos comparar strings vs arrays dentro de Chroma)
            # Traemos un pool más grande y filtramos en cliente.
            pool = max(k * 4, 10)
            logger.info(f"   Ejecutando query por embedding (pool={pool})...")
            results = collection.query(
                query_embeddings=[q_emb],
                n_results=pool,
                include=["documents", "metadatas", "distances"]
            )
            logger.info(f"   ✅ Query ejecutada")

            documents_list = results.get("documents", [])
            documents = documents_list[0] if documents_list and len(documents_list) > 0 else []
            metadatas_list = results.get("metadatas", [])
            metadatas = metadatas_list[0] if metadatas_list and len(metadatas_list) > 0 else []
            distances_list = results.get("distances", [])
            distances = distances_list[0] if distances_list and len(distances_list) > 0 else []

            logger.info(f"   📄 Documentos recuperados: {len(documents)}")

            # Filtrado en cliente por rule_type (robusto a listas/ndarrays)
            rows = []
            for i, (doc, meta, dist) in enumerate(zip(documents, metadatas, distances)):
                meta_rule = flatten_meta_value((meta or {}).get("rule_type", ""))
                if rule_type_detected and norm(meta_rule) != norm(rule_type_detected):
                    continue
                # Normaliza distancia
                try:
                    sim = None if dist is None else (1 - float(dist))
                except Exception:
                    sim = None

                cleaned_text = '\n'.join(
                    line for line in (doc or "").split('\n')
                    if not line.startswith(('TIPO:', 'CATEGORÍA:', 'TÍTULO:', 'CATEGORIA:', 'TITULO:', 'CONTENIDO:'))
                ).strip()

                rows.append({
                    "text": cleaned_text or (doc or "").strip(),
                    "source": flatten_meta_value((meta or {}).get("source_file", f"regla_negocio_{i}")),
                    "evidence_id": flatten_meta_value((meta or {}).get("chunk_id", f"business_rule_{i}")),
                    "title": flatten_meta_value((meta or {}).get("title", "Regla de negocio")),
                    "rule_type": meta_rule or "unknown",
                    "category": flatten_meta_value((meta or {}).get("category", "general")),
                    "similarity_score": sim
                })

            # Si tras filtrar no hay suficientes, usa los mejores sin filtrar
            if not rows:
                logger.info("   ⚠️ Sin matches por rule_type; usando top-k sin filtrar.")
                for i, (doc, meta, dist) in enumerate(zip(documents[:k], metadatas[:k], distances[:k])):
                    try:
                        sim = None if dist is None else (1 - float(dist))
                    except Exception:
                        sim = None
                    rows.append({
                        "text": (doc or "").strip(),
                        "source": flatten_meta_value((meta or {}).get("source_file", f"regla_negocio_{i}")),
                        "evidence_id": flatten_meta_value((meta or {}).get("chunk_id", f"business_rule_{i}")),
                        "title": flatten_meta_value((meta or {}).get("title", "Regla de negocio")),
                        "rule_type": flatten_meta_value((meta or {}).get("rule_type", "unknown")),
                        "category": flatten_meta_value((meta or {}).get("category", "general")),
                        "similarity_score": sim
                    })

            # Ordena por score desc y corta a k
            rows.sort(key=lambda r: (r["similarity_score"] or 0.0), reverse=True)
            snippets = rows[:k]
            retrieval_success = True
            logger.info(f"✅ Recuperados {len(snippets)} snippets (tipo: {rule_type_detected or 'all'})")

        except Exception as e:
            logger.error(f"❌ Error con colección business_rules: {e}")
            error_message = f"Colección de reglas de negocio no disponible: {e}"

            # Fallback: retriever genérico
            logger.info(f"🔄 Intentando fallback con vectorstore genérico...")
            try:
                retriever = vectorstore.as_retriever(search_kwargs={"k": k})
                docs = retriever.invoke(query)
                for i, doc in enumerate(docs):
                    snippets.append({
                        "text": doc.page_content,
                        "source": doc.metadata.get("source", f"documento_{i}"),
                        "evidence_id": f"fallback_{i}",
                        "title": "Regla genérica",
                        "rule_type": "fallback",
                        "category": "general",
                        "similarity_score": 0.5
                    })
                retrieval_success = True
                logger.info(f"✅ Fallback exitoso: {len(snippets)} snippets genéricos")
            except Exception as e2:
                error_message = f"Business rules y fallback fallaron: {str(e2)}"
                snippets = []
                logger.error(f"❌ Fallback también falló: {e2}")

    except Exception as e:
        error_message = str(e)
        snippets = []
        logger.error(f"❌ Error crítico en get_business_snippets: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")

    if retrieval_success and snippets:
        context_details = f"Tipo detectado: {rule_type_detected or 'all'}, Snippets: {len(snippets)}"
        if snippets:
            context_details += f", Fuentes: {list(set(s.get('source', 'N/A') for s in snippets))}"
        report_flow_logger.log_rag_context(
            query=query,
            context_type="business_snippets",
            retrieved_context=context_details,
            source_count=len(snippets)
        )
    else:
        report_flow_logger.log_error(
            error_type="business_snippets_retrieval",
            error_message=error_message or "No se encontraron reglas de negocio",
            context=f"Query: {query}, Tipo detectado: {rule_type_detected}, k: {k}"
        )

    logger.info(f"🔍 BUSINESS_SNIPPETS - FINAL")
    logger.info(f"   Snippets obtenidos: {len(snippets)}")
    logger.info(f"   Éxito: {retrieval_success}")

    return snippets


def extract_defect_from_data(data_rows: List[Dict[str, Any]]) -> str:
    """
    Extrae el defecto específico de los datos para mejorar la búsqueda de evidencia multimodal.
    """
    if not data_rows:
        return None
    
    # Buscar el defecto más relevante (priorizar por antigüedad o estado)
    defect_candidates = []
    
    for row in data_rows:
        defect = row.get('defecto', '')
        if defect and isinstance(defect, str):
            # Extraer número de defecto si existe
            import re
            defect_match = re.search(r'\((\d+)\)', defect)
            if defect_match:
                defect_candidates.append(defect_match.group(1))
            else:
                # Si no hay número, usar el texto completo
                defect_candidates.append(defect.strip())
    
    # Retornar el primer defecto encontrado
    return defect_candidates[0] if defect_candidates else None


def get_multimodal_evidence(query: str, responsable: str, defecto: str = None, k: int = 4) -> List[Dict[str, Any]]:
    """
    RAG de evidencia multimodal para enriquecer recomendaciones.
    Recupera evidencia específica del responsable y defecto desde la colección multimodal_evidence.
    """
    evidence: List[Dict[str, Any]] = []
    retrieval_success = False
    error_message = None

    logger.info(f"🔍 MULTIMODAL_EVIDENCE - INICIO")
    logger.info(f"   Query: '{query}'")
    logger.info(f"   Responsable: '{responsable}'")
    logger.info(f"   Defecto: '{defecto}'")
    logger.info(f"   k: {k}")

    # Helpers locales (no contaminan el módulo)
    import unicodedata, re
    def _norm(s: Any) -> str:
        if s is None:
            return ""
        s = str(s).lower()
        return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')

    def _flatten(v: Any) -> str:
        try:
            if hasattr(v, "tolist"):
                v = v.tolist()
        except Exception:
            pass
        if isinstance(v, (list, tuple, set)):
            v = next(iter(v), "")
        return "" if v is None else str(v)

    def _digits(s: Any) -> str:
        return ''.join(ch for ch in str(s) if ch.isdigit())

    rq_norm = _norm(responsable)
    dq_digits = _digits(defecto) if defecto else ""

    try:
        # 🔗 CONECTAR A CHROMADB MULTIMODAL EVIDENCE
        logger.info(f"   Conectando a ChromaDB...")
        chroma_client = chromadb.PersistentClient(path=str(VECTOR_STORE_DIR))
        collection_name = CHROMA_COLLECTIONS["multimodal_evidence"]
        logger.info(f"   Collection name: {collection_name}")

        try:
            logger.info(f"   Obteniendo colección multimodal_evidence...")
            collection = chroma_client.get_collection(name=collection_name)
            logger.info(f"   ✅ Colección obtenida")

            count = collection.count()
            logger.info(f"   📊 Elementos en colección: {count}")
            if count == 0:
                logger.warning(f"   ⚠️ Colección multimodal_evidence está vacía")
                return []

            # 🔍 GENERAR EMBEDDING DE LA QUERY
            logger.info(f"   Preparando embedding de la query...")
            genai.configure(api_key=GEMINI_API_KEY)
            q_emb = genai.embed_content(
                model=EMBEDDING_MODEL_NAME,
                content=query,
                task_type="RETRIEVAL_QUERY"
            )["embedding"]

            # 🔍 BÚSQUEDA SEMÁNTICA (sin filtros, filtramos después en cliente)
            logger.info(f"   Ejecutando query semántica...")
            results = collection.query(
                query_embeddings=[q_emb],
                n_results=max(k * 4, 10),  # pool más grande para filtrar después
                include=["documents", "metadatas", "distances"]
            )
            logger.info(f"   ✅ Query ejecutada")

            # 📋 PROCESAR RESULTADOS
            documents_list = results.get("documents", [])
            documents = documents_list[0] if documents_list and len(documents_list) > 0 else []
            metadatas_list = results.get("metadatas", [])
            metadatas = metadatas_list[0] if metadatas_list and len(metadatas_list) > 0 else []
            distances_list = results.get("distances", [])
            distances = distances_list[0] if distances_list and len(distances_list) > 0 else []

            logger.info(f"   📄 Documentos recuperados: {len(documents)}")

            # 🔧 PROCESAR Y FILTRAR EVIDENCIA (normalizando meta)
            rows = []
            for i, (doc, meta, dist) in enumerate(zip(documents, metadatas, distances)):
                if not doc or not meta:
                    continue

                # Normalizar distancia a similitud
                try:
                    sim = None if dist is None else (1 - float(dist))
                except Exception:
                    sim = 0.5

                # Extraer/flatten metadatos
                element_type   = _flatten(meta.get("element_type", "unknown"))
                source_file    = _flatten(meta.get("source_file", "unknown"))
                source_path    = _flatten(meta.get("source_path", ""))
                responsable_mt = _flatten(meta.get("responsable", ""))
                defecto_mt     = _flatten(meta.get("defecto", ""))

                # 🔍 FILTRADO ROBUSTO POR RESPONSABLE
                if rq_norm:
                    rm_norm = _norm(responsable_mt)
                    if rm_norm and rq_norm not in rm_norm and rm_norm not in rq_norm:
                        continue  # no coincide de forma laxa

                # 🔍 FILTRADO ROBUSTO POR DEFECTO (preferir ID numérico)
                if dq_digits:
                    dm_digits = _digits(defecto_mt)
                    if dm_digits and dm_digits != dq_digits:
                        continue
                    # si en meta no hay dígitos, probar match laxo por texto normalizado
                    if not dm_digits:
                        if _norm(defecto or "") and _norm(defecto or "") not in _norm(defecto_mt):
                            continue
                elif defecto:
                    # sin ID: comparar por texto normalizado en ambos sentidos
                    ndq = _norm(defecto)
                    ndm = _norm(defecto_mt)
                    if ndq and ndm and ndq not in ndm and ndm not in ndq:
                        continue

                # Filtrar por relevancia semántica (score mínimo)
                if sim and sim < 0.3:  # Umbral de similitud
                    continue

                rows.append({
                    "text": (doc or "").strip(),
                    "source": source_file,
                    "evidence_id": _flatten(meta.get("chunk_id", f"multimodal_{i}")),
                    "title": f"Evidencia {element_type}",
                    "element_type": element_type,
                    "responsable": responsable_mt,
                    "defecto": defecto_mt,
                    "source_path": source_path,
                    "similarity_score": sim,
                    "modality": element_type  # text, table, image
                })

            # Ordenar por score y limitar a k
            rows.sort(key=lambda r: (r["similarity_score"] or 0.0), reverse=True)
            evidence = rows[:k]
            retrieval_success = bool(evidence)  # coherente con los logs

            logger.info(f"✅ Recuperados {len(evidence)} elementos de evidencia multimodal")

        except Exception as e:
            logger.error(f"❌ Error con colección multimodal_evidence: {e}")
            error_message = f"Colección de evidencia multimodal no disponible: {e}"

    except Exception as e:
        error_message = str(e)
        evidence = []
        logger.error(f"❌ Error crítico en get_multimodal_evidence: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")

    # 🔍 LOG: Registrar recuperación de evidencia multimodal
    if retrieval_success and evidence:
        context_details = f"Evidencia multimodal: {len(evidence)} elementos"
        if evidence:
            modalities = list(set(e.get('modality', 'unknown') for e in evidence))
            context_details += f", Modalidades: {modalities}"
        report_flow_logger.log_rag_context(
            query=query,
            context_type="multimodal_evidence",
            retrieved_context=context_details,
            source_count=len(evidence)
        )
    else:
        report_flow_logger.log_error(
            error_type="multimodal_evidence_retrieval",
            error_message=error_message or "No se encontró evidencia multimodal",
            context=f"Query: {query}, Responsable: {responsable}, Defecto: {defecto}"
        )

    logger.info(f"🔍 MULTIMODAL_EVIDENCE - FINAL")
    logger.info(f"   Evidencia obtenida: {len(evidence)}")
    logger.info(f"   Éxito: {retrieval_success}")

    return evidence


def join_multimodal_evidence(evidence: List[Dict[str, Any]]) -> str:
    """Formatea evidencia multimodal para prompts de recomendaciones."""
    if not evidence:
        return "(sin evidencia multimodal disponible)"
    
    formatted_evidence = []
    
    for ev in evidence:
        modality = ev.get('modality', 'unknown')
        source = ev.get('source', 'unknown')
        text = ev.get('text', '').strip()
        
        if not text:
            continue
            
        # Formatear según el tipo de modalidad
        if modality == 'image':
            formatted_evidence.append(f"[IMAGEN - {source}]\n{text}")
        elif modality == 'table':
            formatted_evidence.append(f"[TABLA - {source}]\n{text}")
        elif modality == 'text':
            formatted_evidence.append(f"[TEXTO - {source}]\n{text}")
        else:
            formatted_evidence.append(f"[EVIDENCIA - {source}]\n{text}")
    
    if not formatted_evidence:
        return "(evidencia multimodal sin contenido procesable)"
    
    return "\n\n---\n\n".join(formatted_evidence)


def join_snippets(snips: List[Dict]) -> str:
    """Une snippets en texto plano para prompts."""
    if not snips:
        return "(sin snippets de negocio - usando solo datos)"
    
    texts = []
    for s in snips:
        source_info = f"[Fuente: {s.get('source', 'unknown')}]"
        texts.append(f"{source_info}\n{s['text']}")
    
    return "\n---\n".join(texts)

def get_summary_table_evidence(defecto: str) -> List[Dict[str, Any]]:
    if not defecto:
        logger.info("No se proporcionó un defecto específico para buscar evidencia tabular.")
        return []

    logger.info(f"🔍 SUMMARY_TABLE_EVIDENCE - INICIO para defecto '{defecto}'")
    
    try:
        chroma_client = chromadb.PersistentClient(path=str(VECTOR_STORE_DIR))
        collection_name = CHROMA_COLLECTIONS["multimodal_evidence"]
        collection = chroma_client.get_collection(name=collection_name)

        search_id = ''.join(filter(str.isdigit, defecto))
        if not search_id:
             logger.warning(f"No se pudo extraer un ID numérico del defecto '{defecto}'.")
             return []

        all_tables = collection.get(
            where={"element_type": "table"},
            include=["documents", "metadatas"]
        )
        
        evidence = []
        documents = all_tables.get("documents", [])
        metadatas = all_tables.get("metadatas", [])

        for i, (doc, meta) in enumerate(zip(documents, metadatas)):
            defecto_meta = (meta or {}).get("defecto", "")
            if search_id in defecto_meta:
                evidence.append({
                    "text": (doc or "").strip(),
                    "source": (meta or {}).get("source_file", f"tabla_evidencia_{i}"),
                    "evidence_id": (meta or {}).get("chunk_id", f"table_evidence_{i}")
                })
        
        logger.info(f"✅ Recuperados {len(evidence)} fragmentos de tablas para el resumen tras filtrar en cliente.")
        
        if not evidence:
            logger.warning("No se encontraron tablas para el resumen.")
        
        report_flow_logger.log_rag_context_detailed(
            query=defecto,
            context_type="summary_table_evidence",
            retrieved_context=f"Se encontraron {len(evidence)} tablas para el resumen.",
            source_count=len(evidence),
            collection_name=collection_name,
            embedding_model="N/A (filtro directo)"
        )
        
        return evidence
    except Exception as e:
        logger.error(f"❌ Error al recuperar evidencia tabular para el resumen: {e}")
        report_flow_logger.log_error(
            error_type="summary_table_retrieval",
            error_message=str(e),
            context=f"Defecto: {defecto}"
        )
        return []

def join_table_evidence(evidence: List[Dict[str, Any]]) -> str:
    if not evidence:
        return "(sin evidencia tabular específica para este defecto)"
    
    formatted_texts = [f"[TABLA de {ev.get('source', 'fuente desconocida')}]\n{ev.get('text', '')}" for ev in evidence]
    return "\n\n---\n\n".join(formatted_texts)