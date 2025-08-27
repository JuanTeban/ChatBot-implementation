import sys
from scraper import (
    connect_to_browser, 
    create_requests_session, 
    get_defect_links, 
    process_defect_attachments
)
from config import DOWNLOAD_FOLDER
from collections import defaultdict

def select_defects_to_process(all_defects):
    if not all_defects:
        print("No se encontraron defectos para procesar.")
        return []

    print("\n--- SELECCIÓN DE DEFECTOS ---")
    print("Se encontraron los siguientes defectos:")
    for i, defect in enumerate(all_defects, 1):
        print(f"  {i}: {defect['text']}")

    while True:
        print("\n¿Cuáles deseas procesar?")
        user_input = input("Ingresa los números separados por comas (ej: 1,3,8), 'todos' para procesarlos todos, o deja en blanco para cancelar: ")
        
        choice = user_input.strip().lower()

        if not choice:
            print("Proceso cancelado por el usuario.")
            return []
        
        if choice == 'todos':
            return all_defects

        try:
            selected_indices = [int(num.strip()) - 1 for num in choice.split(',')]
            
            selected_defects = []
            valid_selection = True
            for index in selected_indices:
                if 0 <= index < len(all_defects):
                    selected_defects.append(all_defects[index])
                else:
                    print(f"❌ El número {index + 1} está fuera de rango. Inténtalo de nuevo.")
                    valid_selection = False
                    break
            
            if valid_selection:
                return selected_defects

        except ValueError:
            print("❌ Entrada inválida. Asegúrate de ingresar solo números separados por comas.")


# --- NUEVO: selección por RESPONSABLE ---
def select_responsables_to_process(all_defects):
    """
    Recibe [{text,url,responsable}, ...]
    Muestra responsables y permite elegir 1..N.
    Devuelve la lista de defectos de los responsables elegidos.
    """
    if not all_defects:
        print("No se encontraron defectos para procesar.")
        return []

    # Agrupar
    buckets = defaultdict(list)
    for it in all_defects:
        buckets[it.get("responsable") or "SIN_RESPONSABLE"].append(it)

    responsables = sorted(buckets.keys(), key=lambda k: (k == "SIN_RESPONSABLE", k.lower()))
    print("\n--- SELECCIÓN POR RESPONSABLE ---")
    for i, r in enumerate(responsables, 1):
        print(f"  {i}: {r}  ({len(buckets[r])} defectos)")

    while True:
        choice = input("\n¿De cuáles responsables descargar? (ej: 1,3)  'todos' para todos, Enter para cancelar: ").strip().lower()
        if not choice:
            print("Proceso cancelado por el usuario.")
            return []
        if choice == "todos":
            # aplanar en el orden mostrado
            out = []
            for r in responsables:
                out.extend(buckets[r])
            return out
        try:
            idxs = [int(x.strip())-1 for x in choice.split(",")]
            out = []
            for idx in idxs:
                if 0 <= idx < len(responsables):
                    out.extend(buckets[responsables[idx]])
                else:
                    raise ValueError()
            return out
        except Exception:
            print("❌ Entrada inválida. Intenta de nuevo.")

def run_scraper():
    driver = None
    try:
        driver = connect_to_browser()
        session = create_requests_session(driver)
        
        all_defect_links = get_defect_links(driver)
        
        defects_to_process = select_responsables_to_process(all_defect_links)
        
        if not defects_to_process:
            print("No hay defectos seleccionados para procesar. Finalizando.")
            return
            
        print(f"\n✅ Se procesarán {len(defects_to_process)} defectos seleccionados.")
        for i, defect in enumerate(defects_to_process, 1):
            print(f"\n--- Procesando {i}/{len(defects_to_process)} ---")
            process_defect_attachments(driver, session, defect, DOWNLOAD_FOLDER)
        
        print("\n🎉 Proceso completado exitosamente.")

    except Exception as e:
        print(f"❌ Ocurrió un error general en el proceso: {e}")
    finally:
        if driver:
            print("👋 El bot ha terminado. El navegador principal se mantendrá abierto.")

if __name__ == "__main__":
    run_scraper()