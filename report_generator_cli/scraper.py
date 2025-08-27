# scraper.py
import os
import re
import time
import json
import requests
from datetime import date
import unicodedata
from urllib.parse import unquote

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from config import DEBUGGER_ADDRESS, DOWNLOAD_FOLDER, DEBUG_MODE
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException
from selenium.common.exceptions import NoSuchElementException, JavascriptException
from selenium.common.exceptions import (
    ElementClickInterceptedException, ElementNotInteractableException
)
from config import DEBUGGER_ADDRESS


# ---------------------------
# Conexión y sesión requests
# ---------------------------

def connect_to_browser():
    """Se conecta a un Chrome YA ABIERTO con --remote-debugging-port (sesión autenticada)."""
    opts = Options()
    opts.add_experimental_option("debuggerAddress", DEBUGGER_ADDRESS)
    driver = webdriver.Chrome(options=opts)
    print("✅ Conectado exitosamente al navegador existente.")
    return driver


def create_requests_session(driver):
    """
    Crea una sesión requests reutilizando cookies y User-Agent del navegador.
    En redes corporativas con TLS interno, puedes ajustar verify=False.
    """
    s = requests.Session()
    s.verify = False  # cambia a True o ruta a tu CA corporativa en prod

    # Copiar User-Agent
    try:
        ua = driver.execute_script("return navigator.userAgent")
        if ua:
            s.headers.update({"User-Agent": ua})
    except Exception:
        pass

    # Copiar cookies del navegador
    for c in driver.get_cookies():
        try:
            s.cookies.set(c["name"], c["value"], domain=c.get("domain"))
        except Exception:
            # En caso de dominio None, set sin dominio
            s.cookies.set(c["name"], c["value"])
    print("✅ Sesión de 'requests' creada con las cookies del navegador.")
    return s


# ---------------------------
# Utilidades UI5 / FLP
# ---------------------------

def _ui5_ok(driver) -> bool:
    """Verifica si la API de UI5 está accesible en el contexto actual."""
    try:
        return bool(driver.execute_script("return !!(window.sap && sap.ui && sap.ui.getCore);"))
    except JavascriptException:
        return False


def switch_to_app_iframe(driver):
    """
    En SAP Fiori Launchpad las apps suelen ir embebidas en un iframe.
    Este helper entra al iframe que contiene UI5 y la tabla de defectos.
    """
    driver.switch_to.default_content()
    frames = driver.find_elements(By.TAG_NAME, "iframe")
    for idx, fr in enumerate(frames):
        try:
            driver.switch_to.frame(fr)
            if not _ui5_ok(driver):
                driver.switch_to.default_content()
                continue
            has_table = driver.execute_script("""
                return !!document.querySelector(
                  "[id$='--analyticalTable'],[id$='--table'],[id$='--analyticalTable-vsb']"
                );
            """)
            if has_table:
                print(f"   -> Entré al iframe #{idx} (contiene UI5 + tabla).")
                return True
        except Exception:
            pass
        finally:
            # Si no era este, volvemos a raíz para probar el siguiente
            driver.switch_to.default_content()

    # Si no encontramos nada, probamos raíz
    driver.switch_to.default_content()
    if _ui5_ok(driver):
        print("   -> La app NO parece usar iframe (UI5 presente en raíz).")
        return True

    print("   -> ⚠️ No encontré un iframe con UI5; continuaré en raíz (podría fallar).")
    return False


def ui5_table_info(driver):
    """
    Devuelve información de la tabla UI5:
    - tableId
    - tipo de control (metadata name)
    - total de filas (binding rows/items)
    - número de filas visibles por ventana
    - flags hasRows/hasItems
    """
    if not _ui5_ok(driver):
        return None

    table_id = driver.execute_script("""
        var cand = document.querySelector("[id$='--analyticalTable']")
               || document.querySelector("[id$='--table']");
        return cand ? cand.id : null;
    """)
    if not table_id:
        return None

    info = driver.execute_script("""
        var id = arguments[0];
        var t = sap.ui.getCore().byId(id);
        if (!t) return null;
        var meta = t.getMetadata().getName();
        var rowsBind = t.getBinding && t.getBinding("rows");
        var itemsBind = t.getBinding && t.getBinding("items");
        var total = -1;
        if (rowsBind && rowsBind.getLength) total = rowsBind.getLength();
        else if (itemsBind && itemsBind.getLength) total = itemsBind.getLength();
        var vis = t.getVisibleRowCount ? t.getVisibleRowCount() : 20;
        return {tableId:id, meta:meta, total: total, visible: vis, hasRows: !!rowsBind, hasItems: !!itemsBind};
    """, table_id)
    return info


