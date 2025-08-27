# cli/run_multimodal_rag.py
from __future__ import annotations
import argparse
import asyncio
import logging
import sys
import io
from pathlib import Path
from datetime import datetime

from app.config.settings import MULTIMODAL_INPUT_ROOT
from app.multimodal_rag.ingestion import ingest_tree, clear_multimodal_collection

# Salida UTF-8 para consola (evita UnicodeEncodeError por emojis)
stdout_utf8 = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
stderr_utf8 = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Configurar logging detallado
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(asctime)s %(name)s :: %(message)s",
    handlers=[
        logging.StreamHandler(stream=stdout_utf8),
        logging.FileHandler(f"multimodal_ingestion_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log", encoding="utf-8"),
    ],
    force=True,  # asegura que aplique esta config
)
log = logging.getLogger("mmrag.cli")

def main():
    ap = argparse.ArgumentParser("RAG Multimodal CLI")
    sub = ap.add_subparsers(dest="cmd", required=True)

    ing = sub.add_parser("ingest", help="Ingestar árbol de responsable/defecto")
    ing.add_argument("--root", type=str, default=MULTIMODAL_INPUT_ROOT, help="Ruta root: responsable/defecto/*")
    ing.add_argument("--responsable", type=str, default=None, help="Responsable específico")
    ing.add_argument("--defecto", type=str, default=None, help="Defecto específico")
    ing.add_argument("--clear", action="store_true", help="Limpiar colección antes de ingestar")

    sub.add_parser("clear", help="Limpiar colección multimodal")

    args = ap.parse_args()

    if args.cmd == "clear":
        log.info("🧹 LIMPIANDO COLECCIÓN MULTIMODAL")
        log.info("="*60)
        
        try:
            result = asyncio.run(clear_multimodal_collection())
            
            if result["success"]:
                log.info(f"✅ Colección limpiada: {result['deleted_chunks']} chunks eliminados")
            else:
                log.error(f"❌ Error limpiando colección: {result.get('error', 'Unknown error')}")
                
        except Exception as e:
            log.error(f"❌ Error en limpieza: {e}")
            import traceback
            log.error(f"Traceback: {traceback.format_exc()}")

    elif args.cmd == "ingest":
        if not args.root:
            ap.error("--root es requerido si MULTIMODAL_INPUT_ROOT no está en .env")
        
        # Verificar que el directorio existe
        root_path = Path(args.root)
        if not root_path.exists():
            log.error(f"❌ Directorio no encontrado: {root_path}")
            return
        
        log.info("🚀 INICIANDO INGESTA MULTIMODAL")
        log.info("="*60)
        log.info(f"📁 Directorio raíz: {root_path}")
        log.info(f"👤 Responsable: {args.responsable or 'TODOS'}")
        log.info(f"🐛 Defecto: {args.defecto or 'TODOS'}")
        log.info(f"🧹 Limpiar colección: {args.clear}")
        log.info("="*60)
        
        # Limpiar colección si se solicita
        if args.clear:
            log.info("🧹 Limpiando colección antes de ingestar...")
            try:
                clear_result = asyncio.run(clear_multimodal_collection())
                if clear_result["success"]:
                    log.info(f"✅ Colección limpiada: {clear_result['deleted_chunks']} chunks eliminados")
                else:
                    log.warning(f"⚠️ Error limpiando colección: {clear_result.get('error', 'Unknown error')}")
            except Exception as e:
                log.warning(f"⚠️ Error en limpieza: {e}")
        
        # Ejecutar ingesta
        try:
            result = asyncio.run(ingest_tree(
                root=root_path,
                responsable=args.responsable,
                defecto=args.defecto
            ))
            
            # Mostrar resultados
            log.info("✅ INGESTA COMPLETADA")
            log.info("="*60)
            log.info(f"📊 Archivos procesados: {result['processed_files']}")
            log.info(f"✅ Archivos exitosos: {result['successful_files']}")
            log.info(f"📄 Total chunks: {result['total_chunks']}")
            log.info(f"✅ Chunks vectorizados: {result['successful_chunks']}")
            log.info(f"📝 Log detallado: {result['log_file']}")
            
            if result['successful_chunks'] > 0:
                log.info("🎉 ¡Ingesta exitosa! Los datos están disponibles para RAG.")
            else:
                log.warning("⚠️ No se vectorizaron chunks. Revisar logs para errores.")
                
        except Exception as e:
            log.error(f"❌ Error en ingesta: {e}")
            import traceback
            log.error(f"Traceback: {traceback.format_exc()}")

if __name__ == "__main__":
    main()
