# Bitácora · Laboratorio 08–09 · AnimaBot Veterinaria

**Equipo:** _(nombres)_  **Fecha:** _(fecha)_  **Negocio:** AnimaBot Veterinaria

> Las secciones 1 y 2 están redactadas a partir del código del proyecto: **léanlas, compruébenlas contra sus archivos y reescríbanlas con sus palabras**. Las secciones 3 a 5 son evidencias que solo ustedes pueden generar. No incluyan la API key en ningún archivo ni captura.

## 1. Cómo viaja una solicitud

**¿Qué función recibe el mensaje?** `enviar(mensaje, estado)` de `app_gradio.py`, que se ejecuta al pulsar Enviar o Enter. Esa función llama a `procesar_turno(mensaje, historial, clave, modelo)` de `chatbot_memoria.py`, que envía el historial a Groq (`pedir_plan_groq` en `consulta_llm.py`), recibe un **plan** en JSON, lo valida, lo completa con la memoria y decide si pide un dato, consulta la API o prepara una operación por confirmar.

Ese turno solo **propone** una operación: la deja en `estado["pendiente"]`. Se ejecuta cuando se pulsa **Confirmar** (`confirmar(estado)`), que llama a `ejecutar(plan, confirmar=True)` de `consulta_llm.py`, y ese cliente HTTP llama a la API. **Descartar** (`descartar(estado)`) borra el plan sin ejecutar nada.

**¿Dónde vive el historial?** En el estado de la sesión de Gradio (`gr.State`, creado con `nuevo_estado()`): `estado["historial"]` es lo que se envía al modelo en cada turno (el mensaje del sistema, lo que escribió la persona y los planes que se fueron guardando, con los campos `esperando` y `sistema_dijo`), `estado["pantalla"]` es lo que ve la persona y `estado["pendiente"]` guarda la operación que espera confirmación. Cada ventana del navegador tiene su propio estado; reiniciar el chat lo recrea, pero no borra las reservas, porque estas viven en la base de datos.

**¿Qué endpoint ejecuta la operación?**

| Operación | Endpoint | Función en `main.py` | Método del almacén |
|---|---|---|---|
| Crear | `POST /reservas` | `crear()` | `agenda.crear()` |
| Modificar | `PUT /reservas/{codigo}` | `modificar()` | `agenda.modificar()` |
| Cancelar | `DELETE /reservas/{codigo}?confirmado=true` | `cancelar()` | `agenda.cancelar()` |
| Consultar | `GET /reservas/{codigo}` | `consultar()` | `agenda.consultar()` |
| Disponibilidad | `GET /disponibilidad` | `disponibilidad()` | `agenda.disponibilidad()` |

**¿Qué sentencia SQL corresponde?** (están en `almacen_sqlite.py`)

```sql
-- Crear
INSERT INTO reservas (codigo, cliente, mascota, servicio, fecha, hora, duracion_minutos, estado)
VALUES (?, ?, ?, ?, ?, ?, ?, 'activa');
-- Modificar
UPDATE reservas SET cliente=?, mascota=?, servicio=?, fecha=?, hora=?, duracion_minutos=? WHERE codigo=?;
-- Cancelar (la fila se conserva; solo cambia el estado)
UPDATE reservas SET estado='cancelada' WHERE codigo=?;
-- Antes de crear o modificar: reservas activas del día con las que podría cruzarse
SELECT hora, duracion_minutos FROM reservas WHERE fecha=? AND estado='activa' AND codigo<>?;
```

## 2. Por qué la disponibilidad y el guardado van en una misma transacción

Cada operación de escritura abre la conexión con `BEGIN IMMEDIATE`, que reserva el derecho a escribir desde el inicio. Mientras una petición comprueba si el intervalo está libre y lo guarda, otra petición que quiera escribir espera. Cuando le llega el turno, ya ve la fila de la primera y detecta el cruce. Si la comprobación y el guardado fueran pasos separados, dos personas podrían ver el mismo horario libre al mismo tiempo y las dos guardarlo. Si algo falla dentro de la transacción, se hace `rollback` y no queda nada a medias.

Un intervalo se cruza con otro cuando `inicio_nuevo < fin_existente` **y** `fin_nuevo > inicio_existente`. Por eso una peluquería de 60 minutos a las 10:00 bloquea una consulta a las 10:30, y una consulta a las 11:00 sí cabe (empieza justo cuando la otra termina).

## 3. Evidencias de las pruebas del laboratorio

| # | Prueba | ¿Pasó? | Evidencia (captura o salida) |
|---|---|---|---|
| 1 | Servicios y disponibilidad desde Gradio | | |
| 2 | Solicitud en varios turnos con plan pendiente | | |
| 3 | Confirmar y ver la fila en SQLite | | |
| 4 | Cruce: peluquería 10:00 y consulta 10:30 rechazada | | |
| 5 | Reserva contigua a las 11:00 aceptada | | |
| 6 | Modificar a libre / a ocupado (conserva datos) | | |
| 7 | Cancelar y ver el intervalo disponible otra vez | | |
| 8 | Descartar sin crear fila | | |
| 9 | Reiniciar el chat: filas siguen guardadas | | |
| 10 | Dos ventanas: conversaciones separadas, un solo ganador | | |
| 11 | Reiniciar la API: reservas siguen en la base | | |

## 4. Antes y después, rechazo y persistencia

- **Disponibilidad antes de reservar** (fecha, servicio, horas): _(pegar)_
- **Disponibilidad después de reservar la peluquería de 10:00** (deben faltar 10:00 y 10:30): _(pegar)_
- **Mensaje de rechazo del cruce** (HTTP 409): _(pegar)_
- **Filas después de reiniciar la API** (`SELECT ... FROM reservas`): _(pegar)_

## 5. Un error que encontramos

- **Qué pasó:** _(describan lo que vieron)_
- **Causa:** _(por qué ocurrió)_
- **Cómo lo resolvimos:** _(qué cambiaron y cómo comprobaron que quedó bien)_

## Lista de entrega

- [ ] `main.py`, `almacen_sqlite.py`, `app_gradio.py`, `consulta_llm.py`, `chatbot_memoria.py`
- [ ] `reservas.db` con datos de prueba
- [ ] Esta bitácora con las evidencias
- [ ] Sin API key en archivos, variables guardadas ni capturas
