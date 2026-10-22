---

tipo: bitacora-clase curso: periodo: EAM-2026II equipo: Equipo\_Parra\_Ospina\_Bravo corte: 2 semana: "7" clase: "7" fecha: 2026-10-12 estado: en-progreso tags:

- chatbots  
- bitacora  
- fastapi  
- flowise  
- python  
- sqlite  
- gradio

---

# Bitácora Unificada — Clase \[7\]

> \[\!tip\] Cómo usar esta plantilla Duplica esta nota al finalizar cada clase y nómbrala `C##_AAAA-MM-DD_Tema`. Completa los campos entre corchetes y conserva enlaces verificables.

## 1\. Datos de la sesión

| Campo | Registro |  |
| :---- | :---- | :---- |
| Tema | \[Consolidación arquitectura backend, flujo conversacional, persistencia SQLite e interfaz web\] |  |
| Objetivo | Integrar y validar el flujo end-to-end del chatbot veterinario para consulta de servicios, agendamiento, modificación y cancelación de citas con almacenamiento relacional y soporte multi-turno |  |
| Proyecto | \[animabot\] |  |
| Inicio | \[9:00 am\] |  |
| Cierre | \[12:00 am\] |  |

## 2\. Participación y responsabilidades

| Integrante | Asistió | Rol de la clase | Responsabilidad asumida | Aporte verificable |
| :---- | :---: | :---- | :---- | :---- |
| Jeronimo Parra Hurtado | Sí | Backend & API | Endpoints de FastAPI, lógica de negocio y esquema SQLite | `main.py`, `almacen_sqlite.py`, `consulta_llm.py` |
| Sebastian Ospina Herrera | Si | Prompt & UI | Orquestación en Flowise, prompts de extracción e interfaz UI | `Demo_03_Flowise_FastAPI.json`, `app_gradio.py`, `prompt_sistema.txt` |
| Jose Manuel Bravo Navarro | Si | QA & Doc | Automatización de pruebas, verificación de contexto y doc. | `probar_demo.py`, `pruebas_chatbot.py`, `pruebas_almacen_sqlite.py`, `LEEME.md` |

## 3\. Reto aplicado al proyecto

### Funcionalidad trabajada

**Nombre del chatbot:** animabot

**Dominio:** Dominio cerrado

**Problema:** Resolver la desinformación en la clínica veterinaria, automatizar el agendamiento y modificación de citas, evitar pérdida de contexto en respuestas cortas del cliente y evitar colisiones en horarios

**Usuario objetivo:** Clientes y tutores de mascotas de la veterinaria

**Objetivo:** Informar sobre servicios veterinarios, agendar, consultar, modificar y cancelar citas 24/7, entregando respuestas puntuales o resúmenes completos según la solicitud del usuario

**Capacidades (3–5):** 

1. **Información instantánea de servicios y tarifas:** Lectura de catálogo desde `negocio.json` y respuestas a datos puntuales (`campo`) o resúmenes completos  
2. **Consulta de disponibilidad en tiempo real:** Cálculo dinámico de franjas horarias libres filtrando citas activas  
3. **Gestión integral de reservas (CRUD completo):** Creación (`POST`), consulta (`GET`), modificación (`PUT`) y cancelación (`DELETE`) de citas  
4. **Mantenimiento de contexto y extracción inteligente:** Captura de datos faltantes en respuestas de una sola palabra (ej. "Arturo") y preservación de memoria ante mensajes fuera de tema sin duplicar información entre cliente y mascota  
5. **Persistencia relacional e interfaz interactiva:** Almacenamiento seguro en SQLite (`almacen_sqlite.py`) accesible mediante una interfaz web accesible en Gradio (`app_gradio.py`)  
* **Sí puede:** \* Consultar servicios, precios y horarios de atención.  
* Verificar disponibilidad de agenda por fecha.  
* Registrar nuevas reservas validando que el horario esté libre.  
* Modificar citas existentes cambiando fecha o hora sin alterar el código de reserva.  
* Cancelar citas liberando la franja horaria ocupada.  
* Responder consultas puntuales (solo la hora, solo el precio, solo el estado) usando extracción por `campo`.  
* Retener datos del cliente/mascota ante intervenciones fuera de tema.  
* Persistir la información en base de datos SQLite y responder mediante interfaz gráfica en Gradio.  
* **No puede:**  
* Agendar o modificar citas en horarios previamente ocupados o fuera de la jornada laboral.  
* Asignar el mismo nombre simultáneamente al cliente y a la mascota en el proceso de extracción.  
* Borrar físicamente el historial de transacciones (las cancelaciones se registran como cambio de estado).  
* Ejecutar cambios en la base de datos sin confirmación o sin pasar por las validaciones de FastAPI.

**Patrón adaptado:** INFORMAR \+ CONVERSAR \+ CONSULTAR DISPONIBILIDAD \+ CREAR \+ CONSULTAR \+ MODIFICAR \+ CANCELAR

