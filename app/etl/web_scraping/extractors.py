"""
Extractores de contenido limpio desde HTML raw.
"""
import logging
import re
from typing import Dict, Optional
from bs4 import BeautifulSoup
from datetime import datetime

from app.config.settings import SCRAPING_CONFIG

logger = logging.getLogger(__name__)

class ContentExtractor:
    """Extrae y limpia contenido de HTML usando BeautifulSoup."""
    
    def __init__(self):
        self.config = SCRAPING_CONFIG["extraction"]
    
    def extract_clean_content(self, html_content: str, url: str, title: str = "") -> Dict[str, any]:
        """
        Extrae contenido limpio usando BeautifulSoup.
        
        Returns:
            Dict con: success, clean_text, metadata, extraction_stats
        """
        result = {
            "success": False,
            "clean_text": "",
            "metadata": {
                "extraction_method": "",
                "original_length": len(html_content),
                "clean_length": 0,
                "title": title,
                "url": url,
                "extracted_at": datetime.now().isoformat()
            },
            "extraction_stats": {}
        }
        
        # Extraer contenido con BeautifulSoup
        clean_text = self._extract_with_beautifulsoup(html_content)
        
        if clean_text and len(clean_text) >= self.config["min_content_length"]:
            result["clean_text"] = clean_text
            result["metadata"]["extraction_method"] = "beautifulsoup"
            logger.info(f"✅ Extracción exitosa: {len(clean_text)} chars")
        else:
            logger.error(f"❌ Extracción falló para {url}")
            result["metadata"]["extraction_method"] = "failed"
            return result
        
        # Validaciones finales
        if len(result["clean_text"]) > self.config["max_content_length"]:
            result["clean_text"] = result["clean_text"][:self.config["max_content_length"]]
            logger.info(f"🔄 Contenido truncado a {self.config['max_content_length']} chars")
        
        # Limpieza final
        result["clean_text"] = self._final_cleanup(result["clean_text"])
        
        # Estadísticas
        result["metadata"]["clean_length"] = len(result["clean_text"])
        result["extraction_stats"] = {
            "compression_ratio": round(len(result["clean_text"]) / len(html_content), 3),
            "word_count": len(result["clean_text"].split()),
            "line_count": len(result["clean_text"].split('\n'))
        }
        
        result["success"] = True
        return result
    
    def _extract_with_beautifulsoup(self, html_content: str) -> Optional[str]:
        """Extrae contenido usando BeautifulSoup."""
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Remover elementos no deseados
            for element in soup(['script', 'style', 'nav', 'header', 'footer', 'aside', 'advertisement']):
                element.decompose()
            
            # Buscar contenido principal por selectores comunes
            main_content = None
            
            # Lista de selectores para contenido principal
            content_selectors = [
                'main',
                '[role="main"]',
                '.main-content',
                '.content',
                '.post-content',
                '.article-content',
                '.entry-content',
                'article',
                '.container .row .col'  # Bootstrap común
            ]
            
            for selector in content_selectors:
                try:
                    element = soup.select_one(selector)
                    if element:
                        main_content = element
                        break
                except Exception:
                    continue
            
            # Si no encuentra selectores específicos, usar body
            if not main_content:
                main_content = soup.find('body')
            
            if main_content:
                # Extraer solo texto, manteniendo estructura básica
                text = main_content.get_text(separator='\n', strip=True)
                return text
            
        except Exception as e:
            logger.warning(f"Error en BeautifulSoup: {e}")
        
        return None
    
    def _final_cleanup(self, text: str) -> str:
        """Limpieza final del texto extraído."""
        if not text:
            return ""
        
        # Normalizar espacios en blanco
        text = re.sub(r'\s+', ' ', text)
        
        # Normalizar saltos de línea
        text = re.sub(r'\n\s*\n', '\n\n', text)
        
        # Remover líneas muy cortas (probablemente navegación)
        lines = text.split('\n')
        filtered_lines = []
        
        for line in lines:
            line = line.strip()
            if len(line) >= 10:  # Solo líneas con contenido sustancial
                filtered_lines.append(line)
        
        text = '\n'.join(filtered_lines)
        
        # Limitar líneas vacías consecutivas
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        return text.strip()