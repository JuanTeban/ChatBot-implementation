#!/usr/bin/env python3
"""
Script para verificar todas las colecciones de ChromaDB y mostrar previsualizaciones.
Verifica las colecciones definidas en settings.py: schema_knowledge, business_rules, external_docs, multimodal_evidence
"""

import sys
import logging
from pathlib import Path
import chromadb
import json
from datetime import datetime

# Añadir el directorio raíz al path
sys.path.insert(0, str(Path(__file__).parent))

from app.config.settings import VECTOR_STORE_DIR, CHROMA_COLLECTIONS

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def verify_collection(collection_name: str, collection) -> dict:
    """
    Verifica una colección específica y retorna información detallada.
    """
    try:
        # Obtener estadísticas básicas
        count = collection.count()
        
        if count == 0:
            return {
                "name": collection_name,
                "status": "empty",
                "count": 0,
                "sample": None,
                "metadata_fields": [],
                "content_types": {}
            }
        
        # Obtener muestra de datos
        sample_data = collection.get(
            include=["documents", "metadatas", "embeddings"],
            limit=min(5, count)  # Máximo 5 elementos para la muestra
        )
        
        # Analizar metadatos
        metadatas = sample_data.get("metadatas", [])
        metadata_fields = set()
        content_types = {}
        
        for metadata in metadatas:
            if metadata:
                # Campos de metadatos
                metadata_fields.update(metadata.keys())
                
                # Tipos de contenido (element_type, rule_type, etc.)
                element_type = metadata.get("element_type", "unknown")
                rule_type = metadata.get("rule_type", "unknown")
                table_name = metadata.get("table_name", "unknown")
                
                if element_type != "unknown":
                    content_types[element_type] = content_types.get(element_type, 0) + 1
                elif rule_type != "unknown":
                    content_types[f"rule_{rule_type}"] = content_types.get(f"rule_{rule_type}", 0) + 1
                elif table_name != "unknown":
                    content_types["table"] = content_types.get("table", 0) + 1
                else:
                    content_types["unknown"] = content_types.get("unknown", 0) + 1
        
        # Preparar muestra de contenido
        documents = sample_data.get("documents", [])
        sample_content = []
        
        for i, doc in enumerate(documents):
            if doc:
                # Truncar contenido largo
                preview = str(doc)[:200].replace('\n', ' ')
                if len(str(doc)) > 200:
                    preview += "..."
                
                sample_content.append({
                    "index": i + 1,
                    "preview": preview,
                    "length": len(str(doc)),
                    "metadata": metadatas[i] if i < len(metadatas) else {}
                })
        
        return {
            "name": collection_name,
            "status": "active",
            "count": count,
            "sample": sample_content,
            "metadata_fields": list(metadata_fields),
            "content_types": content_types
        }
        
    except Exception as e:
        return {
            "name": collection_name,
            "status": "error",
            "error": str(e),
            "count": 0,
            "sample": None,
            "metadata_fields": [],
            "content_types": {}
        }

def display_collection_info(collection_info: dict):
    """
    Muestra información de una colección de forma legible.
    """
    print(f"\n{'='*80}")
    print(f"📊 COLECCIÓN: {collection_info['name'].upper()}")
    print(f"{'='*80}")
    
    if collection_info['status'] == 'error':
        print(f"❌ ERROR: {collection_info['error']}")
        return
    
    if collection_info['status'] == 'empty':
        print(f"📭 COLECCIÓN VACÍA")
        print(f"   No hay elementos vectorizados en esta colección.")
        return
    
    print(f"✅ ESTADO: Activa")
    print(f"📈 TOTAL ELEMENTOS: {collection_info['count']}")
    
    # Mostrar tipos de contenido
    if collection_info['content_types']:
        print(f"\n📋 DISTRIBUCIÓN DE CONTENIDO:")
        for content_type, count in collection_info['content_types'].items():
            percentage = (count / collection_info['count']) * 100
            print(f"   • {content_type}: {count} ({percentage:.1f}%)")
    
    # Mostrar campos de metadatos
    if collection_info['metadata_fields']:
        print(f"\n🏷️ CAMPOS DE METADATOS:")
        for field in sorted(collection_info['metadata_fields']):
            print(f"   • {field}")
    
    # Mostrar muestra de contenido
    if collection_info['sample']:
        print(f"\n📄 MUESTRA DE CONTENIDO (primeros {len(collection_info['sample'])} elementos):")
        for item in collection_info['sample']:
            print(f"\n   --- Elemento {item['index']} ---")
            print(f"   📏 Longitud: {item['length']} caracteres")
            
            # Mostrar metadatos relevantes
            metadata = item.get('metadata', {})
            if metadata:
                relevant_fields = ['element_type', 'rule_type', 'table_name', 'source_file', 'responsable', 'defecto']
                shown_fields = []
                for field in relevant_fields:
                    if field in metadata and metadata[field]:
                        shown_fields.append(f"{field}: {metadata[field]}")
                
                if shown_fields:
                    print(f"   🏷️ Metadatos: {', '.join(shown_fields)}")
            
            print(f"   📝 Preview: {item['preview']}")

