#!/usr/bin/env python3
"""
Script para gestionar colecciones de vectores en ChromaDB
Analiza todas las colecciones y permite eliminarlas desde la consola
"""

import sys
import os
from pathlib import Path
import chromadb
from typing import Dict, List, Optional

# Agregar el directorio del proyecto al path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.config.settings import VECTOR_STORE_DIR, CHROMA_COLLECTIONS

class VectorCollectionManager:
    """Gestor de colecciones de vectores en ChromaDB"""
    
    def __init__(self):
        self.vector_store_path = VECTOR_STORE_DIR
        self.collections_config = CHROMA_COLLECTIONS
        self.client = None
        
    def connect_to_chromadb(self) -> bool:
        """Conecta a ChromaDB"""
        try:
            print(f"🔗 Conectando a ChromaDB en: {self.vector_store_path}")
            self.client = chromadb.PersistentClient(path=str(self.vector_store_path))
            print("✅ Conexión exitosa a ChromaDB")
            return True
        except Exception as e:
            print(f"❌ Error conectando a ChromaDB: {e}")
            return False
    
    def list_all_collections(self) -> Dict[str, Dict]:
        """Lista todas las colecciones con información detallada"""
        if not self.client:
            print("❌ No hay conexión a ChromaDB")
            return {}
        
        collections_info = {}
        
        try:
            # Obtener todas las colecciones del cliente
            all_collections = self.client.list_collections()
            print(f"\n📊 COlecciones encontradas en ChromaDB: {len(all_collections)}")
            
            for collection in all_collections:
                collection_name = collection.name
                collection_info = {
                    'name': collection_name,
                    'count': collection.count(),
                    'metadata': collection.metadata or {},
                    'is_configured': collection_name in self.collections_config.values()
                }
                collections_info[collection_name] = collection_info
                
                # Mostrar información de la colección
                status_icon = "✅" if collection_info['is_configured'] else "⚠️"
                print(f"\n{status_icon} Colección: {collection_name}")
                print(f"   📊 Elementos: {collection_info['count']}")
                print(f"   ⚙️ Configurada: {'Sí' if collection_info['is_configured'] else 'No'}")
                
                if collection_info['metadata']:
                    print(f"   📋 Metadatos: {collection_info['metadata']}")
                else:
                    print(f"   📋 Metadatos: Sin metadatos")
            
            # Mostrar colecciones configuradas vs encontradas
            configured_names = set(self.collections_config.values())
            found_names = set(collections_info.keys())
            
            print(f"\n🔍 ANÁLISIS DE CONFIGURACIÓN:")
            print(f"   📋 Colecciones configuradas: {len(configured_names)}")
            for name in configured_names:
                if name in found_names:
                    print(f"      ✅ {name}")
                else:
                    print(f"      ❌ {name} (NO ENCONTRADA)")
            
            if found_names - configured_names:
                print(f"   🆕 Colecciones no configuradas: {len(found_names - configured_names)}")
                for name in found_names - configured_names:
                    print(f"      ⚠️ {name}")
            
            return collections_info
            
        except Exception as e:
            print(f"❌ Error listando colecciones: {e}")
            return {}
    
    def get_collection_details(self, collection_name: str) -> Optional[Dict]:
        """Obtiene detalles específicos de una colección"""
        if not self.client:
            return None
        
        try:
            collection = self.client.get_collection(name=collection_name)
            
            # Obtener una muestra de elementos para análisis
            sample = collection.get(limit=1, include=['metadatas', 'documents'])
            
            details = {
                'name': collection_name,
                'count': collection.count(),
                'metadata': collection.metadata or {},
                'has_sample': len(sample.get('documents', [])) > 0,
                'sample_metadata': sample.get('metadatas', [])[0] if sample.get('metadatas') else None
            }
            
            return details
            
        except Exception as e:
            print(f"❌ Error obteniendo detalles de {collection_name}: {e}")
            return None
    
    def delete_collection(self, collection_name: str) -> bool:
        """Elimina una colección específica"""
        if not self.client:
            print("❌ No hay conexión a ChromaDB")
            return False
        
        try:
            # Verificar si la colección existe
            if not self.client.get_collection(name=collection_name):
                print(f"❌ La colección '{collection_name}' no existe")
                return False
            
            # Confirmar eliminación
            print(f"\n⚠️ ADVERTENCIA: Estás a punto de eliminar la colección '{collection_name}'")
            print("   Esta acción es IRREVERSIBLE y eliminará todos los vectores almacenados.")
            
            confirm = input(f"\n¿Estás seguro de que quieres eliminar '{collection_name}'? (escribe 'SI' para confirmar): ")
            
            if confirm.upper() != 'SI':
                print("❌ Eliminación cancelada")
                return False
            
            # Eliminar la colección
            self.client.delete_collection(name=collection_name)
            print(f"✅ Colección '{collection_name}' eliminada exitosamente")
            return True
            
        except Exception as e:
            print(f"❌ Error eliminando colección '{collection_name}': {e}")
            return False
    
    def show_menu(self):
        """Muestra el menú principal"""
        print("\n" + "="*60)
        print("🗄️ GESTOR DE COLECCIONES DE VECTORES")
        print("="*60)
        print("1. 📊 Listar todas las colecciones")
        print("2. 🔍 Ver detalles de una colección específica")
        print("3. 🗑️ Eliminar una colección")
        print("4. 🔄 Actualizar lista de colecciones")
        print("5. ❌ Salir")
        print("="*60)

