"""
Cliente Selenium para web scraping automatizado.
"""
import logging
import time
from typing import Dict, List
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException, TimeoutException
from webdriver_manager.chrome import ChromeDriverManager
import platform

from app.config.settings import SCRAPING_CONFIG, DOCS_RAW_DIR

logger = logging.getLogger(__name__)

class SeleniumClient:
    """Cliente Selenium para scraping web automatizado."""
    
    def __init__(self):
        self.config = SCRAPING_CONFIG["browser"]
    
    def setup_driver(self) -> webdriver.Chrome:
        """Configura y retorna un driver de Chrome optimizado."""
        options = Options()
        
        if self.config["headless"]:
            options.add_argument("--headless=new")
        
        # Optimizaciones para rendimiento y estabilidad
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-web-security")
        options.add_argument("--disable-features=VizDisplayCompositor")
        options.add_argument("--disable-renderer-backgrounding")
        options.add_argument("--disable-features=TranslateUI")
        options.add_argument(f"--user-agent={self.config['user_agent']}")
        
        # Configuración específica para Windows
        if platform.system() == "Windows":
            options.add_argument("--disable-software-rasterizer")
            options.add_argument("--no-first-run")
            options.add_argument("--disable-default-apps")
        
        try:
            # LÓGICA QUE FUNCIONA (copiada del test exitoso)
            import shutil
            import os
            
            # Limpiar caché de webdriver-manager
            cache_dir = os.path.expanduser("~/.wdm")
            if os.path.exists(cache_dir):
                shutil.rmtree(cache_dir)
                logger.info("🧹 Caché de ChromeDriver limpiado")
            
            # Descargar ChromeDriver
            driver_path = ChromeDriverManager().install()
            logger.info(f"ChromeDriver path original: {driver_path}")
            
            # VERIFICAR y corregir la ruta si es necesaria (lógica del test)
            if not os.path.isfile(driver_path) or driver_path.endswith('.chromedriver'):
                driver_dir = os.path.dirname(driver_path)
                # Buscar el ejecutable real
                for root, dirs, files in os.walk(driver_dir):
                    for file in files:
                        if file == 'chromedriver.exe':
                            driver_path = os.path.join(root, file)
                            logger.info(f"ChromeDriver ejecutable encontrado: {driver_path}")
                            break
                    if driver_path.endswith('.exe'):
                        break
            
            if not os.path.isfile(driver_path):
                raise RuntimeError(f"No se encontró chromedriver.exe")
            
            service = Service(driver_path)
            driver = webdriver.Chrome(service=service, options=options)
            
            # Configurar timeouts del driver
            driver.set_page_load_timeout(self.config["page_load_timeout"])
            driver.implicitly_wait(5)
            
            logger.info("✅ Driver de Chrome configurado exitosamente")
            return driver
            
        except Exception as e:
            logger.error(f"❌ Error configurando driver de Chrome: {e}")
            raise
    
    def scrape_page(self, url: str, source_name: str) -> Dict[str, any]:
        """
        Scrapea una página específica y devuelve metadatos + contenido.
        
        Returns:
            Dict con: success, url, content, title, metadata, errors
        """
        result = {
            "success": False,
            "url": url,
            "content": "",
            "title": "",
            "metadata": {},
            "errors": [],
            "scraped_at": datetime.now().isoformat()
        }
        
        driver = None
        try:
            logger.info(f"🌐 Iniciando scraping de: {url}")
            
            # Configurar driver
            driver = self.setup_driver()
            
            # Navegar a la URL
            driver.get(url)
            
            # Esperar que la página cargue
            wait = WebDriverWait(driver, self.config["wait_time"])
            wait.until(EC.presence_of_element_located((By.TAG_NAME, 'body')))
            
            # Espera adicional para contenido dinámico
            time.sleep(2)
            
            # Extraer información
            result["title"] = driver.title or "Sin título"
            result["content"] = driver.page_source
            result["metadata"] = {
                "url": url,
                "title": result["title"],
                "content_length": len(result["content"]),
                "scraped_at": result["scraped_at"],
                "source_name": source_name
            }
            
            # Guardar HTML raw para auditoría
            self._save_raw_html(result["content"], url, source_name)
            
            result["success"] = True
            logger.info(f"✅ Scraping exitoso: {url} ({len(result['content'])} chars)")
            
        except TimeoutException:
            error_msg = f"Timeout al cargar la página: {url}"
            logger.error(f"⏰ {error_msg}")
            result["errors"].append(error_msg)
            
        except WebDriverException as e:
            error_msg = f"Error del WebDriver para {url}: {str(e)}"
            logger.error(f"🚫 {error_msg}")
            result["errors"].append(error_msg)
            
        except Exception as e:
            error_msg = f"Error inesperado scrapeando {url}: {str(e)}"
            logger.error(f"❌ {error_msg}")
            result["errors"].append(error_msg)
            
        finally:
            if driver:
                try:
                    driver.quit()
                except:
                    pass  # Ignorar errores al cerrar
        
        return result
    
    def _save_raw_html(self, content: str, url: str, source_name: str):
        """Guarda el HTML raw para auditoría."""
        try:
            raw_dir = DOCS_RAW_DIR / source_name
            raw_dir.mkdir(parents=True, exist_ok=True)
            
            # Nombre de archivo seguro
            safe_filename = url.replace('https://', '').replace('http://', '').replace('/', '_').replace('?', '_').replace('&', '_')
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{safe_filename}_{timestamp}.html"
            
            file_path = raw_dir / filename
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
                
            logger.debug(f"�� HTML raw guardado: {file_path}")
            
        except Exception as e:
            logger.warning(f"No se pudo guardar HTML raw: {e}")

    def scrape_multiple(self, urls: List[str], source_name: str) -> List[Dict[str, any]]:
        """Scrapea múltiples URLs secuencialmente."""
        results = []
        
        logger.info(f"🚀 Iniciando scraping de {len(urls)} URLs para '{source_name}'")
        
        for i, url in enumerate(urls, 1):
            logger.info(f"[{i}/{len(urls)}] Procesando: {url}")
            
            result = self.scrape_page(url, source_name)
            results.append(result)
            
            # Pausa entre requests para ser respetuoso
            if i < len(urls):
                time.sleep(1)
        
        successful = sum(1 for r in results if r["success"])
        logger.info(f"✅ Scraping completado: {successful}/{len(urls)} exitosos")
        
        return results
