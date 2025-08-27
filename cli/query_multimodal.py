import argparse
import io
from pathlib import Path
from PIL import Image
from app.multimodal_rag.config import get_chroma_collection, get_text_embedder
from app.agent.shared import answer_llm

def display_image_in_console(image_path: Path):
    try:
        img = Image.open(image_path)
        width, height = 80, 30
        img = img.resize((width, height))
        img = img.convert('L')
        
        ascii_chars = "@%#*+=-:. "
        pixels = img.getdata()
        ascii_str = "".join([ascii_chars[pixel * (len(ascii_chars) - 1) // 255] for pixel in pixels])
        
        print(f"--- INICIO IMAGEN: {image_path.name} ---")
        for i in range(0, len(ascii_str), width):
            print(ascii_str[i:i+width])
        print(f"--- FIN IMAGEN ---")

    except Exception as e:
        print(f"[No se pudo mostrar la imagen {image_path.name}: {e}]")

def is_general_query(query: str) -> bool:
    """Detecta si es una pregunta general que requiere información completa."""
    general_patterns = [
        "defectos tiene", "información", "todo", "resumen", 
        "cuéntame", "qué sabe", "evidencia", "completo"
    ]
    return any(pattern in query.lower() for pattern in general_patterns)

def get_expanded_results(collection, query_embedding, where_filter, original_k=15):
    """Para preguntas generales, trae más chunks."""
    return collection.query(
        query_embeddings=[query_embedding],
        n_results=min(30, original_k * 2),  # Duplicar resultados para preguntas generales
        where=where_filter if where_filter else None,
        include=["documents", "metadatas", "distances"]
    )

def main():
    parser = argparse.ArgumentParser(description="Consulta el RAG multimodal desde la consola.")
    parser.add_argument("query", type=str, help="La pregunta que quieres hacer.")
    parser.add_argument("-k", type=int, default=15, help="Número de chunks a recuperar.")
    parser.add_argument("--responsable", type=str, default=None, help="Filtra la búsqueda por un responsable específico.")
    parser.add_argument("--defecto", type=str, default=None, help="Filtra la búsqueda por un defecto específico.")
    args = parser.parse_args()

    print(f"Buscando respuesta para: '{args.query}'")

    where_filter = {}
    if args.responsable:
        where_filter["responsable"] = args.responsable
        print(f"Aplicando filtro por RESPONSABLE: {args.responsable}")
    if args.defecto:
        where_filter["defecto"] = args.defecto
        print(f"Aplicando filtro por DEFECTO: {args.defecto}")
    
    print("")

    collection = get_chroma_collection()
    embedder = get_text_embedder()

    print("1. Generando embedding para la pregunta...")
    query_embedding = embedder.embed([args.query])[0]

    print(f"2. Buscando {args.k} chunks relevantes en ChromaDB...")
    
    # 🔍 DEBUG SIMPLE: Ver QUÉ tablas hay en ChromaDB
    print("\n🔍 AUDITANDO TABLAS EN CHROMADB...")
    all_tables = collection.get(
        where={"element_type": "table"}, 
        include=["documents", "metadatas"]
    )
    
    if all_tables and all_tables.get("documents"):
        docs = all_tables.get("documents", [])
        metas = all_tables.get("metadatas", [])
        
        print(f"📊 TOTAL TABLAS EN CHROMADB: {len(docs)}")
        for i, (doc, meta) in enumerate(zip(docs, metas)):
            file_name = meta.get("source_file", "N/A")
            # Buscar específicamente la tabla de aprobación
            has_approval = "juan carlos" in str(doc).lower() or "mejía" in str(doc).lower()
            marker = "🎯 ¡APROBACIÓN!" if has_approval else "📄"
            preview = str(doc)[:80].replace('\n', ' ')
            print(f"  {marker} Tabla {i+1}: {preview}...")
    
    print("\n" + "="*50)

    if is_general_query(args.query):
        print("🔍 PREGUNTA GENERAL detectada - buscando información completa...")
        results = get_expanded_results(collection, query_embedding, where_filter, args.k)
    else:
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=args.k,
            where=where_filter if where_filter else None,
            include=["documents", "metadatas", "distances"]
        )

    if not results or not results.get("ids", [[]])[0]:
        print("\nNo se encontraron resultados relevantes con los filtros aplicados.")
        return

    # 🔧 FIX: Construir contexto desde LO VECTORIZADO (documents) no desde archivos del disco
    metadatas = results.get("metadatas", [[]])[0]
    docs = results.get("documents", [[]])[0]  # ✅ ESTO es lo que se vectorizó
    distances = results.get("distances", [[]])[0]

    # 🎯 RE-RANKING INTELIGENTE para mejorar precisión
    query_lower = args.query.lower()
    keywords = ["aprob", "aprobó", "aprobación", "fecha", "versión", "rol", "nombre", "firma"]
    
    def calculate_relevance_score(text: str, metadata: dict) -> float:
        text_lower = (text or "").lower()
        
        # Puntuación base por keywords
        keyword_score = sum(1 for kw in keywords if kw in text_lower)
        
        # Bonus por estructura de tabla
        table_bonus = 5 if (" | " in text and "\n---" in text) else 0
        
        # Bonus por ser tipo tabla en metadatos
        type_bonus = 2 if metadata.get("element_type") == "table" else 0
        
        return keyword_score + table_bonus + type_bonus
    
    # Reordenar por relevancia mejorada
    scored_items = [
        (i, calculate_relevance_score(docs[i], metadatas[i]), distances[i])
        for i in range(len(docs))
    ]
    
    # Ordenar por: 1) puntuación relevancia, 2) distancia embedding
    scored_items.sort(key=lambda x: (-x[1], x[2]))
    
    # Reordenar las listas
    reordered_indices = [item[0] for item in scored_items]
    docs = [docs[i] for i in reordered_indices]
    metadatas = [metadatas[i] for i in reordered_indices]
    distances = [distances[i] for i in reordered_indices]
    
    print(f"🔄 RE-RANKING aplicado: chunks reordenados por relevancia semántica + léxica")

    print("\n3. Chunks recuperados:")
    context_lines = []
    retrieved_images = []

    for i, meta in enumerate(metadatas):
        element_type = meta.get("element_type", "desconocido")
        source_file = meta.get("source_file", "N/A")
        responsable_meta = meta.get("responsable", "N/A")
        defecto_meta = meta.get("defecto", "N/A")
        doc_text = (docs[i] or "").strip()  # ✅ Texto vectorizado
        distance = distances[i]
        
        print(f"\n--- Chunk {i+1}: Tipo={element_type.upper()}, Archivo={source_file} ---")
        print(f"    Responsable: {responsable_meta}")
        print(f"    Defecto: {defecto_meta}")
        print(f"    Distancia (menor = mejor): {distance:.4f}")
        print(f"    VECTOR_TEXT (preview 300): {doc_text[:300].replace(chr(10), ' ')}...")

        # ✅ CLAVE: Usar el texto vectorizado para el contexto del LLM
        section_header = f"[{element_type.upper()}] {source_file} - Responsable: {responsable_meta} - Defecto: {defecto_meta}"
        context_lines.append(f"{section_header}\n{doc_text}")

        # Para imágenes, mostrar preview si existe el archivo
        if element_type == "image":
            source_path = Path(meta.get("source_path", ""))
            if source_path.exists():
                retrieved_images.append(source_path)

    # Construir contexto final con LO VECTORIZADO
    context_text = "\n\n".join(context_lines)

    print("\n" + "="*50)
    print("4. Generando respuesta con el LLM (Cerebras Llama-3)...")
    
    if retrieved_images:
        print("\nImágenes recuperadas (se mostrará una previsualización en texto):")
        for img_path in retrieved_images:
            display_image_in_console(img_path)

    # ✅ PROMPT mejorado con el contexto vectorizado correcto
    if is_general_query(args.query):
        prompt = (
            "Eres un asistente especializado en organizar evidencias técnicas de forma estructurada. "
            "El usuario te pide información completa sobre un responsable o defecto. "
            "Organiza TODA la información disponible de forma clara y estructurada.\n\n"
            
            "INSTRUCCIONES:\n"
            "1. Agrupa la información por secciones lógicas (Control de plantilla, Control de documento, Datos del proyecto, etc.)\n"
            "2. Presenta las tablas en formato legible\n"
            "3. Incluye TODOS los detalles disponibles\n"
            "4. Conecta nombres parciales con nombres completos en metadatos\n\n"
            
            "--- INICIO DEL CONTEXTO COMPLETO ---\n"
            f"{context_text}\n"
            "--- FIN DEL CONTEXTO COMPLETO ---\n\n"
            
            f"Pregunta del usuario: {args.query}\n\n"
            "Organiza y presenta TODA la información disponible de forma estructurada:"
        )
    else:
        prompt = (
            "Eres un asistente de QA especializado en evidencias técnicas. "
            "Responde la pregunta específica del usuario basándote en el contexto.\n\n"
            "--- CONTEXTO ---\n"
            f"{context_text}\n"
            "--- FIN CONTEXTO ---\n\n"
            f"Pregunta: {args.query}\n\nRespuesta:"
        )

    response = answer_llm.invoke(prompt)

    print("\n" + "="*50)
    print("✅ RESPUESTA FINAL:\n")
    print(response.content)
    print("\n" + "="*50)


if __name__ == "__main__":
    main()