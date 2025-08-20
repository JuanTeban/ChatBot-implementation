import sys
import asyncio
from pathlib import Path

# Añadir el proyecto al path
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

from app.etl.multimodal_ingestor import process_pdf_document

async def test_pdf_processing():
    """Prueba el procesamiento de PDFs con análisis detallado."""
    pdf_path = project_root / "data_store" / "uploads"
    
    # Buscar archivos PDF
    pdf_files = list(pdf_path.glob("*.pdf"))
    
    if not pdf_files:
        print("❌ No se encontraron archivos PDF en data_store/uploads/")
        return
    
    for pdf_file in pdf_files:
        print(f"\n📄 Analizando: {pdf_file.name}")
        print("=" * 50)
        
        result = await process_pdf_document(pdf_file)
        
        print(f"✅ Éxito: {result['success']}")
        print(f"📊 Elementos procesados: {result['elements_processed']}")
        
        # Análisis por tipo
        type_counts = {}
        for doc in result["documents"]:
            doc_type = doc["doc_type"]
            type_counts[doc_type] = type_counts.get(doc_type, 0) + 1
        
        print("\n📋 Tipos de elementos:")
        for doc_type, count in type_counts.items():
            print(f"  {doc_type}: {count}")
        
        # Mostrar estrategias intentadas
        if "strategies_tried" in result:
            print("\n🔍 Estrategias probadas:")
            for strategy_info in result["strategies_tried"]:
                strategy = strategy_info["strategy"]
                analysis = strategy_info["analysis"]
                print(f"  {strategy}: {analysis}")
        
        # Mostrar errores si los hay
        if result["errors"]:
            print(f"\n❌ Errores: {len(result['errors'])}")
            for error in result["errors"]:
                print(f"  - {error}")
        
        print()

if __name__ == "__main__":
    asyncio.run(test_pdf_processing())