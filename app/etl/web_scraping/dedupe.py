"""
Sistema de deduplicación para evitar procesar contenido repetido.
"""
import hashlib
import json
import logging
from typing import Dict, List, Optional, Set
from datetime import datetime
from pathlib import Path

from app.config.settings import SCRAPING_LOGS_DIR, SCRAPING_CONFIG

logger = logging.getLogger(__name__)

class DedupeManager:
    """Gestiona la deduplicación de contenido scrapeado."""
    
    def __init__(self):
        self.config = SCRAPING_CONFIG["dedupe"]
        self.dedupe_file = SCRAPING_LOGS_DIR / "content_hashes.json"
        self.hashes_db = self._load_hashes_db()
    
    def _load_hashes_db(self) -> Dict[str, Dict]:
        """Carga la base de datos de hashes existentes."""
        try:
            if self.dedupe_file.exists():
                with open(self.dedupe_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                logger.info(f"📚 Base de hashes cargada: {len(data)} entradas")
                return data
        except Exception as e:
            logger.warning(f"No se pudo cargar base de hashes: {e}")
        
        return {}
    
    def _save_hashes_db(self):
        """Guarda la base de datos de hashes."""
        try:
            self.dedupe_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.dedupe_file, 'w', encoding='utf-8') as f:
                json.dump(self.hashes_db, f, indent=2, ensure_ascii=False)
            logger.debug(f"💾 Base de hashes guardada: {len(self.hashes_db)} entradas")
        except Exception as e:
            logger.error(f"Error guardando base de hashes: {e}")
    
    def generate_content_hash(self, content: str, url: str) -> str:
        """Genera hash único para el contenido."""
        # Normalizar contenido para hash estable
        normalized = content.strip().lower()
        # Incluir URL para hacer hash único por página
        hash_input = f"{url}:::{normalized}"
        
        if self.config["hash_algorithm"] == "sha256":
            return hashlib.sha256(hash_input.encode('utf-8')).hexdigest()
        else:
            return hashlib.md5(hash_input.encode('utf-8')).hexdigest()
    
    def is_duplicate(self, content: str, url: str) -> Dict[str, any]:
        """
        Verifica si el contenido es duplicado.
        
        Returns:
            Dict con: is_duplicate, content_hash, last_seen, action
        """
        if not self.config["enabled"]:
            return {
                "is_duplicate": False,
                "content_hash": None,
                "last_seen": None,
                "action": "skip_deduplication"
            }
        
        content_hash = self.generate_content_hash(content, url)
        
        if content_hash in self.hashes_db:
            entry = self.hashes_db[content_hash]
            logger.info(f"🔄 Contenido duplicado detectado: {url} (último visto: {entry['last_seen']})")
            
            return {
                "is_duplicate": True,
                "content_hash": content_hash,
                "last_seen": entry["last_seen"],
                "action": "skip_processing"
            }
        else:
            logger.info(f"✨ Contenido nuevo detectado: {url}")
            return {
                "is_duplicate": False,
                "content_hash": content_hash,
                "last_seen": None,
                "action": "process_new"
            }
    
    def register_content(self, content: str, url: str, metadata: Dict = None) -> str:
        """
        Registra contenido nuevo en la base de hashes.
        
        Returns:
            content_hash del contenido registrado
        """
        content_hash = self.generate_content_hash(content, url)
        
        entry = {
            "url": url,
            "content_length": len(content),
            "first_seen": datetime.now().isoformat(),
            "last_seen": datetime.now().isoformat(),
            "times_seen": 1,
            "metadata": metadata or {}
        }
        
        if content_hash in self.hashes_db:
            # Actualizar entrada existente
            existing = self.hashes_db[content_hash]
            existing["last_seen"] = datetime.now().isoformat()
            existing["times_seen"] = existing.get("times_seen", 1) + 1
            existing["metadata"].update(metadata or {})
        else:
            # Nueva entrada
            self.hashes_db[content_hash] = entry
        
        self._save_hashes_db()
        
        logger.debug(f"📝 Contenido registrado: {content_hash[:8]}... ({url})")
        return content_hash
    
    def get_stats(self) -> Dict[str, any]:
        """Devuelve estadísticas de la base de deduplicación."""
        if not self.hashes_db:
            return {"total_entries": 0, "total_urls": 0}
        
        urls = set(entry["url"] for entry in self.hashes_db.values())
        
        return {
            "total_entries": len(self.hashes_db),
            "total_urls": len(urls),
            "avg_content_length": sum(entry["content_length"] for entry in self.hashes_db.values()) // len(self.hashes_db),
            "dedupe_file_path": str(self.dedupe_file)
        }
    
    def cleanup_old_entries(self, days_old: int = 30):
        """Limpia entradas antigas de la base de hashes."""
        from datetime import datetime, timedelta
        
        cutoff_date = datetime.now() - timedelta(days=days_old)
        
        old_hashes = []
        for content_hash, entry in self.hashes_db.items():
            try:
                last_seen = datetime.fromisoformat(entry["last_seen"])
                if last_seen < cutoff_date:
                    old_hashes.append(content_hash)
            except Exception:
                # Si no se puede parsear fecha, considerar como antigua
                old_hashes.append(content_hash)
        
        for content_hash in old_hashes:
            del self.hashes_db[content_hash]
        
        if old_hashes:
            self._save_hashes_db()
            logger.info(f"🧹 Limpieza completada: {len(old_hashes)} entradas antigas eliminadas")
        
        return len(old_hashes)