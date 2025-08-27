# 📋 Business Rules for Report Generation

## 🎯 Descripción

Este directorio almacena PDFs con **reglas de negocio** que enriquecen la generación de reportes automáticos. Los documentos aquí se procesan mediante RAG para proporcionar contexto específico a las secciones de **resumen ejecutivo** y **recomendaciones**.

## 📁 Estructura

```
data_store/business_rules/
├── README.md                    # Esta documentación
├── summary_rules.pdf           # Reglas para resúmenes ejecutivos
├── recommendations_rules.pdf   # Reglas para planes de acción
└── [otros PDFs]               # Reglas adicionales por categoría
```

## 🔄 Flujo de Procesamiento

### 1. **Subir PDFs**
```bash
# Via Admin UI: /admin
# Sección: "Reglas de Negocio para Reportes"
# Arrastra PDFs o selecciona archivos
```

### 2. **Procesar por Tipo**
- **Reglas de Resumen**: Para enriquecer resúmenes ejecutivos
  - Incluye: KPIs, métricas, definiciones, reglas de calidad
- **Reglas de Recomendaciones**: Para mejorar planes de acción
  - Incluye: Priorización, SLA, procedimientos, escalamiento

### 3. **Vectorización Automática**
- ✅ Extracción de texto inteligente
- ✅ Chunking por secciones naturales
- ✅ Embeddings con Gemini
- ✅ Almacenamiento en ChromaDB collection `business_rules`

## 🎨 Metadatos de Chunking

Cada chunk vectorizado incluye:

```json
{
  "chunk_id": "uuid-único",
  "source_file": "reglas_resumen.pdf", 
  "rule_type": "summary|recommendations",
  "category": "general|kpi|sla|quality",
  "title": "Título de la sección",
  "content_length": 1234,
  "created_at": "2025-08-23T10:30:00Z"
}
```

## 🔍 Búsqueda Inteligente

El sistema detecta automáticamente el tipo de regla según el query:

### **Queries de Resumen** → `rule_type: "summary"`
- "resumen ejecutivo defectos KPI reglas definiciones calidad"
- Palabras clave: `resumen`, `ejecutivo`, `kpi`, `métricas`, `definiciones`, `calidad`

### **Queries de Recomendaciones** → `rule_type: "recommendations"` 
- "priorización plan de acción defectos reglas SLA"
- Palabras clave: `plan`, `acción`, `priorización`, `recomendaciones`, `sla`

## 📊 Integración en Reportes

### **Antes** (sin reglas de negocio):
```
🧠 RECUPERACIÓN RAG - BUSINESS_SNIPPETS
📚 Fuentes encontradas: 0
📖 CONTEXTO RECUPERADO: Se obtuvieron 0 snippets de negocio
```

### **Después** (con reglas procesadas):
```
🧠 RECUPERACIÓN RAG - BUSINESS_SNIPPETS  
Query: resumen ejecutivo defectos KPI reglas definiciones calidad
📚 Fuentes encontradas: 5
📖 CONTEXTO RECUPERADO: Tipo detectado: summary, Snippets: 5, 
Fuentes: [reglas_kpi.pdf, definiciones_calidad.pdf]
```

## 🛠️ Comandos de Gestión

### Via Admin UI (`/admin`):
- ✅ **Subir PDFs**: Drag & drop o selección múltiple
- ✅ **Procesar por Tipo**: Botones separados para resumen/recomendaciones  
- ✅ **Ver Estadísticas**: Distribución por tipo y categoría
- ✅ **Limpiar Colección**: Reset completo si necesario

### Via API directa:
```bash
# Subir PDFs
curl -X POST "/admin/upload-business-rules" -F "files=@reglas.pdf"

# Procesar para resúmenes
curl -X POST "/admin/process-business-rules?rule_type=summary&category=kpi"

# Ver estadísticas
curl -X GET "/admin/business-rules/stats"

# Limpiar todo
curl -X DELETE "/admin/business-rules/clear"
```

## 📝 Logging Detallado

Todos los procesamientos se registran en:
- `data_store/logs/report_flow/report_flow_YYYYMMDD.log`
- `data_store/logs/business_rules_log.json`

### Ejemplo de log exitoso:
```
🧠 RECUPERACIÓN RAG - BUSINESS_SNIPPETS
Query: resumen ejecutivo defectos KPI reglas definiciones calidad  
📚 Fuentes encontradas: 3
📖 CONTEXTO RECUPERADO: Tipo detectado: summary, Snippets: 3, 
Fuentes: [reglas_resumen.pdf, kpi_definiciones.pdf]

📋 SNIPPETS DE NEGOCIO - RESUMEN
📚 Snippets obtenidos: 3
----- Snippet 1 -----
Fuente: reglas_resumen.pdf
ID: chunk_abc123...
Texto: Los resúmenes ejecutivos deben incluir...
```

## ✅ Beneficios

1. **Contexto Rico**: Los reportes incluyen reglas específicas del negocio
2. **Consistencia**: Todos los reportes siguen las mismas reglas
3. **Escalabilidad**: Fácil agregar nuevas reglas sin cambiar código
4. **Trazabilidad**: Log completo de qué reglas se usaron
5. **Flexibilidad**: Diferentes reglas para diferentes secciones

## 🔧 Troubleshooting

### ❌ "0 snippets encontrados"
- Verificar que los PDFs fueron procesados correctamente
- Revisar estadísticas en `/admin/business-rules/stats`
- Validar que el tipo de query coincide con las reglas vectorizadas

### ❌ "Colección no disponible"  
- Asegurar que al menos un PDF fue procesado exitosamente
- Verificar logs en `business_rules_log.json`
- Reintentar el procesamiento desde Admin UI

### ❌ Errores de extracción de PDF
- Instalar dependencias: `pip install PyMuPDF` o `pip install unstructured`
- Verificar que el PDF no esté protegido por contraseña
- Revisar logs de procesamiento en Admin UI
