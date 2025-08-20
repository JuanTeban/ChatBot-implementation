from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import platform
import shutil
import os

def test_chrome_driver():
    print(f"Sistema: {platform.architecture()}")
    print(f"Plataforma: {platform.system()}")
    
    try:
        # Limpiar caché de webdriver-manager completamente
        cache_dir = os.path.expanduser("~/.wdm")
        if os.path.exists(cache_dir):
            shutil.rmtree(cache_dir)
            print("✅ Caché de ChromeDriver limpiado")
        
        # Descargar ChromeDriver
        driver_path = ChromeDriverManager().install()
        print(f"ChromeDriver path original: {driver_path}")
        
        # VERIFICAR y corregir la ruta si es necesaria
        if not os.path.isfile(driver_path) or driver_path.endswith('.chromedriver'):
            driver_dir = os.path.dirname(driver_path)
            # Buscar el ejecutable real
            for root, dirs, files in os.walk(driver_dir):
                for file in files:
                    if file == 'chromedriver.exe':
                        driver_path = os.path.join(root, file)
                        print(f"ChromeDriver ejecutable encontrado: {driver_path}")
                        break
                if driver_path.endswith('.exe'):
                    break
        
        if not os.path.isfile(driver_path):
            raise RuntimeError(f"No se encontró chromedriver.exe en: {driver_dir}")
        
        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-software-rasterizer")
        
        service = Service(driver_path)
        driver = webdriver.Chrome(service=service, options=options)
        
        driver.get("https://www.google.com")
        print(f"✅ Título: {driver.title}")
        
        driver.quit()
        print("✅ ChromeDriver funciona correctamente!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_chrome_driver()