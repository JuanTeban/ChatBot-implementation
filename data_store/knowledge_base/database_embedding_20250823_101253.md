# DATABASE KNOWLEDGE BASE
Generated: 2025-08-23 10:12:53

## DATABASE OVERVIEW
- **Total Tables:** 1
- **Total Rows:** 66

---

## TABLE DOCUMENTATION

### TABLE 1: seguimiento_hallazgos_solman_seguimiento_detalles_defecto

- **SOURCE FILE:** Seguimiento hallazgos - Solman.xlsx (Sheet: hallazgos_solman_seguimiento_detalles_defecto)
- **ROW COUNT:** 66
- **COLUMN COUNT:** 16

#### TABLE STRUCTURE:
```sql
CREATE TABLE seguimiento_hallazgos_solman_seguimiento_detalles_defecto (...);
```

#### COLUMN DEFINITIONS:
| Column Name | Data Type | Nullable | Default Value |
|-------------|-----------|----------|---------------|
| n | BIGINT | YES | None |
| defecto | VARCHAR | YES | None |
| modulo | VARCHAR | YES | None |
| id_hallazgo_matriz | VARCHAR | YES | None |
| responsable_del_defecto | VARCHAR | YES | None |
| autor_del_defecto | VARCHAR | YES | None |
| antiguedad_del_defecto_promedio_en_dias | VARCHAR | YES | None |
| categoria_de_defecto | VARCHAR | YES | None |
| estado_de_defecto | VARCHAR | YES | None |
| hora_de_creacion_de_defecto_utc | VARCHAR | YES | None |
| hora_modificacion_defecto_utc | VARCHAR | YES | None |
| fecha_propuesta_de_solucion | VARCHAR | YES | None |
| comentarios | VARCHAR | YES | None |
| frente | VARCHAR | YES | None |
| bloqueante_escenarios | VARCHAR | YES | None |
| unnamed_15 | VARCHAR | YES | None |

#### UNIQUE VALUES:
- **modulo:** FM, TR, GL, AR, GL , AA, MM, PAPM, TX, GR, AP, RE
- **categoria_de_defecto:** Roles y perfiles, Maestros, 0, Configuración, Desarrollo, Control de cambio
- **estado_de_defecto:** Nuevo, En tratamiento, Transferido, Propuesta de solución, Acción responsable test
- **frente:** TECNICO , NO FINANCIERO, FINANCIERO , NO FINANCIERO , Financiero , TECNICO, FINANCIERO
- **bloqueante_escenarios:** NO, SI

#### SAMPLE DATA (First 5 Records):
|   n | defecto                                              | modulo   | id_hallazgo_matriz   | responsable_del_defecto           | autor_del_defecto                    | antiguedad_del_defecto_promedio_en_dias   | categoria_de_defecto   | estado_de_defecto     | hora_de_creacion_de_defecto_utc   | hora_modificacion_defecto_utc   | fecha_propuesta_de_solucion   | comentarios                                                                                                                                        | frente        | bloqueante_escenarios   | unnamed_15   |
|----:|:-----------------------------------------------------|:---------|:---------------------|:----------------------------------|:-------------------------------------|:------------------------------------------|:-----------------------|:----------------------|:----------------------------------|:--------------------------------|:------------------------------|:---------------------------------------------------------------------------------------------------------------------------------------------------|:--------------|:------------------------|:-------------|
|   1 | H0_AA_Lentitud carga de datos en MC (8000001452)     | AA       | Nuevo                | ANA MILENA IBARBO GUTIERREZ (320) | ANA MILENA IBARBO GUTIERREZ (320)    | 38,94                                     | 0                      | Propuesta de solución | 14/07/2025 19:34                  | 2025-01-08 14:52:00             |                               |                                                                                                                                                    | NO FINANCIERO | NO                      |              |
|   2 | H1_MM_SC120  EROR VISTA WORZONE (8000001414)         | MM       | Nuevo                | GUSTAVO ESPINOSA (646)            | PAOLA ANDREA JIMENEZ RODRIGUEZ (492) | 43,18                                     | Configuración          | En tratamiento        | 2025-10-07 13:51:00               | 14/08/2025 13:56                | PENDIENTE SAP                 | Se escalo a SAP. 926160/2025                                                                                                                       | NO FINANCIERO | NO                      |              |
|     |                                                      |          |                      |                                   |                                      |                                           |                        |                       |                                   |                                 |                               | 22/08/2025: La nota se encuentra en tratamiento por SAP                                                                                            |               |                         |              |
|   3 | H0_EPM_TR_ErrorPagosDavivienda (8000001408)          | TR       | 1408                 | MANUEL HERNANDO SANTA JARA (132)  | MANUEL HERNANDO SANTA JARA (132)     | 43,81                                     | Desarrollo             | Propuesta de solución | 2025-09-07 22:33:00               | 19/08/2025 16:55                |                               | Control de cambio                                                                                                                                  | FINANCIERO    | NO                      |              |
|   4 | H0_PAPM_1294_Capturadecontroladores (8000001391)     | PAPM     | 1294                 | JULIANA LUNA RESTREPO (186)       | JUAN DAVID VARGAS RESTREPO (127)     | 43,94                                     | Desarrollo             | Propuesta de solución | 2025-09-07 19:32:00               | xº                              |                               | Abap:Danilo en tratamiento con Consultor Fiori, Entrega 28 de Julio para pruebas funcionales                                                       | Financiero    | SI                      |              |
|     |                                                      |          |                      |                                   |                                      |                                           |                        |                       |                                   |                                 |                               | 7/29/2025: Equipo tecnico entrega para pruebas dia Lunes 28                                                                                        |               |                         |              |
|   5 | H0_MM_1258_Carga registros info Proveed (8000001382) | MM       | Nuevo                | GUSTAVO ESPINOSA (646)            | LUIS GERMAN PINEDA ARCILA (191)      | 44,06                                     | Maestros               | En tratamiento        | 2025-09-07 16:31:00               | 28/07/2025 22:16                | PENDIENTE SAP                 | 28/07/2025: Se escala Nota -  884403/2025                                                                                                          | NO FINANCIERO | NO                      |              |
|     |                                                      |          |                      |                                   |                                      |                                           |                        |                       |                                   |                                 |                               | CEDR: Despues de hacer varios simulacro se crea nota ya que el proceso se realiza con la herramienta de migracion de datos cockpik estandar de SAP |               |                         |              |
|     |                                                      |          |                      |                                   |                                      |                                           |                        |                       |                                   |                                 |                               | 5/08/2025: El dia de hoy SAP propuso solución                                                                                                      |               |                         |              |
|     |                                                      |          |                      |                                   |                                      |                                           |                        |                       |                                   |                                 |                               | 22/08/2025: Se encuentra en procesaminto de SAP                                                                                                    |               |                         |              |

---