**Proceso (pasos):** 

1. **Recepción:** El usuario envía un mensaje (frase completa o dato aislado) a través de Gradio o llamada direct a la API.  
2. **Interpretación NLU:** Flowise (`Demo_03_Flowise_FastAPI.json`) o el cliente LLM extrae la intención (`agendar`, `modificar`, `cancelar`, `consultar`, `fuera_de_tema`) y los campos (`cliente`, `mascota`, `servicio`, `fecha`, `hora`, `campo`).  
3. **Gestión de Contexto:** `main.py` procesa los datos entrantes, completa slots pendientes, evita duplicar cliente/mascota y mantiene los datos previos aun si hay mensajes intercalados fuera de tema.  
4. **Validación de Negocio:** FastAPI valida reglas (existencia del servicio, horario válido y disponibilidad).  
5. **Persistencia:** Las operaciones exitosas se persisten de manera relacional en SQLite (`almacen_sqlite.py`).  
6. **Respuesta:** La API retorna el resultado puntual solicitado o la confirmación de la transacción a la interfaz del cliente.

### Criterios de aceptación

- [ ] 1.Arquitectura REST operativa en FastAPI con endpoints de lectura, creación, modificación y cancelación  
- [ ] 2.Persistencia relacional en base de datos SQLite mediante `almacen_sqlite.py`  
- [ ] 3\. Flujo NLU configurado en Flowise para la extracción de intenciones y slots estructurados  
- [ ] 4\. Manejo de consultas puntuales a través del campo `campo`  
- [ ] 5.Conservación de slots y memoria ante mensajes de una sola palabra o intervenciones fuera de tema  
- [ ] 6.Despliegue de interfaz conversacional en Gradio (`app_gradio.py`).  
- [ ] 7.Suite de pruebas automatizadas con teardown de datos limpia y documentada

### Archivos o componentes modificados

* **`main.py`**: Servidor principal FastAPI. Implementa los endpoints REST, el enrutamiento de intenciones, la gestión de memoria en sesión y la extracción del parámetro `campo`.  
* **`almacen_sqlite.py`**: Capa de persistencia relacional que gestiona la creación de tablas, inserción, actualización, consulta y cancelación de reservas en la base de datos SQLite.  
* **`Demo_03_Flowise_FastAPI.json`**: Grafo y prompts de Flowise configurados para la extracción estricta de JSON, intenciones NLU y reconocimiento del parámetro `campo`.  
* **`app_gradio.py`**: Interfaz de usuario basada en web para interacción conversacional con el chatbot.  
* **`chatbot_memoria.py` / `consulta_llm.py`**: Módulos auxiliares para la gestión de historial conversacional y comunicación directa con APIs de modelos de lenguaje.  
* **`negocio.json` / `reservas.json`**: Catálogo estático de servicios veterinarios y soporte de respaldo en JSON.  
* **`probar_demo.py`**: Suite de pruebas integradas que valida los flujos end-to-end de la API y el chatbot.  
* **`pruebas_chatbot.py`**: Pruebas unitarias para validar la extracción de entidades y conservación de memoria  
* **`pruebas_almacen_sqlite.py`**: Pruebas unitarias para validar las operaciones CRUD directamente sobre la base de datos SQLite  
* **`LEEME.md` / `REPORTE_PRUEBAS.md`**: Documentación técnica del proyecto y reporte detallado de la estrategia de QA.

## 4\. Decisiones técnicas

| Decisión | Razón | Alternativa descartada |
| :---- | :---- | :---- |
| **Separación entre NLU y Lógica de Negocio** | Delegar al LLM únicamente la interpretación de intención y extracción de entidades, dejando la validación de disponibilidad y persistencia a FastAPI/SQLite | Permitir que el LLM modifique directamente la base de datos o tome decisiones de disponibilidad sin validación previa |
| **Persistencia Relacional en SQLite (`almacen_sqlite.py`)** | Garantizar la integridad ACID, evitar corrupción de datos por concurrencia y facilitar consultas estructuradas | Mantener únicamente archivos JSON planos para el almacenamiento de reservas en producción |
| **Manejo del parámetro `campo`** | Permitir que el usuario consulte datos puntuales (ej. "¿Cuál es el costo?" o "¿A qué hora es?") sin forzar la lectura del resumen completo de la cita | Retornar siempre la estructura completa de la reserva independientemente de la pregunta |
| **Estrategia de Memoria Persistente en FastAPI** | Mantener los slots recopilados (`cliente`, `mascota`, `servicio`) aun cuando el usuario introduzca comentarios fuera de tema o responda con una sola palabra | Reiniciar el flujo de diálogo ante cualquier respuesta que no encajara exactamente en la estructura esperada |
| **Teardown Explícito en Suite de Pruebas (`probar_demo.py`)** | Garantizar la limpieza de la base de datos de pruebas mediante cancelación al finalizar cada test | Dejar reservas de prueba persistidas en el sistema |

## 5\. Problemas y soluciones