def main():
    """Función principal del script"""
    manager = VectorCollectionManager()
    
    # Conectar a ChromaDB
    if not manager.connect_to_chromadb():
        print("❌ No se pudo conectar a ChromaDB. Verifica la configuración.")
        return
    
    collections_info = {}
    
    while True:
        manager.show_menu()
        
        try:
            option = input("\nSelecciona una opción (1-5): ").strip()
            
            if option == '1':
                print("\n📊 LISTANDO COLECCIONES...")
                collections_info = manager.list_all_collections()
                
            elif option == '2':
                if not collections_info:
                    print("❌ Primero ejecuta la opción 1 para cargar las colecciones")
                    continue
                
                print("\n🔍 DETALLES DE COLECCIÓN")
                collection_name = input("Ingresa el nombre de la colección: ").strip()
                
                if collection_name in collections_info:
                    details = manager.get_collection_details(collection_name)
                    if details:
                        print(f"\n📋 DETALLES DE '{collection_name}':")
                        print(f"   📊 Elementos: {details['count']}")
                        print(f"   📋 Metadatos: {details['metadata']}")
                        print(f"   📄 Tiene muestra: {'Sí' if details['has_sample'] else 'No'}")
                        if details['sample_metadata']:
                            print(f"   🔍 Muestra de metadatos: {details['sample_metadata']}")
                else:
                    print(f"❌ Colección '{collection_name}' no encontrada")
                    print("Colecciones disponibles:")
                    for name in collections_info.keys():
                        print(f"   - {name}")
                
            elif option == '3':
                if not collections_info:
                    print("❌ Primero ejecuta la opción 1 para cargar las colecciones")
                    continue
                
                print("\n🗑️ ELIMINAR COLECCIÓN")
                print("Colecciones disponibles:")
                for i, (name, info) in enumerate(collections_info.items(), 1):
                    status = "✅" if info['is_configured'] else "⚠️"
                    print(f"   {i}. {status} {name} ({info['count']} elementos)")
                
                try:
                    choice = input("\nSelecciona el número de la colección a eliminar: ").strip()
                    choice_idx = int(choice) - 1
                    collection_names = list(collections_info.keys())
                    
                    if 0 <= choice_idx < len(collection_names):
                        collection_name = collection_names[choice_idx]
                        manager.delete_collection(collection_name)
                        # Actualizar la lista después de eliminar
                        collections_info = manager.list_all_collections()
                    else:
                        print("❌ Opción inválida")
                except ValueError:
                    print("❌ Por favor ingresa un número válido")
                
            elif option == '4':
                print("\n🔄 ACTUALIZANDO LISTA...")
                collections_info = manager.list_all_collections()
                
            elif option == '5':
                print("\n👋 ¡Hasta luego!")
                break
                
            else:
                print("❌ Opción inválida. Por favor selecciona 1-5.")
                
        except KeyboardInterrupt:
            print("\n\n👋 ¡Hasta luego!")
            break
        except Exception as e:
            print(f"❌ Error inesperado: {e}")

if __name__ == "__main__":
    main()


