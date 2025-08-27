# scripts/pdf_worker_url.py
import sys, os, asyncio
import time
import logging
from pathlib import Path
from pyppeteer import launch

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Configurar logging para el worker
def setup_worker_logging():
    logger = logging.getLogger("pdf_worker")
    logger.setLevel(logging.INFO)
    
    # Crear directorio de logs si no existe
    log_dir = Path("data_store/logs/pdf_flow")
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Handler para logs del worker
    from logging.handlers import RotatingFileHandler
    handler = RotatingFileHandler(
        log_dir / f"pdf_worker_{time.strftime('%Y%m%d')}.log",
        maxBytes=5*1024*1024,  # 5MB
        backupCount=3,
        encoding='utf-8'  # Forzar encoding UTF-8 para Windows
    )
    
    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    handler.setFormatter(formatter)
    
    if not logger.handlers:
        logger.addHandler(handler)
    
    return logger

def _find_chrome():
    for p in [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]:
        if Path(p).exists():
            return p
    raise FileNotFoundError("Instala Chrome/Edge o ajusta la ruta en pdf_worker_url.py")

async def run(url: str, out_pdf: str):
    logger = setup_worker_logging()
    
    logger.info("=" * 60)
    logger.info("🚀 INICIANDO WORKER DE GENERACIÓN DE PDF")
    logger.info(f"📋 URL: {url}")
    logger.info(f"📋 Output: {out_pdf}")
    logger.info("=" * 60)
    
    start_time = time.time()
    
    try:
        # Paso 1: Inicializar browser
        logger.info("⏱️ INICIO: inicializar_browser")
        browser_start = time.time()
        browser = await launch(executablePath=_find_chrome(), args=["--no-sandbox","--disable-gpu"])
        browser_time = time.time() - browser_start
        logger.info(f"✅ FIN: inicializar_browser - Duración: {browser_time:.2f}s")
        
        # Paso 2: Crear nueva página
        logger.info("⏱️ INICIO: crear_pagina")
        page_start = time.time()
        page = await browser.newPage()
        page_time = time.time() - page_start
        logger.info(f"✅ FIN: crear_pagina - Duración: {page_time:.2f}s")
        
        # Paso 3: Configurar viewport
        logger.info("⏱️ INICIO: configurar_viewport")
        viewport_start = time.time()
        await page.setViewport({'width': 1600, 'height': 1200})
        viewport_time = time.time() - viewport_start
        logger.info(f"✅ FIN: configurar_viewport - Duración: {viewport_time:.2f}s")
        
        # Paso 4: Navegar a la URL
        logger.info("⏱️ INICIO: navegar_url")
        navigate_start = time.time()
        await page.goto(url, {"waitUntil": "networkidle2", "timeout": 60000})
        navigate_time = time.time() - navigate_start
        logger.info(f"✅ FIN: navegar_url - Duración: {navigate_time:.2f}s")
        
        # Paso 5: Esperar renderizado de gráficos
        logger.info("⏱️ INICIO: esperar_renderizado")
        render_start = time.time()
        await asyncio.sleep(8)
        render_time = time.time() - render_start
        logger.info(f"✅ FIN: esperar_renderizado - Duración: {render_time:.2f}s")
        
        # Paso 6: Aplicar estilos CSS
        logger.info("⏱️ INICIO: aplicar_estilos_css")
        css_start = time.time()
        await page.evaluate("""
            const style = document.createElement('style');
            style.textContent = `
                @media print {
                    body { background: #fff !important; }
                    .no-print, form.toolbar, .hint, details, .btn-success, .approval-section { 
                        display: none !important; 
                    }
                    .box, .chart-container, section { 
                        break-inside: avoid; 
                        page-break-inside: avoid; 
                    }
                    h2, h3 { 
                        break-after: avoid; 
                        page-break-after: avoid; 
                    }
                    .chart-container { 
                        min-height: 400px !important; 
                        height: auto !important; 
                        width: 100% !important; 
                        overflow: visible !important; 
                    }
                    .js-plotly-plot, .plotly { 
                        width: 100% !important; 
                        height: auto !important; 
                        min-height: 400px !important; 
                        overflow: visible !important; 
                    }
                }
            `;
            document.head.appendChild(style);
        """)
        css_time = time.time() - css_start
        logger.info(f"✅ FIN: aplicar_estilos_css - Duración: {css_time:.2f}s")
        
        # Paso 7: Emular medios de impresión
        logger.info("⏱️ INICIO: emular_medios_impresion")
        media_start = time.time()
        await page.emulateMedia(mediaType='print')
        media_time = time.time() - media_start
        logger.info(f"✅ FIN: emular_medios_impresion - Duración: {media_time:.2f}s")

        # Paso 8: Generar PDF
        logger.info("⏱️ INICIO: generar_pdf")
        pdf_start = time.time()
        await page.pdf({
            "path": out_pdf, 
            "format": "A4",
            "printBackground": True,
            "margin": {"top":"16mm","right":"12mm","bottom":"16mm","left":"12mm"},
            "displayHeaderFooter": False,
            "preferCSSPageSize": True
        })
        pdf_time = time.time() - pdf_start
        logger.info(f"✅ FIN: generar_pdf - Duración: {pdf_time:.2f}s")
        
        # Paso 9: Cerrar browser
        logger.info("⏱️ INICIO: cerrar_browser")
        close_start = time.time()
        await browser.close()
        close_time = time.time() - close_start
        logger.info(f"✅ FIN: cerrar_browser - Duración: {close_time:.2f}s")
        
        # Resumen final
        total_time = time.time() - start_time
        logger.info("=" * 60)
        logger.info("✅ GENERACIÓN DE PDF COMPLETADA")
        logger.info(f"⏱️ Tiempo total: {total_time:.2f}s")
        logger.info(f"📊 Desglose:")
        logger.info(f"   - Browser init: {browser_time:.2f}s")
        logger.info(f"   - Navegación: {navigate_time:.2f}s")
        logger.info(f"   - Renderizado: {render_time:.2f}s")
        logger.info(f"   - Generación PDF: {pdf_time:.2f}s")
        logger.info("=" * 60)
        
    except Exception as e:
        total_time = time.time() - start_time
        logger.error(f"❌ ERROR en generación de PDF: {str(e)}")
        logger.error(f"⏱️ Tiempo transcurrido: {total_time:.2f}s")
        raise

if __name__ == "__main__":
    url, out_pdf = sys.argv[1], sys.argv[2]
    asyncio.run(run(url, out_pdf))