| Problema encontrado | Causa identificada | Solución aplicada | ¿Cómo se verificó? |
| :---- | :---- | :---- | :---- |
| **Duplicación de datos entre cliente y mascota** | El prompt extractor asignaba el mismo nombre a ambos slots cuando la entrada del usuario era ambigua (ej. "Carlos") | Refinamiento de reglas en `Demo_03_Flowise_FastAPI.json` y validación de slots en `main.py` para asegurar asignación única | Ejecución de `pruebas_chatbot.py` con entradas ambiguas |
| **Pérdida de contexto ante mensajes fuera de tema** | El clasificador marcaba el mensaje como "fuera de tema" e ignoraba la memoria temporal acumulada | Preservación explícita del diccionario de sesión en `main.py` ante intenciones no transaccionales | Test de integración en `probar_demo.py` simulando preguntas fuera de tema durante el agendamiento |
| **Acumulación de registros basura en pruebas** | `probar_demo.py` creaba reservas para validar endpoints pero no ejecutaba la limpieza al finalizar | Incorporación de llamadas a `DELETE /reservas/{codigo}` en el bloque teardown de cada caso de prueba | Inspección de la base de datos SQLite tras ejecutar la suite de pruebas completa |
| **Bloqueo de horarios al modificar una cita (`PUT`)** | La modificación no liberaba temporalmente el horario actual del cliente al evaluar disponibilidad de la nueva hora | Ajuste del endpoint `PUT` en `main.py` para excluir la reserva actual al consultar disponibilidades | Pruebas de modificación de hora sobre la misma reserva |
|  |  |  |  |

## 6\. Evidencias

| Tipo | Descripción | Enlace o ruta |
| :---- | :---- | :---- |
| Codigo | \[Endpoints, intenciones y flujo conversacional\] | \[`main.py` \] |
| Bases de datos | \[Modulo de almacenamiento relacional SQLite\] | \[`almacen_sqlite.py`\] |
| Interfaz UI | \[Aplicación web interactiva en Gradio\] | \[`app_gradio.py`\] |
| Prompt/Flujo | \[JSON del flujo de Flowise actualizado\] | \[`Demo_03_Flowise_FastAPI.json`\] |
| Pruebas | \[Script de pruebas ajustado y corregido\] | \[`probar_demo.py`, `pruebas_chatbot.py`\] |
| Documentacion | \[Explicacion detallada de los cambios\] | \[`LEEME.md`\] |

## 7\. Uso de inteligencia artificial

> \[\!important\] Registrar la IA no reemplaza la explicación técnica. El equipo debe verificar, adaptar y comprender cualquier resultado utilizado.

| Herramienta | Objetivo o pregunta | Qué se utilizó | Cómo se verificó | Qué se modificó |
| :---- | :---- | :---- | :---- | :---- |
| **Flowise / Groq LLM** | Extracción de entidades NLU, detección de intenciones y parametrización de campos | `Demo_03_Flowise_FastAPI.json`, `consulta_llm.py` | Validación del JSON de salida mediante Pydantic y pruebas unitarias en `pruebas_chatbot.py` | Prompt de extracción refinado en el JSON |
| **Asistente de Código AI** | Generación de plantillas de pruebas unitarias y ayuda en la maquetación de la interfaz | `pruebas_almacen_sqlite.py`, `app_gradio.py` | Revisión manual línea por línea, refactorización y ejecución de tests automatizados |  |

Si no se utilizó IA, escribir: **No se utilizó inteligencia artificial en esta sesión.**

## 8\. Defensa técnica y retroalimentación

| Campo | Registro |
| :---- | :---- |
| Integrante que defendió | \[Nombre\] |
| Pregunta recibida | \[Pregunta\] |
| Respuesta resumida | \[Respuesta\] |
| Retroalimentación docente | \[Observación\] |
| Mejora acordada | \[Acción concreta\] |

## 9\. Aprendizajes

- **Principio de Mínimo Privilegio en LLMs:** Los modelos de lenguaje son excelentes intérpretes de intenciones pero no deben controlar directamente el estado del sistema ni la base de datos sin una capa intermedia de validación (FastAPI).  
* **Gestión Eficiente del Estado:** Mantener una memoria conversacional sólida requiere reglas claras de resolución de ambigüedades (evitando sobrescribir datos valiosos cuando el usuario responde de forma escueta o cambia momentáneamente de tema).  
* **Importancia de la Suite de Pruebas Automatizada:** Contar con scripts de prueba integrados (`probar_demo.py`) permitió identificar tempranamente regresiones, como la pérdida de citas o la duplicación de entidad entre cliente y mascota

## 10\. Revisión antes de entregar

- [x] Todos los integrantes registraron un aporte verificable.  
- [x] Los enlaces y rutas de evidencia funcionan.  
- [x] Los criterios de aceptación están actualizados.  
- [x] El uso de IA fue declarado y verificado.  
- [x] El equipo puede explicar las decisiones registradas.