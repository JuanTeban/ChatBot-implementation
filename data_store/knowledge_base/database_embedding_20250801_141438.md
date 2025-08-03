# DATABASE KNOWLEDGE BASE
Generated: 2025-08-01 14:14:38

## DATABASE OVERVIEW
- **Total Tables:** 5
- **Total Rows:** 86

---

## TABLE DOCUMENTATION

### TABLE 1: company_data_departments

- **SOURCE FILE:** company_data.xlsx (Sheet: data_departments)
- **ROW COUNT:** 3
- **COLUMN COUNT:** 2

#### TABLE STRUCTURE:
```sql
CREATE TABLE company_data_departments (...);
```

#### COLUMN DEFINITIONS:
| Column Name | Data Type | Nullable | Default Value |
|-------------|-----------|----------|---------------|
| department_id | BIGINT | YES | None |
| department_name | VARCHAR | YES | None |

#### UNIQUE VALUES:
- **department_name:** HR, Sales, Engineering

#### SAMPLE DATA (First 5 Records):
|   department_id | department_name   |
|----------------:|:------------------|
|              10 | Engineering       |
|              20 | Sales             |
|              30 | HR                |

---

### TABLE 2: company_data_employees

- **SOURCE FILE:** company_data.xlsx (Sheet: data_employees)
- **ROW COUNT:** 5
- **COLUMN COUNT:** 5

#### TABLE STRUCTURE:
```sql
CREATE TABLE company_data_employees (...);
```

#### COLUMN DEFINITIONS:
| Column Name | Data Type | Nullable | Default Value |
|-------------|-----------|----------|---------------|
| employee_id | BIGINT | YES | None |
| name | VARCHAR | YES | None |
| salary | BIGINT | YES | None |
| department_id | BIGINT | YES | None |
| hire_date | DATE | YES | None |

#### UNIQUE VALUES:
- **name:** Ana, Diana, Carlos, Elena, Bruno

#### SAMPLE DATA (First 5 Records):
|   employee_id | name   |   salary |   department_id | hire_date           |
|--------------:|:-------|---------:|----------------:|:--------------------|
|             1 | Ana    |    45000 |              10 | 2021-05-10 00:00:00 |
|             2 | Bruno  |    52000 |              20 | 2022-03-15 00:00:00 |
|             3 | Carlos |    61000 |              10 | 2020-08-21 00:00:00 |
|             4 | Diana  |    48000 |              30 | 2023-01-11 00:00:00 |
|             5 | Elena  |    70000 |              20 | 2019-12-03 00:00:00 |

---

### TABLE 3: departments_departments

- **SOURCE FILE:** departments.xlsx (Sheet: departments)
- **ROW COUNT:** 3
- **COLUMN COUNT:** 2

#### TABLE STRUCTURE:
```sql
CREATE TABLE departments_departments (...);
```

#### COLUMN DEFINITIONS:
| Column Name | Data Type | Nullable | Default Value |
|-------------|-----------|----------|---------------|
| department_id | BIGINT | YES | None |
| department_name | VARCHAR | YES | None |

#### UNIQUE VALUES:
- **department_name:** Engineering, Sales, HR

#### SAMPLE DATA (First 5 Records):
|   department_id | department_name   |
|----------------:|:------------------|
|              10 | Engineering       |
|              20 | Sales             |
|              30 | HR                |

---

### TABLE 4: employees_employees

- **SOURCE FILE:** employees.xlsx (Sheet: employees)
- **ROW COUNT:** 5
- **COLUMN COUNT:** 5

#### TABLE STRUCTURE:
```sql
CREATE TABLE employees_employees (...);
```

#### COLUMN DEFINITIONS:
| Column Name | Data Type | Nullable | Default Value |
|-------------|-----------|----------|---------------|
| employee_id | BIGINT | YES | None |
| name | VARCHAR | YES | None |
| salary | BIGINT | YES | None |
| department_id | BIGINT | YES | None |
| hire_date | DATE | YES | None |

#### UNIQUE VALUES:
- **name:** Bruno, Ana, Diana, Elena, Carlos

#### SAMPLE DATA (First 5 Records):
|   employee_id | name   |   salary |   department_id | hire_date           |
|--------------:|:-------|---------:|----------------:|:--------------------|
|             1 | Ana    |    45000 |              10 | 2021-05-10 00:00:00 |
|             2 | Bruno  |    52000 |              20 | 2022-03-15 00:00:00 |
|             3 | Carlos |    61000 |              10 | 2020-08-21 00:00:00 |
|             4 | Diana  |    48000 |              30 | 2023-01-11 00:00:00 |
|             5 | Elena  |    70000 |              20 | 2019-12-03 00:00:00 |

---

### TABLE 5: seguimiento_hallazgos_solman_seguimiento_defectos

- **SOURCE FILE:** Seguimiento hallazgos - Solman.xlsx (Sheet: hallazgos_solman_seguimiento_defectos)
- **ROW COUNT:** 70
- **COLUMN COUNT:** 13

#### TABLE STRUCTURE:
```sql
CREATE TABLE seguimiento_hallazgos_solman_seguimiento_defectos (...);
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
- **modulo:** PAPM, TX, RE, TRM , BCM, MM, AA, EW, AP, GR, TR, GL, AR, FM, FI
- **categoria_de_defecto:** Roles y perfiles, Funcionales, Legados, Control de cambio, 0, Maestros, Desarrollo, Configuración
- **estado_de_defecto:** En tratamiento, Acción responsable test, Nuevo, Propuesta de solución
- **frente:** ET, FINANCIERO , FINANCIERO, NO FINANCIERO, NO FINANCIERO , TECNICO

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