# ---------------------------
# Recolección de defectos
# ---------------------------

def _safe_slug(txt: str, max_len: int = 64) -> str:
    """
    Slug seguro para nombres de carpetas/archivos en Windows.
    - Limpia caracteres inválidos
    - Convierte espacios en _
    - Recorta a max_len y quita puntos/espacios finales
    """
    txt = (txt or "").strip()
    txt = txt.replace("\\", "_").replace("/", "_")
    txt = re.sub(r'[<>:"|?*]+', "_", txt)
    txt = re.sub(r"\s+", "_", txt)
    txt = txt[:max_len].rstrip(" ._")
    return txt or "SIN_NOMBRE"


def get_defect_links(driver):
    """
    Recorre la tabla UI5 fila a fila y devuelve:
      [{ 'text': <defecto>, 'url': <link>, 'responsable': <responsable> }, ...]
    """
    print("🔎 Buscando la lista de defectos agrupando por Responsable…")
    wait = WebDriverWait(driver, 30)

    # 0) Contexto correcto + que exista al menos un link
    switch_to_app_iframe(driver)
    link_sel = (By.XPATH, "//a[contains(@class,'sapMLnk') and contains(@href,'Action-genericApp')]")
    wait.until(EC.presence_of_element_located(link_sel))

    # 1) Info de la tabla
    info = ui5_table_info(driver)
    if not info or not isinstance(info.get("total"), (int, float)) or info["total"] <= 0:
        print("   -> ⚠️ No hay info confiable; uso fallback con rueda.")
        return _fallback_wheel_collect(driver)

    table_id = info["tableId"]
    total = int(info["total"])
    print(f"   -> Tabla: {info['meta']}  total={total} visibles={info['visible']}")

    seen, collected = set(), []

    def harvest_visible_using_headers():
        # Lee el “responsable” usando el atributo headers de cada <td> en la MISMA fila del enlace
        return driver.execute_script("""
            function norm(s){return (s||'').replace(/\\s+/g,' ').trim();}
            function lower(s){return norm(s).toLowerCase();}
            var root = document.querySelector('div.sapUiTableCnt');
            if (!root) return [];
            var out = [];

            var links = Array.from(root.querySelectorAll("a.sapMLnk[href*='Action-genericApp']"));
            links.forEach(function(a){
                var tr = a.closest('tr');
                if (!tr) return;

                var responsable = "";
                // Busca en los <td> hermanos de esa MISMA fila
                var tds = Array.from(tr.querySelectorAll('td'));
                for (var i=0; i<tds.length; i++){
                    var td = tds[i];
                    var hdrId = td.getAttribute('headers');
                    var headerTxt = '';
                    if (hdrId) {
                        var hdrEl = document.getElementById(hdrId);
                        headerTxt = lower(hdrEl ? hdrEl.textContent : '');
                    }
                    if (!headerTxt) {
                        // Fallback: a veces usan aria-labelledby
                        var lb = td.getAttribute('aria-labelledby') || '';
                        lb.split(/\\s+/).forEach(function(id){
                            var el = document.getElementById(id);
                            if (el) headerTxt += ' ' + lower(el.textContent || '');
                        });
                        headerTxt = lower(headerTxt);
                    }
                    if (headerTxt.includes('responsable')) {
                        responsable = norm(td.innerText || td.textContent);
                        break;
                    }
                }

                out.push({
                    text: norm(a.textContent || ''),
                    url: a.href || '',
                    responsable: responsable || 'SIN_RESPONSABLE'
                });
            });

            // de-duplicar por url
            var seen = new Set(), dedup = [];
            out.forEach(function(it){
                if (it.url && !seen.has(it.url)) { dedup.push(it); seen.add(it.url); }
            });
            return dedup;
        """) or []

    # 2) Recorremos la tabla moviendo la primera fila visible
    last_size = 0
    for i in range(total):
        driver.execute_script("""
            var t = sap.ui.getCore().byId(arguments[0]);
            if (t && t.setFirstVisibleRow) { t.setFirstVisibleRow(arguments[1]); }
        """, table_id, i)
        time.sleep(0.18)

        for it in harvest_visible_using_headers():
            if it["url"] in seen:
                continue
            collected.append(it); seen.add(it["url"])

        if (i + 1) % 10 == 0 or i == total - 1:
            if len(collected) != last_size:
                print(f"   -> Progreso: {i+1}/{total} (acumulados: {len(collected)})")
                last_size = len(collected)

    print(f"   -> ✅ Recopilados {len(collected)} defectos (con responsable).")
    if not collected:
        print("   -> ⚠️ Nada recolectado; intento fallback con rueda.")
        return _fallback_wheel_collect(driver)

    return collected



