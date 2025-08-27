# Report Flow Logging System

## 📋 Descripción

Este sistema de logging captura **todo el flujo completo** de generación de reportes, incluyendo:

- 🔍 **Generación de SQL**: Prompts, contexto de esquemas, SQL generada
- 💾 **Ejecución de consultas**: SQL ejecutada, resultados obtenidos, errores
- 🧠 **Contexto RAG**: Queries de búsqueda, documentos recuperados, fuentes
- 📋 **Snippets de negocio**: Fragmentos de conocimiento usados
- 🤖 **Interacciones LLM**: Prompts enviados y respuestas recibidas
- 📊 **Generación de gráficos**: Tipo, datos, éxito/fallo
- ⏱️ **Tiempo total**: Duración completa del proceso

## 📁 Ubicación de Logs

Los logs se guardan automáticamente en:
```
data_store/logs/report_flow/report_flow_YYYYMMDD.log
```

Ejemplo: `report_flow_20250823.log`

## 🔍 Formato de Logs

Cada entrada tiene el formato:
```
YYYY-MM-DD HH:MM:SS | NIVEL | MENSAJE
```

### Tipos de Secciones:

- **🚀 INICIANDO GENERACIÓN DE REPORTE** - Inicio del proceso
- **🔍 GENERACIÓN DE SQL** - Creación de consultas
- **💾 EJECUCIÓN DE SQL** - Resultados de consultas
- **🧠 RECUPERACIÓN RAG** - Búsqueda de contexto
- **📋 SNIPPETS DE NEGOCIO** - Fragmentos de conocimiento
- **🤖 LLM INTERACTION** - Comunicación con IA
- **📊 GENERACIÓN DE GRÁFICO** - Creación de visualizaciones
- **🏁 REPORTE COMPLETADO/FALLIDO** - Final del proceso

## 📊 Información Capturada

### Para cada reporte generado:
- **Consultor**: Nombre del responsable
- **Tipo**: preview | from_template
- **SQL generada**: Query completa con contexto
- **Datos obtenidos**: Número de registros
- **Prompts completos**: Texto enviado al LLM
- **Respuestas LLM**: Texto generado (resumen/recomendaciones)
- **Gráficos**: Tipos y estado de generación
- **Tiempo total**: Duración en segundos
- **Errores**: Detalles completos de fallos

## 🛠️ Uso

El logging es **automático**. Cada vez que generes un reporte via:
- `/reports/preview` (nuevo reporte)
- Plantillas SQL aprobadas

Se creará automáticamente un log detallado.

## 📖 Ejemplo de Flujo Logged

```
================================================================================
🚀 INICIANDO GENERACIÓN DE REPORTE
📋 Consultor: Juan Pérez
📋 Tipo: preview
================================================================================

🔍 GENERACIÓN DE SQL
Pregunta/Objetivo: Para el responsable 'Juan Pérez', obtener todos los campos...
📚 CONTEXTO DE ESQUEMAS USADO:
TABLA PRINCIPAL: seguimiento_hallazgos_solman_seguimiento_detalles_defecto
⚡ SQL GENERADA:
SELECT * FROM seguimiento_hallazgos_solman_seguimiento_detalles_defecto 
WHERE UPPER(responsable_del_defecto) LIKE UPPER('%Juan%Pérez%');

💾 EJECUCIÓN DE SQL - ✅ EXITOSA
📊 Registros obtenidos: 15

🤖 LLM INTERACTION - RESUMEN_EJECUTIVO
📤 PROMPT ENVIADO:
Eres un analista de proyectos experto. Redacta un RESUMEN EJECUTIVO...
📥 RESPUESTA LLM:
El consultor Juan Pérez presenta 15 defectos activos...

🏁 REPORTE ✅ COMPLETADO
📊 Gráficos generados: 4
⏱️ Tiempo total: 12.45s
```

## 🔧 Configuración

El sistema está configurado para:
- ✅ **Rotación diaria**: Un archivo por día
- ✅ **UTF-8 encoding**: Soporte completo de caracteres
- ✅ **Truncamiento inteligente**: Textos largos se cortan automáticamente
- ✅ **Sin impacto en rendimiento**: Logging asíncrono
