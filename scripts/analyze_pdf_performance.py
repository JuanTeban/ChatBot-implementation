#!/usr/bin/env python3
"""
Script para analizar logs de generación de PDFs y envío de emails
Genera reportes de rendimiento y identifica cuellos de botella
"""

import json
import re
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from collections import defaultdict

class PDFPerformanceAnalyzer:
    """Analizador de rendimiento para logs de PDF y email"""
    
    def __init__(self, log_dir: str = "data_store/logs/pdf_flow"):
        self.log_dir = Path(log_dir)
        self.operations = defaultdict(list)
        self.errors = []
        
    def parse_log_file(self, log_file: Path) -> Dict[str, Any]:
        """Parsea un archivo de log y extrae métricas de tiempo"""
        metrics = {
            "file": log_file.name,
            "operations": {},
            "errors": [],
            "total_time": 0,
            "start_time": None,
            "end_time": None
        }
        
        if not log_file.exists():
            return metrics
            
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        current_operation = None
        operation_start = None
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # Extraer timestamp
            timestamp_match = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
            if timestamp_match:
                timestamp = timestamp_match.group(1)
                
                # Detectar inicio de operación
                if "⏱️ INICIO:" in line:
                    operation_match = re.search(r'⏱️ INICIO: (.+)', line)
                    if operation_match:
                        current_operation = operation_match.group(1)
                        operation_start = timestamp
                        
                # Detectar fin de operación
                elif "✅ FIN:" in line and current_operation:
                    duration_match = re.search(r'Duración: ([\d.]+)s', line)
                    if duration_match:
                        duration = float(duration_match.group(1))
                        metrics["operations"][current_operation] = {
                            "duration": duration,
                            "start": operation_start,
                            "end": timestamp
                        }
                        current_operation = None
                        
                # Detectar errores
                elif "❌ ERROR" in line:
                    error_msg = line.split("|")[-1].strip() if "|" in line else line
                    metrics["errors"].append({
                        "timestamp": timestamp,
                        "message": error_msg
                    })
                    
                # Detectar tiempo total
                elif "⏱️ Tiempo total:" in line:
                    total_match = re.search(r'Tiempo total: ([\d.]+)s', line)
                    if total_match:
                        metrics["total_time"] = float(total_match.group(1))
                        
        return metrics
    
    def analyze_logs(self, days: int = 1) -> Dict[str, Any]:
        """Analiza logs de los últimos N días"""
        cutoff_date = datetime.now() - timedelta(days=days)
        
        all_metrics = []
        total_operations = defaultdict(list)
        total_errors = []
        
        # Buscar archivos de log
        for log_file in self.log_dir.glob("*.log"):
            # Verificar fecha del archivo
            try:
                file_date_str = log_file.stem.split("_")[-1]  # Extraer fecha del nombre
                file_date = datetime.strptime(file_date_str, "%Y%m%d")
                if file_date < cutoff_date:
                    continue
            except (ValueError, IndexError):
                # Si no se puede parsear la fecha, incluir el archivo
                pass
                
            metrics = self.parse_log_file(log_file)
            all_metrics.append(metrics)
            
            # Agregar operaciones al total
            for op_name, op_data in metrics["operations"].items():
                total_operations[op_name].append(op_data["duration"])
                
            # Agregar errores al total
            total_errors.extend(metrics["errors"])
        
        # Calcular estadísticas
        stats = {
            "period": f"Últimos {days} días",
            "files_analyzed": len(all_metrics),
            "total_operations": {},
            "errors": total_errors,
            "summary": {}
        }
        
        for op_name, durations in total_operations.items():
            if durations:
                stats["total_operations"][op_name] = {
                    "count": len(durations),
                    "avg_duration": sum(durations) / len(durations),
                    "min_duration": min(durations),
                    "max_duration": max(durations),
                    "total_time": sum(durations)
                }
        
        # Calcular resumen general
        if total_operations:
            all_durations = [d for durations in total_operations.values() for d in durations]
            stats["summary"] = {
                "total_operations_count": len(all_durations),
                "total_time_spent": sum(all_durations),
                "avg_operation_time": sum(all_durations) / len(all_durations),
                "slowest_operation": max(all_durations),
                "fastest_operation": min(all_durations)
            }
        
        return stats
    
    def generate_report(self, stats: Dict[str, Any], output_file: Optional[str] = None) -> str:
        """Genera un reporte legible de las estadísticas"""
        report = []
        report.append("=" * 80)
        report.append("📊 REPORTE DE RENDIMIENTO - GENERACIÓN DE PDFS Y EMAILS")
        report.append("=" * 80)
        report.append(f"📅 Período: {stats['period']}")
        report.append(f"📁 Archivos analizados: {stats['files_analyzed']}")
        report.append("")
        
        # Resumen general
        if stats["summary"]:
            report.append("📈 RESUMEN GENERAL:")
            report.append(f"   • Total de operaciones: {stats['summary']['total_operations_count']}")
            report.append(f"   • Tiempo total invertido: {stats['summary']['total_time_spent']:.2f}s")
            report.append(f"   • Tiempo promedio por operación: {stats['summary']['avg_operation_time']:.2f}s")
            report.append(f"   • Operación más rápida: {stats['summary']['fastest_operation']:.2f}s")
            report.append(f"   • Operación más lenta: {stats['summary']['slowest_operation']:.2f}s")
            report.append("")
        
        # Desglose por operación
        if stats["total_operations"]:
            report.append("🔍 DESGLOSE POR OPERACIÓN:")
            report.append("-" * 60)
            
            # Ordenar por tiempo promedio (más lento primero)
            sorted_ops = sorted(
                stats["total_operations"].items(),
                key=lambda x: x[1]["avg_duration"],
                reverse=True
            )
            
            for op_name, op_stats in sorted_ops:
                report.append(f"📝 {op_name}:")
                report.append(f"   • Cantidad: {op_stats['count']}")
                report.append(f"   • Promedio: {op_stats['avg_duration']:.2f}s")
                report.append(f"   • Mínimo: {op_stats['min_duration']:.2f}s")
                report.append(f"   • Máximo: {op_stats['max_duration']:.2f}s")
                report.append(f"   • Tiempo total: {op_stats['total_time']:.2f}s")
                report.append("")
        
        # Errores
        if stats["errors"]:
            report.append("❌ ERRORES ENCONTRADOS:")
            report.append("-" * 60)
            for error in stats["errors"][:10]:  # Mostrar solo los primeros 10
                report.append(f"🕐 {error['timestamp']}: {error['message']}")
            if len(stats["errors"]) > 10:
                report.append(f"... y {len(stats['errors']) - 10} errores más")
            report.append("")
        
        # Recomendaciones
        report.append("💡 RECOMENDACIONES:")
        report.append("-" * 60)
        
        if stats["total_operations"]:
            slowest_op = max(stats["total_operations"].items(), key=lambda x: x[1]["avg_duration"])
            if slowest_op[1]["avg_duration"] > 5.0:
                report.append(f"⚠️  La operación '{slowest_op[0]}' es muy lenta ({slowest_op[1]['avg_duration']:.2f}s promedio)")
                report.append("   Considera optimizar esta operación")
            
            if stats["summary"]["avg_operation_time"] > 10.0:
                report.append("⚠️  El tiempo promedio general es alto")
                report.append("   Revisa la configuración del navegador y la red")
        
        if stats["errors"]:
            report.append(f"⚠️  Se encontraron {len(stats['errors'])} errores")
            report.append("   Revisa la configuración y conectividad")
        
        report.append("")
        report.append("=" * 80)
        
        report_text = "\n".join(report)
        
        # Guardar reporte si se especifica archivo
        if output_file:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(report_text)
            print(f"📄 Reporte guardado en: {output_path}")
        
        return report_text

def main():
    parser = argparse.ArgumentParser(description="Analizar rendimiento de generación de PDFs")
    parser.add_argument("--days", type=int, default=1, help="Días hacia atrás para analizar (default: 1)")
    parser.add_argument("--output", type=str, help="Archivo de salida para el reporte")
    parser.add_argument("--log-dir", type=str, default="data_store/logs/pdf_flow", help="Directorio de logs")
    
    args = parser.parse_args()
    
    analyzer = PDFPerformanceAnalyzer(args.log_dir)
    stats = analyzer.analyze_logs(args.days)
    report = analyzer.generate_report(stats, args.output)
    
    print(report)

if __name__ == "__main__":
    main()