def _fallback_wheel_collect(driver):
    """
    Fallback: fuerza desplazamiento con 'wheel' sobre el contenedor de filas de sap.ui.table.Table,
    cosechando en vivo (texto+href+responsable) SIN depender del índice de la columna.
    """
    print("   -> Fallback: desplazamiento con rueda sobre el contenedor de filas…")
    wait = WebDriverWait(driver, 20)
    link_sel = (By.XPATH, "//a[contains(@class,'sapMLnk') and contains(@href,'Action-genericApp')]")
    wait.until(EC.presence_of_element_located(link_sel))

    # contenedor real que scrollea las filas
    try:
        scroll_area = driver.find_element(By.CSS_SELECTOR, "div.sapUiTableCtrlScr")
    except NoSuchElementException:
        # Ancestro de la tabla como último recurso
        first_link = driver.find_element(*link_sel)
        scroll_area = first_link.find_element(By.XPATH, "./ancestor::*[contains(@class,'sapUiTableCnt') or contains(@class,'sapUiTable')]")

    seen, collected = set(), []

    def harvest_once():
        added = 0
        # Hacemos todo con JS para, además del link, leer el “responsable” por fila
        rows = driver.execute_script("""
            function norm(s){return (s||'').replace(/\\s+/g,' ').trim();}
            function lower(s){return norm(s).toLowerCase();}
            var root = document.querySelector('div.sapUiTableCnt');
            if (!root) return [];
            var out = [];

            var links = Array.from(root.querySelectorAll("a.sapMLnk[href*='Action-genericApp']"));
            links.forEach(function(a){
                var tr = a.closest('tr');
                if (!tr) return;

                var responsable = "";
                var tds = Array.from(tr.querySelectorAll('td'));
                for (var i=0; i<tds.length; i++){
                    var td = tds[i];
                    var hdrId = td.getAttribute('headers');
                    var headerTxt = '';
                    if (hdrId) {
                        var hdrEl = document.getElementById(hdrId);
                        headerTxt = lower(hdrEl ? hdrEl.textContent : '');
                    }
                    if (!headerTxt) {
                        var lb = td.getAttribute('aria-labelledby') || '';
                        lb.split(/\\s+/).forEach(function(id){
                            var el = document.getElementById(id);
                            if (el) headerTxt += ' ' + lower(el.textContent || '');
                        });
                        headerTxt = lower(headerTxt);
                    }
                    if (headerTxt.includes('responsable')) {
                        responsable = norm(td.innerText || td.textContent);
                        break;
                    }
                }

                out.push({
                    text: norm(a.textContent || ''),
                    url: a.href || '',
                    responsable: responsable || 'SIN_RESPONSABLE'
                });
            });
            return out;
        """) or []

        for it in rows:
            href = it.get("url") or ""
            if "Action-genericApp" not in href or href in seen:
                continue
            text = (it.get("text") or "").strip()
            if not text:
                continue
            it["responsable"] = it.get("responsable") or "SIN_RESPONSABLE"
            collected.append(it)
            seen.add(href)
            added += 1
        return added

    harvest_once()
    stagnant = 0
    for _ in range(500):
        # 'wheel' dispara mejor el virtual scroll de UI5
        driver.execute_script("""
            const el = arguments[0];
            const evt = new WheelEvent('wheel', {deltaY: el.clientHeight});
            el.dispatchEvent(evt);
        """, scroll_area)
        time.sleep(0.2)
        if harvest_once() == 0:
            stagnant += 1
            if stagnant >= 8:
                break
        else:
            stagnant = 0

    print(f"   -> Fallback reunió {len(collected)} enlaces.")
    return collected

# ---------------------------
# Descarga de anexos
# ---------------------------

_WIN_RESERVED = {"CON","PRN","AUX","NUL",
                 "COM1","COM2","COM3","COM4","COM5","COM6","COM7","COM8","COM9",
                 "LPT1","LPT2","LPT3","LPT4","LPT5","LPT6","LPT7","LPT8","LPT9"}

