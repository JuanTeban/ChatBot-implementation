import sqlite3

EXCEL_FILENAME = "Seguimiento-hallazgos-Solman.xlsx"
# Usaremos el filename como ID único en este caso para la lógica de chequeo
EXCEL_TYPE = 'excel'
DB_PATH = 'rag_app.db'
TABLE_NAME = 'document_store'

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

try:
    # Primero, verifica si ya existe un registro con ese nombre de archivo y tipo
    cursor.execute(f"SELECT filename FROM {TABLE_NAME} WHERE filename = ? AND type = ?", (EXCEL_FILENAME, EXCEL_TYPE))
    if cursor.fetchone():
        print(f"El archivo Excel '{EXCEL_FILENAME}' ya está registrado.")
    else:
        # Inserta el registro del archivo Excel con el tipo 'excel'
        cursor.execute(
            f"INSERT INTO {TABLE_NAME} (filename, type) VALUES (?, ?)",
            (EXCEL_FILENAME, EXCEL_TYPE)
        )
        conn.commit()
        print(f"✅ Archivo Excel '{EXCEL_FILENAME}' registrado exitosamente.")

except sqlite3.Error as e:
    print(f"Ocurrió un error: {e}")
finally:
    conn.close()