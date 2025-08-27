# Sistema de Logging de Generación de PDFs y Emails

Este directorio contiene los logs detallados del sistema de generación de PDFs y envío de emails, implementado para identificar y resolver problemas de rendimiento.

## 📁 Estructura de Archivos

- `pdf_generation_YYYYMMDD.log` - Logs principales de generación de PDFs
- `pdf_worker_YYYYMMDD.log` - Logs del worker de Pyppeteer
- `README.md` - Este archivo

## 🔍 Qué se Registra

### Generación de PDFs
- ⏱️ Tiempo de cada paso del proceso
- 📋 Información del preview y consultor
- 🔧 Configuración de URL y directorios
- 🌐 Navegación y renderizado de páginas
- 📄 Generación del archivo PDF
- ❌ Errores y excepciones

### Envío de Emails
- 📧 Configuración SMTP
- 🔐 Autenticación
- 📤 Envío del mensaje
- 📎 Adjuntado de PDFs
- ❌ Errores de conexión

## 📊 Métricas Registradas

Cada operación registra:
- **Duración exacta** en segundos
- **Estado de éxito/fallo**
- **Timestamp** de inicio y fin
- **Contexto** adicional (URLs, archivos, etc.)

## 🛠️ Herramientas de Análisis

### 1. Script de Análisis de Rendimiento
```bash
# Analizar logs del último día
python scripts/analyze_pdf_performance.py

# Analizar logs de los últimos 7 días
python scripts/analyze_pdf_performance.py --days 7

# Guardar reporte en archivo
python scripts/analyze_pdf_performance.py --output reporte_rendimiento.txt
```

### 2. Endpoints de Monitoreo
- `GET /admin/pdf-performance` - Métricas generales
- `GET /admin/pdf-performance/recent` - Métricas de la última hora
- `GET /admin/pdf-performance/slowest` - Operaciones más lentas
- `GET /admin/pdf-performance/errors` - Errores recientes

### 3. Script de Pruebas
```bash
# Probar el sistema de logging
python scripts/test_pdf_logging.py
```

## 📈 Interpretación de Logs

### Tiempos Normales
- **Preparación**: < 1 segundo
- **Navegación**: 2-5 segundos
- **Renderizado**: 8 segundos (configurado)
- **Generación PDF**: 1-3 segundos
- **Envío email**: 2-5 segundos

### Señales de Problemas
- **Navegación > 10s**: Problemas de red o servidor
- **Renderizado > 15s**: Gráficos complejos o recursos lentos
- **Generación PDF > 10s**: Problemas de memoria o CPU
- **Email > 10s**: Problemas de SMTP o red

## 🔧 Optimizaciones Implementadas

### 1. Logging Detallado
- Timers precisos para cada operación
- Contexto completo de errores
- Rotación automática de archivos

### 2. Monitoreo en Tiempo Real
- Endpoints REST para métricas
- Identificación de cuellos de botella
- Alertas automáticas

### 3. Análisis Automático
- Reportes de rendimiento
- Identificación de operaciones lentas
- Recomendaciones de optimización

## 🚨 Solución de Problemas

### Si los logs no se generan:
1. Verificar que el directorio `data_store/logs/pdf_flow/` existe
2. Comprobar permisos de escritura
3. Ejecutar `python scripts/test_pdf_logging.py`

### Si los tiempos son muy altos:
1. Revisar conectividad de red
2. Verificar recursos del sistema (CPU, memoria)
3. Comprobar configuración del navegador
4. Analizar logs con `analyze_pdf_performance.py`

### Si hay errores frecuentes:
1. Revisar configuración SMTP
2. Verificar que Chrome/Edge esté instalado
3. Comprobar que los archivos PDF se generan correctamente

## 📋 Próximos Pasos

1. **Ejecutar pruebas** para verificar que el logging funciona
2. **Generar algunos PDFs** para recolectar datos iniciales
3. **Analizar logs** para identificar cuellos de botella
4. **Implementar optimizaciones** basadas en los hallazgos

## 🔗 Archivos Relacionados

- `app/utils/pdf_logger.py` - Sistema de logging
- `app/routers/reports.py` - Endpoint de generación de PDFs
- `scripts/pdf_worker_url.py` - Worker de Pyppeteer
- `app/email_sender/sender.py` - Sistema de envío de emails
- `app/routers/admin.py` - Endpoints de monitoreo