def _sanitize_filename_win(name: str) -> str:
    s = (name or "").strip()
    s = s.replace("\\", "_").replace("/", "_")
    s = re.sub(r'[<>:"|?*]+', "_", s)
    s = re.sub(r"\s+", "_", s)
    base, ext = os.path.splitext(s or "archivo")
    if base.upper() in _WIN_RESERVED:
        base += "_"
    s = base + ext
    return s or "archivo.bin"


def download_file_with_requests(session, url, dir_path, fallback_name):
    dir_path = os.path.abspath(dir_path)
    os.makedirs(dir_path, exist_ok=True)
    try:
        with session.get(url, stream=True, timeout=90) as r:
            r.raise_for_status()
            cd = r.headers.get("Content-Disposition") or r.headers.get("content-disposition", "")
            m = re.search(r'filename\*?=(?:UTF-8\'\')?["\']?([^"\';]+)', cd or "", re.I)

            raw_name = m.group(1) if m else (fallback_name or "archivo.bin")
            raw_name = unquote(raw_name)
            raw_name = unicodedata.normalize("NFC", raw_name)
            
            fname = _sanitize_filename_win(raw_name)
            if "." not in os.path.basename(fname):
                fname += ".bin"

            fpath = os.path.join(dir_path, fname)
            
            counter = 1
            original_base, original_ext = os.path.splitext(fname)
            while os.path.exists(fpath):
                new_name = f"{original_base}({counter}){original_ext}"
                fpath = os.path.join(dir_path, new_name)
                counter += 1
            
            fname = os.path.basename(fpath)
            
            final_fpath = os.path.abspath(fpath)
            if os.name == 'nt' and len(final_fpath) > 255 and not final_fpath.startswith('\\\\?\\'):
                final_fpath = '\\\\?\\' + final_fpath

            print(f"      - [DL] {fname}")

            with open(final_fpath, "wb") as f:
                for chunk in r.iter_content(1 << 15):
                    if chunk:
                        f.write(chunk)
            print(f"      - ✅ Descargado: '{fname}'")
            return fpath
            
    except requests.RequestException as e:
        print(f"      - ❌ Error HTTP al descargar {url}: {e}")
        return None


def save_debug_screenshot(driver, name):
    if not DEBUG_MODE:
        return
    try:
        # Crea una carpeta 'debug' si no existe
        debug_folder = os.path.join(os.path.dirname(__file__), "debug")
        os.makedirs(debug_folder, exist_ok=True)
        
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        filepath = os.path.join(debug_folder, f"{name}_{timestamp}.png")
        
        driver.save_screenshot(filepath)
        print(f"   -> 📸 [DEBUG] Captura de pantalla guardada en: {filepath}")
    except Exception as e:
        print(f"   -> ⚠️ [DEBUG] No se pudo guardar la captura de pantalla: {e}")


def wait_ui5_global_idle(driver, timeout=90, stable_ms=600, poll=0.25, debug=False):
    """
    Espera a que NO haya busy indicators globales en la página (UI5).
    Además exige una ventana estable 'sin busy' de stable_ms.
    """
    deadline = time.time() + timeout
    last_clear = None
    while time.time() < deadline:
        try:
            busy_count = driver.execute_script("""
                var nodes = document.querySelectorAll('.sapUiLocalBusyIndicator');
                // visibles:
                var visible = 0;
                nodes.forEach(function(n){
                    var s = window.getComputedStyle(n);
                    if (s && s.display !== 'none' && s.visibility !== 'hidden' && s.opacity !== '0') visible++;
                });
                return visible;
            """) or 0
        except Exception:
            busy_count = 0

        if busy_count == 0:
            if last_clear is None:
                last_clear = time.time()
            if (time.time() - last_clear) * 1000 >= stable_ms:
                if debug:
                    print("   -> [DEBUG] UI5 global idle.")
                return True
        else:
            last_clear = None
        time.sleep(poll)
    if debug:
        print("   -> [DEBUG] UI5 global idle: timeout.")
    return False


def _js_links_from(driver, container_id):
    return driver.execute_script("""
        function map(ns){return Array.from(ns).map(a=>({
            href:a.href||"",
            text:(a.textContent||"").trim(),
            title:a.getAttribute('title')||"",
            id:a.id||""
        }));}
        var sel = "a.sapMLnk[href*='/documentContent'][href*='$value'], a[title^='Hacer clic para descargar fichero']";
        var root = container_id ? document.getElementById(container_id) : null;
        var out = root ? map(root.querySelectorAll(sel)) : [];
        if (!out.length) { out = map(document.querySelectorAll(sel)); }
        return out;
    """, container_id) or []

