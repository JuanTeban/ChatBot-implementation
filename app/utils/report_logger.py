import logging
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from app.config.settings import LOGS_DIR

class ReportFlowLogger:
    """
    Logger especializado para rastrear el flujo completo de generación de reportes.
    Captura prompts, datos, queries, contextos RAG y respuestas del LLM.
    """
    
    def __init__(self):
        self.logger = logging.getLogger('report_flow')
        self.logger.setLevel(logging.INFO)
        
        # Crear directorio de logs si no existe
        report_logs_dir = LOGS_DIR / "report_flow"
        report_logs_dir.mkdir(parents=True, exist_ok=True)
        
        # Configurar handler para archivo específico
        if not self.logger.handlers:
            log_file = report_logs_dir / f"report_flow_{datetime.now().strftime('%Y%m%d')}.log"
            handler = logging.FileHandler(log_file, encoding='utf-8')
            
            # Formato detallado para el flujo
            formatter = logging.Formatter(
                '%(asctime)s | %(levelname)s | %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
    
    def _format_data(self, data: Any) -> str:
        """Formatea datos para logging legible."""
        if isinstance(data, str):
            return data
        elif isinstance(data, (dict, list)):
            return json.dumps(data, ensure_ascii=False, indent=2)
        else:
            return str(data)
    
    def _truncate_if_long(self, text: str, max_length: int = 2000) -> str:
        """Trunca texto muy largo para mantener logs manejables."""
        if len(text) <= max_length:
            return text
        return text[:max_length] + f"\n... [TRUNCADO - Total: {len(text)} caracteres]"
    
    def start_report_generation(self, consultant_name: str, report_type: str = "preview"):
        """Inicia el logging de un nuevo reporte."""
        self.logger.info("="*80)
        self.logger.info(f"🚀 INICIANDO GENERACIÓN DE REPORTE")
        self.logger.info(f"📋 Consultor: {consultant_name}")
        self.logger.info(f"📋 Tipo: {report_type}")
        self.logger.info(f"📋 Timestamp: {datetime.now().isoformat()}")
        self.logger.info("="*80)
    
    def log_sql_generation(self, question: str, schema_context: str, generated_sql: str):
        """Registra la generación de SQL."""
        self.logger.info("🔍 GENERACIÓN DE SQL")
        self.logger.info(f"Pregunta/Objetivo: {question}")
        self.logger.info("-" * 40)
        self.logger.info("📚 CONTEXTO DE ESQUEMAS USADO:")
        self.logger.info(self._truncate_if_long(schema_context))
        self.logger.info("-" * 40)
        self.logger.info("⚡ SQL GENERADA:")
        self.logger.info(generated_sql)
        self.logger.info("")
    
    def log_sql_execution(self, sql: str, result_count: int, execution_success: bool, error: Optional[str] = None):
        """Registra la ejecución de SQL."""
        status = "✅ EXITOSA" if execution_success else "❌ FALLIDA"
        self.logger.info(f"💾 EJECUCIÓN DE SQL - {status}")
        self.logger.info(f"SQL: {sql}")
        if execution_success:
            self.logger.info(f"📊 Registros obtenidos: {result_count}")
        else:
            self.logger.info(f"❌ Error: {error}")
        self.logger.info("")
    
    def log_rag_context(self, query: str, context_type: str, retrieved_context: str, source_count: int):
        """Registra la recuperación de contexto RAG."""
        self.logger.info(f"🧠 RECUPERACIÓN RAG - {context_type.upper()}")
        self.logger.info(f"Query: {query}")
        self.logger.info(f"📚 Fuentes encontradas: {source_count}")
        self.logger.info("-" * 40)
        self.logger.info("📖 CONTEXTO RECUPERADO:")
        self.logger.info(self._truncate_if_long(retrieved_context))
        self.logger.info("")
    
    def log_rag_context_detailed(self, query: str, context_type: str, retrieved_context: str, source_count: int, 
                                collection_name: str = None, embedding_model: str = None, similarity_scores: List[float] = None):
        """Registra la recuperación de contexto RAG con detalles técnicos."""
        self.logger.info(f"🧠 RECUPERACIÓN RAG - {context_type.upper()}")
        self.logger.info(f"Query: {query}")
        self.logger.info(f"📚 Fuentes encontradas: {source_count}")
        if collection_name:
            self.logger.info(f"🗄️ Colección: {collection_name}")
        if embedding_model:
            self.logger.info(f"🤖 Modelo de embedding: {embedding_model}")
        if similarity_scores:
            self.logger.info(f"📊 Scores de similitud: {similarity_scores}")
        self.logger.info("-" * 40)
        self.logger.info("📖 CONTEXTO RECUPERADO:")
        self.logger.info(self._truncate_if_long(retrieved_context))
        self.logger.info("")
    
    def log_business_snippets(self, query: str, snippets: List[Dict], snippet_type: str):
        """Registra los snippets de negocio obtenidos."""
        self.logger.info(f"📋 SNIPPETS DE NEGOCIO - {snippet_type.upper()}")
        self.logger.info(f"Query: {query}")
        self.logger.info(f"📚 Snippets obtenidos: {len(snippets)}")
        
        for i, snippet in enumerate(snippets):
            self.logger.info(f"----- Snippet {i+1} -----")
            self.logger.info(f"Fuente: {snippet.get('source', 'N/A')}")
            self.logger.info(f"ID: {snippet.get('evidence_id', 'N/A')}")
            text = snippet.get('text', '')
            self.logger.info(f"Texto: {self._truncate_if_long(text, 800)}")
        self.logger.info("")
    
    def log_llm_prompt_and_response(self, prompt_type: str, prompt: str, response: str, consultant_name: str):
        """Registra prompt enviado al LLM y su respuesta."""
        self.logger.info(f"🤖 LLM INTERACTION - {prompt_type.upper()}")
        self.logger.info(f"📋 Para consultor: {consultant_name}")
        self.logger.info("-" * 40)
        self.logger.info("📤 PROMPT ENVIADO:")
        self.logger.info(self._truncate_if_long(prompt, 1500))
        self.logger.info("-" * 40)
        self.logger.info("📥 RESPUESTA LLM:")
        self.logger.info(self._truncate_if_long(response))
        self.logger.info("")
    
    def log_chart_generation(self, chart_title: str, chart_type: str, data_points: int, success: bool, error: Optional[str] = None):
        """Registra la generación de gráficos."""
        status = "✅ EXITOSO" if success else "❌ FALLIDO"
        self.logger.info(f"📊 GENERACIÓN DE GRÁFICO - {status}")
        self.logger.info(f"Título: {chart_title}")
        self.logger.info(f"Tipo: {chart_type}")
        if success:
            self.logger.info(f"📊 Puntos de datos: {data_points}")
        else:
            self.logger.info(f"❌ Error: {error}")
        self.logger.info("")
    
    def log_data_processing(self, step: str, input_count: int, output_count: int, details: Optional[str] = None):
        """Registra procesamientos de datos."""
        self.logger.info(f"⚙️ PROCESAMIENTO DE DATOS - {step.upper()}")
        self.logger.info(f"📊 Entrada: {input_count} registros")
        self.logger.info(f"📊 Salida: {output_count} registros")
        if details:
            self.logger.info(f"📝 Detalles: {details}")
        self.logger.info("")
    
    def log_template_operation(self, operation: str, sql_template: str, consultant_name: str):
        """Registra operaciones con plantillas SQL."""
        self.logger.info(f"📋 OPERACIÓN DE PLANTILLA - {operation.upper()}")
        self.logger.info(f"📋 Consultor: {consultant_name}")
        self.logger.info("-" * 40)
        self.logger.info("📜 PLANTILLA SQL:")
        self.logger.info(sql_template)
        self.logger.info("")
    
    def log_vector_details(self, collection_name: str, total_vectors: int, retrieved_vectors: List[Dict], 
                          query_embedding_dim: int = None, similarity_threshold: float = None):
        """Registra detalles completos de los vectores recuperados."""
        self.logger.info(f"🔍 DETALLES DE VECTORES - {collection_name.upper()}")
        self.logger.info(f"📊 Total de vectores en colección: {total_vectors}")
        self.logger.info(f"📈 Vectores recuperados: {len(retrieved_vectors)}")
        if query_embedding_dim:
            self.logger.info(f"🔢 Dimensión del embedding de query: {query_embedding_dim}")
        if similarity_threshold:
            self.logger.info(f"🎯 Umbral de similitud: {similarity_threshold}")
        self.logger.info("-" * 40)
        
        for i, vector in enumerate(retrieved_vectors, 1):
            self.logger.info(f"📄 Vector {i}:")
            self.logger.info(f"   🆔 ID: {vector.get('evidence_id', 'N/A')}")
            self.logger.info(f"   📁 Fuente: {vector.get('source', 'N/A')}")
            self.logger.info(f"   🏷️ Tipo: {vector.get('element_type', 'N/A')}")
            self.logger.info(f"   📊 Score: {vector.get('similarity_score', 'N/A')}")
            self.logger.info(f"   👤 Responsable: {vector.get('responsable', 'N/A')}")
            self.logger.info(f"   🐛 Defecto: {vector.get('defecto', 'N/A')}")
            text = vector.get('text', '')
            self.logger.info(f"   📝 Contenido: {self._truncate_if_long(text, 500)}")
            self.logger.info("")
        self.logger.info("")
    
    def log_rag_summary(self, all_retrieved_data: Dict[str, Any]):
        """Registra un resumen completo de toda la información RAG recuperada."""
        self.logger.info("📋 RESUMEN COMPLETO DE RECUPERACIÓN RAG")
        self.logger.info("=" * 60)
        
        # Esquemas
        if 'schema_context' in all_retrieved_data:
            schema_data = all_retrieved_data['schema_context']
            self.logger.info("🗄️ ESQUEMAS DE BASE DE DATOS:")
            self.logger.info(f"   📚 Fuentes: {schema_data.get('source_count', 0)}")
            self.logger.info(f"   📄 Contenido: {self._truncate_if_long(schema_data.get('context', ''), 1000)}")
            self.logger.info("")
        
        # Snippets de negocio
        if 'business_snippets' in all_retrieved_data:
            snippets_data = all_retrieved_data['business_snippets']
            self.logger.info("📋 SNIPPETS DE NEGOCIO:")
            for snippet_type, snippets in snippets_data.items():
                self.logger.info(f"   📖 {snippet_type.upper()}: {len(snippets)} snippets")
                for i, snippet in enumerate(snippets[:2], 1):  # Solo primeros 2
                    self.logger.info(f"      {i}. {snippet.get('source', 'N/A')} - {self._truncate_if_long(snippet.get('text', ''), 200)}")
            self.logger.info("")
        
        # Evidencia multimodal
        if 'multimodal_evidence' in all_retrieved_data:
            multimodal_data = all_retrieved_data['multimodal_evidence']
            self.logger.info("🖼️ EVIDENCIA MULTIMODAL:")
            self.logger.info(f"   📊 Elementos: {len(multimodal_data)}")
            modalities = list(set(e.get('element_type', 'unknown') for e in multimodal_data))
            self.logger.info(f"   🎨 Modalidades: {modalities}")
            for i, evidence in enumerate(multimodal_data[:3], 1):  # Solo primeros 3
                self.logger.info(f"      {i}. {evidence.get('element_type', 'N/A')} - {evidence.get('source', 'N/A')} (score: {evidence.get('similarity_score', 'N/A')})")
            self.logger.info("")
        
        # Estadísticas generales
        total_sources = 0
        total_content_length = 0
        
        if 'schema_context' in all_retrieved_data:
            total_sources += 1
            total_content_length += len(all_retrieved_data['schema_context'].get('context', ''))
        
        if 'business_snippets' in all_retrieved_data:
            for snippets in all_retrieved_data['business_snippets'].values():
                total_sources += len(snippets)
                for snippet in snippets:
                    total_content_length += len(snippet.get('text', ''))
        
        if 'multimodal_evidence' in all_retrieved_data:
            total_sources += len(all_retrieved_data['multimodal_evidence'])
            for evidence in all_retrieved_data['multimodal_evidence']:
                total_content_length += len(evidence.get('text', ''))
        
        self.logger.info("📊 ESTADÍSTICAS GENERALES:")
        self.logger.info(f"   🔢 Total de fuentes recuperadas: {total_sources}")
        self.logger.info(f"   📏 Total de caracteres de contenido: {total_content_length:,}")
        self.logger.info(f"   🗂️ Tipos de información: {list(all_retrieved_data.keys())}")
        self.logger.info("=" * 60)
        self.logger.info("")
    
    def log_error(self, error_type: str, error_message: str, context: Optional[str] = None):
        """Registra errores en el flujo."""
        self.logger.error(f"❌ ERROR - {error_type.upper()}")
        self.logger.error(f"Mensaje: {error_message}")
        if context:
            self.logger.error(f"Contexto: {context}")
        self.logger.error("")
    
    def finish_report_generation(self, consultant_name: str, success: bool, total_charts: int, execution_time: Optional[float] = None):
        """Finaliza el logging del reporte."""
        status = "✅ COMPLETADO" if success else "❌ FALLIDO"
        self.logger.info("-" * 80)
        self.logger.info(f"🏁 REPORTE {status}")
        self.logger.info(f"📋 Consultor: {consultant_name}")
        self.logger.info(f"📊 Gráficos generados: {total_charts}")
        if execution_time:
            self.logger.info(f"⏱️ Tiempo total: {execution_time:.2f}s")
        self.logger.info(f"📋 Finalizado: {datetime.now().isoformat()}")
        self.logger.info("=" * 80)
        self.logger.info("")

# Instancia global para usar en todo el módulo
report_flow_logger = ReportFlowLogger()

