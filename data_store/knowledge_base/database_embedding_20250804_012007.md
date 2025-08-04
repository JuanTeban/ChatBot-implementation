# DATABASE KNOWLEDGE BASE
Generated: 2025-08-04 01:20:07

## DATABASE OVERVIEW
- **Total Tables:** 1
- **Total Rows:** 70

---

## TABLE DOCUMENTATION

### TABLE 1: seguimiento_hallazgos_solman_seguimiento_detalles_defecto

- **SOURCE FILE:** Seguimiento hallazgos - Solman.xlsx (Sheet: hallazgos_solman_seguimiento_detalles_defecto)
- **ROW COUNT:** 70
- **COLUMN COUNT:** 13

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
| fecha_propuesta_de_solucion | VARCHAR | YES | None |
| comentarios | VARCHAR | YES | None |
| frente | VARCHAR | YES | None |
| bloqueante_escenarios | VARCHAR | YES | None |

#### UNIQUE VALUES:
- **modulo:** FM, FI, AP, PAPM, TX, RE, TRM , GR, MM, AA, EW, TR, GL, AR, BCM
- **categoria_de_defecto:** 0, Roles y perfiles, Maestros, Desarrollo, Configuración, Control de cambio, Funcionales, Legados
- **estado_de_defecto:** Nuevo, Propuesta de solución, Acción responsable test, En tratamiento
- **frente:** ET, FINANCIERO, FINANCIERO , NO FINANCIERO , TECNICO, NO FINANCIERO

#### SAMPLE DATA (First 5 Records):
|   n | defecto                                         | modulo   | id_hallazgo_matriz   | responsable_del_defecto              | autor_del_defecto                    | antiguedad_del_defecto_promedio_en_dias   | categoria_de_defecto   | estado_de_defecto       | fecha_propuesta_de_solucion   | comentarios                                                                                               | frente        | bloqueante_escenarios   |
|----:|:------------------------------------------------|:---------|:---------------------|:-------------------------------------|:-------------------------------------|:------------------------------------------|:-----------------------|:------------------------|:------------------------------|:----------------------------------------------------------------------------------------------------------|:--------------|:------------------------|
|   1 | H0-MM-Modif Pedido mensaje salida (8000001608)  | MM       | Nuevo                | Wilmar Vargas Preciado (174)         | MONICA PATRICIA GIRALDO PEREZ (192)  | 4,54                                      | 0                      | Nuevo                   | 2025-04-08 00:00:00           |                                                                                                           | NO FINANCIERO | SI                      |
|   2 | H0_AP_Error en documento soporte (8000001605)   | AP       | Nuevo                | Alberto Rivera Betancourt (822)      | SINDY CRISTINA ALZATE ARIAS (201)    | 4,65                                      | Desarrollo             | Nuevo                   |                               |                                                                                                           | FINANCIERO    | SI                      |
|   3 | H0_TR_ERROR MONEDA E IMPORTE ME (8000001603)    | TR       | Nuevo                | Nurky Castro (46)                    | ANGELA PATRICIA PERDOMO (175)        | 5,65                                      | Desarrollo             | En tratamiento          |                               |                                                                                                           | FINANCIERO    |                         |
|   4 | H2_ RE_ EPM ERROR ANULACIÓN AJUSTE (8000001471) | RE       | Nuevo                | Pedro Emilio Jimenez Pabon (139)     | NATALIA EUGENIA RAMIREZ MOLINA (193) | 13,91                                     | Desarrollo             | En tratamiento          |                               |                                                                                                           | FINANCIERO    | SI                      |
|   5 | H0_ RE_ CONTABILIDA FINANCIERA AGN (8000001462) | RE       | Nuevo                | NATALIA EUGENIA RAMIREZ MOLINA (193) | NATALIA EUGENIA RAMIREZ MOLINA (193) | 14,62                                     | Roles y perfiles       | Acción responsable test |                               | 22/07/2025: Equipo tecnico esta revisando con el funcional la parametrizacion  para dar fecha del ajuste  | ET            |                         |
|     |                                                 |          |                      |                                      |                                      |                                           |                        |                         |                               | 28/07/2025: Equipo tecnico regresa para funcional para su revisiòn.                                       |               |                         |

---