def _selenium_links_fallback(driver):
    els = driver.find_elements(
        By.CSS_SELECTOR,
        "a.sapMLnk[href*='/documentContent'][href*='$value'], a[title^='Hacer clic para descargar fichero']"
    )
    out = []
    for a in els:
        href = a.get_attribute("href") or ""
        if not href: 
            continue
        out.append({
            "href": href,
            "text": (a.text or "").strip(),
            "title": a.get_attribute("title") or "",
            "id": a.get_attribute("id") or ""
        })
    return out

def _try_get_links(driver, container_id, debug=False, retries=3):
    for i in range(retries):
        try:
            return _js_links_from(driver, container_id)
        except JavascriptException as e:
            if debug:
                print(f"   -> [DEBUG] JS exception leyendo enlaces (intento {i+1}); reintento…")
            wait_ui5_global_idle(driver, timeout=20, debug=debug)
            time.sleep(0.5)
    if debug:
        print("   -> [DEBUG] Fallback Selenium para enlaces (sin JS).")
    return _selenium_links_fallback(driver)


def select_anexos_tab(driver, wait, debug=False):
    """
    Selecciona la pestaña 'Anexos'. Si ya está seleccionada, la usa.
    Reintenta si hay busy/overlay bloqueando el clic.
    """
    XPATH = ("//div[@role='tab' and (normalize-space(@title)='Anexos' "
             " or .//div[contains(@class,'sapMITBText') and normalize-space(.)='Anexos'])]")

    def is_selected(tab_el):
        try:
            sel = tab_el.get_attribute("aria-selected")
            cls = tab_el.get_attribute("class") or ""
            return sel == "true" or "sapMITBSelected" in cls
        except Exception:
            return False

    # localizar
    tab = wait.until(EC.presence_of_element_located((By.XPATH, XPATH)))
    content_id = tab.get_attribute("aria-controls") or "__xmlview3--idIconTabBarMulti-content"

    # si ya está seleccionada, listo
    if is_selected(tab):
        if debug:
            print("   -> [DEBUG] 'Anexos' ya estaba seleccionado.")
        return content_id

    # reintentos con espera global
    for attempt in range(1, 11):
        try:
            # evita overlays
            wait_ui5_global_idle(driver, timeout=20, debug=debug)

            # traer al centro y clicar
            target = None
            try:
                target = tab.find_element(By.CSS_SELECTOR, ".sapMITBTab")
            except Exception:
                target = tab

            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", target)
            try:
                ActionChains(driver).move_to_element(target).pause(0.05).click().perform()
            except (ElementClickInterceptedException, ElementNotInteractableException):
                driver.execute_script("arguments[0].click();", target)

            # verificar seleccionado
            WebDriverWait(driver, 10).until(lambda d: is_selected(tab))
            # y esperar que termine el busy después del cambio
            wait_ui5_global_idle(driver, timeout=30, debug=debug)
            return content_id

        except StaleElementReferenceException:
            if debug:
                print(f"   -> [DEBUG] STALE al clicar 'Anexos' (intento {attempt}); relocalizando…")
            tab = wait.until(EC.presence_of_element_located((By.XPATH, XPATH)))
            content_id = tab.get_attribute("aria-controls") or content_id
        except TimeoutException:
            if debug:
                print(f"   -> [DEBUG] 'Anexos' no quedó seleccionado (intento {attempt}); reintento…")
        time.sleep(0.4)

    # plan B: no pudimos “verificar” selección; devolvemos content_id y que arriba se intente leer enlaces globalmente
    if debug:
        print("   -> [DEBUG] Fallback: no pude confirmar selección; uso content_id y seguiré.")
    return content_id