def main():
    """
    Función principal que verifica todas las colecciones.
    """
    print("🔍 VERIFICACIÓN COMPLETA DE COLECCIONES CHROMADB")
    print("="*80)
    print(f"📁 Directorio de vectores: {VECTOR_STORE_DIR}")
    print(f"🕐 Fecha de verificación: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Verificar que el directorio existe
    if not VECTOR_STORE_DIR.exists():
        print(f"\n❌ ERROR: El directorio de vectores no existe: {VECTOR_STORE_DIR}")
        return
    
    try:
        # Conectar a ChromaDB
        print(f"\n🔌 Conectando a ChromaDB...")
        client = chromadb.PersistentClient(path=str(VECTOR_STORE_DIR))
        print(f"✅ Conexión exitosa")
        
        # Obtener todas las colecciones existentes
        existing_collections = client.list_collections()
        existing_names = [col.name for col in existing_collections]
        
        print(f"\n📋 COLECCIONES ENCONTRADAS: {len(existing_collections)}")
        for col in existing_collections:
            print(f"   • {col.name}")
        
        # Verificar cada colección definida en settings
        print(f"\n🔍 VERIFICANDO COLECCIONES DEFINIDAS EN SETTINGS:")
        all_results = []
        
        for collection_key, collection_name in CHROMA_COLLECTIONS.items():
            print(f"\n🔄 Verificando {collection_key} -> {collection_name}...")
            
            try:
                # Intentar obtener la colección
                collection = client.get_collection(name=collection_name)
                collection_info = verify_collection(collection_name, collection)
                all_results.append(collection_info)
                
            except Exception as e:
                # La colección no existe
                collection_info = {
                    "name": collection_name,
                    "status": "not_found",
                    "error": f"Colección no existe: {str(e)}",
                    "count": 0,
                    "sample": None,
                    "metadata_fields": [],
                    "content_types": {}
                }
                all_results.append(collection_info)
        
        # Mostrar resultados detallados
        print(f"\n{'='*80}")
        print(f"📊 RESUMEN COMPLETO DE COLECCIONES")
        print(f"{'='*80}")
        
        total_elements = 0
        active_collections = 0
        
        for collection_info in all_results:
            display_collection_info(collection_info)
            
            if collection_info['status'] == 'active':
                active_collections += 1
                total_elements += collection_info['count']
        
        # Resumen final
        print(f"\n{'='*80}")
        print(f"📈 RESUMEN FINAL")
        print(f"{'='*80}")
        print(f"✅ Colecciones activas: {active_collections}/{len(CHROMA_COLLECTIONS)}")
        print(f"📊 Total elementos vectorizados: {total_elements}")
        print(f"📁 Directorio: {VECTOR_STORE_DIR}")
        
        # Guardar reporte
        report_data = {
            "timestamp": datetime.now().isoformat(),
            "vector_store_dir": str(VECTOR_STORE_DIR),
            "collections_checked": len(CHROMA_COLLECTIONS),
            "active_collections": active_collections,
            "total_elements": total_elements,
            "collections": all_results
        }
        
        report_file = Path("collections_verification_report.json")
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)
        
        print(f"📝 Reporte detallado guardado en: {report_file}")
        
    except Exception as e:
        print(f"\n❌ ERROR CRÍTICO: {e}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")

if __name__ == "__main__":
    main()