def process_defect_attachments(driver, session, defect_info, base_folder):
    main_window = driver.current_window_handle
    driver.switch_to.new_window('tab')

    print(f"📂 Procesando defecto: {defect_info['text']}")
    print("   -> Abriendo URL del defecto. Esperando a que la página cargue...")

    try:
        driver.set_page_load_timeout(90)
        driver.get(defect_info["url"])
    except TimeoutException:
        print("   -> ❌ Timeout: La página del defecto tardó más de 90 segundos en cargar.")
        save_debug_screenshot(driver, "error_carga_inicial")
        return
    finally:
        driver.set_page_load_timeout(35)

    wait = WebDriverWait(driver, 60)

    try:
        wait.until(EC.visibility_of_element_located((
            By.XPATH, "//div[@role='tab' and contains(., 'Detalles')]"
        )))
        wait_ui5_global_idle(driver, timeout=45, debug=DEBUG_MODE)
        print("   -> ✅ Página del defecto cargada.")

        try:
            switch_to_app_iframe(driver)
        except Exception:
            pass

        print("   -> Abriendo pestaña 'Anexos' de forma robusta…")
        content_id = select_anexos_tab(driver, wait, debug=DEBUG_MODE)
        
        wait_ui5_global_idle(driver, timeout=60, debug=DEBUG_MODE)

        print("   -> Esperando a que la tabla de anexos sea poblada con filas...")
        try:
            tabla_selector = (By.XPATH, f"//tbody[contains(@id, 'CustomColumnsTable-tblBody')]/tr")
            WebDriverWait(driver, 45).until(
                EC.presence_of_element_located(tabla_selector)
            )
            print("   -> ✅ ¡Tabla poblada! Las filas de anexos ahora son visibles.")
        except TimeoutException:
            print("   -> ❌ Timeout: La tabla de anexos nunca se llenó con filas de datos.")
            save_debug_screenshot(driver, "timeout_tabla_vacia")
            return
            
        def get_links_multifrequency(container_id):
            return driver.execute_script("""
                const containerId = arguments[0];
                const root = containerId ? document.getElementById(containerId) : document;
                const selectors = [
                    "a.sapMLnk[href*='/documentContent'][href*='$value']",
                    "a[title^='Hacer clic para descargar fichero']",
                    "a[href*='vhp-downloaddocument-']",
                    "a.sapMListTblCell[href*='/documentContent']",
                    "a[href*='/documentContent']"
                ];
                let links = [];
                for (const selector of selectors) {
                    const found = Array.from(root.querySelectorAll(selector));
                    if (found.length) {
                        links = found;
                        break;
                    }
                }
                return links.map(a => ({
                    href: a.href || "", text: (a.textContent || "").trim(),
                    title: a.getAttribute('title') || "", id: a.id || ""
                }));
            """, container_id) or []
        
        links_info = get_links_multifrequency(content_id)

        if not links_info:
            print("   -> ⚠️ Se encontraron filas pero no se pudo extraer ningún enlace (muy raro).")
            save_debug_screenshot(driver, "error_extraccion_links_raro")
            return

        print(f"   -> ✅ ¡Éxito! Se encontraron {len(links_info)} enlaces de anexos.")

        m = re.search(r'^(.*)\s\((\d+)\)\s*$', defect_info["text"])
        title = (m.group(1) if m else defect_info["text"]).strip()
        defect_id = (m.group(2) if m else "SIN_ID").strip()

        responsable = (defect_info.get("responsable") or "SIN_RESPONSABLE").strip()
        responsable_dir = _safe_slug(responsable, 48)
        defect_dirname = f"{defect_id}-{_safe_slug(title, 64)}"

        defect_dir = os.path.join(
            base_folder, responsable_dir, defect_dirname, date.today().isoformat()
        )
        os.makedirs(defect_dir, exist_ok=True)
        print(f"   -> Descargando en: {defect_dir} (len={len(os.path.abspath(defect_dir))})")

        meta = {"defect": defect_info["text"], "url": defect_info["url"], "attachments": []}
        print(f"   -> Descargando {len(links_info)} anexos…")
        for li in links_info:
            href = li.get("href") or ""
            title_attr = li.get("title") or ""
            text_attr = li.get("text") or ""
            m_title = re.search(r'Hacer clic para descargar fichero:\s*(.+)$', title_attr)
            suggested_name = m_title.group(1).strip() if m_title else (text_attr.strip() or "archivo.bin")
            saved_path = download_file_with_requests(session, href, defect_dir, suggested_name)
            if saved_path:
                meta["attachments"].append({"title": suggested_name, "href": href, "path": saved_path})

        meta_path = os.path.join(defect_dir, "metadata.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        print(f"   -> 📝 Metadata guardada en '{meta_path}'")

    except Exception as e:
        print(f"   -> ❌ Error inesperado procesando defecto: {repr(e)}")
        save_debug_screenshot(driver, "error_inesperado_defecto")
    finally:
        if DEBUG_MODE:
            print("   -> DEBUG_MODE=True: dejo la pestaña abierta para inspección.")
            return
        try:
            print("   -> Finalizando procesamiento, cerrando pestaña...")
            driver.close()
            driver.switch_to.window(main_window)
        except Exception:
            pass