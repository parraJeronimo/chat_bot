# Laboratorio 08–09 · AnimaBot Veterinaria con SQLite

Esta carpeta es el proyecto de la veterinaria con las reservas guardadas en **SQLite** (`reservas.db`) y lista para conectarse a Gradio. Sigue el orden del `Laboratorio_Clase_08_09.md`; aquí está lo que cambió y cómo comprobarlo con los datos de la veterinaria.

## 1. Qué archivo hace cada trabajo

| Archivo | Estado | Qué hace |
|---|---|---|
| `almacen_sqlite.py` | **Adaptado** | `AgendaSQLite`: tabla, intervalos, transacciones, migración desde JSON |
| `main.py` | **Migrado** | Mismas rutas y cuerpos; ahora llaman a `agenda.*` en vez de leer y escribir JSON |
| `app_gradio.py` | Entregado, sin cambios | Pantalla, botones y estado por sesión |
| `main_sqlite_ejemplo.py` | Entregado, sin cambios | Referencia para estudiar. Usa el horario genérico: no la ejecuten sobre su `reservas.db` |
| `consulta_llm.py` | **Nuevo** | Peticiones a Groq y a la API; `ejecutar()`, lo que llama el botón Confirmar |
| `chatbot_memoria.py` | **Nuevo** | La memoria: historial, planes y `procesar_turno()`. Ver el punto 5 |
| `pruebas_almacen_sqlite.py` | Nuevo | 19 pruebas del almacén. Solo necesitan Python |
| `pruebas_chatbot.py` | Nuevo | Prueba el chatbot completo con un Groq de mentira (sin clave ni internet) |
| `probar_demo.py` | Actualizado | Pruebas de la API y del chat de Flowise con una base temporal |
| `negocio.json`, `reservas.json` | Sin cambios | Catálogo y reservas anteriores (la migración las lee) |

### Cambios en `almacen_sqlite.py`
Todos los parámetros nuevos son opcionales: las llamadas del laboratorio (`agenda.crear(cliente, servicio, fecha, hora)`, etc.) siguen funcionando igual.

- **`mascota`**: la veterinaria la pide en cada cita. Hay una columna nueva; si ya existe una base creada con el archivo original, se agrega sola sin perder filas.
- **Horario por día** (`horarios=`): lunes a viernes 08:00–18:00 y **sábado 08:00–13:00**, como en `negocio.json`. El archivo original solo admitía un horario único.
- **Hora actual del negocio** (`zona=`): hoy no se ofrecen ni se aceptan horas que ya pasaron.
- **Código `AB-` + 12 caracteres** (`prefijo=`, `largo_codigo=`): el mismo formato de antes, que el prompt de Flowise ya espera.
- **`modificar` parcial**: puede cambiar solo la mascota, solo el cliente o solo el horario. Los datos que no se indican se conservan, y se resuelven dentro de la misma transacción.
- **Domingo**: consultar su disponibilidad devuelve una lista vacía (como antes) en vez de un error; reservar en domingo sí se rechaza.

### Cambios en `main.py`
| Ruta | Almacén | Notas |
|---|---|---|
| `GET /servicios` | `negocio.json` | Igual |
| `GET /disponibilidad` | `agenda.disponibilidad()` | Mantiene la clave `horarios`, agrega `duracion_minutos` y acepta `excluir=CODIGO` (opcional): al mover una cita, su propio horario cuenta como libre |
| `GET /reservas` | `agenda.listar()` | **Nueva**: sirve para ver las filas guardadas |
| `POST /reservas` | `agenda.crear()` | Mismo cuerpo: `cliente, mascota, servicio, fecha, hora, confirmado` |
| `GET /reservas/{codigo}` | `agenda.consultar()` | El código se normaliza a mayúsculas |
| `PUT /reservas/{codigo}` | `agenda.modificar()` | Campos opcionales + `confirmado` |
| `DELETE /reservas/{codigo}?confirmado=true` | `agenda.cancelar()` | Cancelar dos veces devuelve 200 con la cita ya cancelada |
| `POST /chat` | usa las funciones anteriores | El puente de Flowise sigue funcionando |

La función `llamar_agenda()` convierte los errores del almacén en HTTP: **404** código inexistente, **409** cruce con otra reserva, **422** datos inválidos, **503** si la base no responde. Es el equivalente de `responder()` en `main_sqlite_ejemplo.py`; se llama distinto porque en este archivo `responder()` ya era la respuesta del chat.

### Diferencias de comportamiento respecto a la versión con JSON
1. Una hora **fuera del horario** (por ejemplo 18:00) ahora responde **422**; antes respondía 409. El 409 queda solo para cruces de intervalos.
2. Solo se aceptan horas en pasos de 30 minutos (09:00, 09:30…). Una hora como 09:15 se rechaza.
3. `creada_en` y `cancelada_en` ya no se guardan. `precio_cop` no está en la tabla: se toma del catálogo al responder.

## 2. Poner los archivos y preparar el entorno

Copien el contenido de esta carpeta sobre su carpeta `Demostraciones_02_03` (reemplaza `main.py`, `probar_demo.py`, `LEEME.md` y `VALIDACION.md`). Si el equipo ya tenía sus propios `consulta_llm.py` y `chatbot_memoria.py` de la clase anterior, guárdenlos aparte antes de copiar: los de esta carpeta son nuevos y los reemplazarían. Desde la carpeta, con el `.venv` que ya tienen:

```powershell
.\.venv\Scripts\python.exe -m pip install "gradio>=6,<7"
.\.venv\Scripts\python.exe pruebas_almacen_sqlite.py
.\.venv\Scripts\python.exe probar_demo.py
.\.venv\Scripts\python.exe pruebas_chatbot.py
```

Si las tres terminan sin `Traceback` (verán varias líneas `OK`), el almacén, la API y el chatbot están bien. `pruebas_chatbot.py` no necesita clave de Groq ni internet.

## 3. Migrar las reservas anteriores (opcional)

`reservas.json` está vacío en este paquete, así que no hay nada que importar. Si hicieron reservas de práctica con la versión anterior:

```powershell
.\.venv\Scripts\python.exe almacen_sqlite.py --migrar reservas.json --negocio negocio.json --base reservas.db
```

Es seguro repetirlo: la segunda vez informa `ya_existentes`. Si el JSON tiene un cruce de intervalos o un código repetido con datos distintos, se detiene y **no importa nada**.

## 4. Encender la API y revisar

```powershell
.\.venv\Scripts\python.exe -m uvicorn main:app --reload --port 8011
```

Abran `http://127.0.0.1:8011/docs`, prueben consultar, crear, modificar y cancelar, y comprueben que aparece `reservas.db`. Para ver las filas:

```powershell
.\.venv\Scripts\python.exe -m sqlite3 reservas.db "SELECT codigo, cliente, mascota, servicio, fecha, hora, estado FROM reservas;"
```

(Requiere Python 3.12 o posterior; también pueden abrir `http://127.0.0.1:8011/reservas`.)

Después, en otra terminal, inicien Gradio como indica la sección 9 del laboratorio (`CHATBOT_API_URL`, `GROQ_MODEL`, `GROQ_API_KEY` y `app_gradio.py`). **No guarden la clave en ningún archivo ni la incluyan en capturas.**

## 5. Cómo funcionan `consulta_llm.py` y `chatbot_memoria.py`

**Un turno** (`procesar_turno`, llamado desde `enviar()` de `app_gradio.py`):

1. El historial de la sesión viaja a Groq junto con el mensaje nuevo. El primer mensaje es el del sistema: dice qué puede hacer el asistente, el catálogo y **la fecha de hoy**, para entender «mañana» o «el viernes».
2. Groq responde con un **plan** en JSON: la acción (`servicios`, `disponibilidad`, `reservar`, `consultar`, `modificar`, `cancelar` o `conversar`) y los datos que conoce.
3. Python valida el plan (servicio del catálogo, fecha y hora con formato correcto), lo completa con la memoria y decide: pedir el dato que falta, consultar la API, o preparar una operación que **espera confirmación**.
4. Las operaciones que escriben (reservar, modificar, cancelar) **no se ejecutan en ese turno**: el plan queda en `estado["pendiente"]`. Solo el botón **Confirmar** llama a `ejecutar(plan, confirmar=True)`, y sin `confirmar=True` esa función se niega.

**La memoria** tiene dos capas, porque un modelo a veces se descuida:

- *El modelo ve todo el historial*, incluidos sus planes anteriores y dos campos que escribe el sistema: `esperando` (el dato que se le pidió a la persona) y `sistema_dijo` (lo que se le mostró). Así una respuesta de una sola palabra, como «Arturo», se entiende como el dato pendiente.
- *Python repite esa memoria de forma segura*: recuerda el **cliente y la mascota** de toda la sesión, los datos de la **solicitud que sigue en curso** (se cierra al Confirmar o Descartar) y el **código de la última cita**, para poder decir «cancela mi cita» sin repetirlo. Si el modelo pone el mismo nombre como cliente y como mascota, o clasifica mal una respuesta suelta, se corrige.

**Disponibilidad y cruces los decide la API**, no el modelo: antes de pedir confirmación se consulta `GET /disponibilidad`, y si el horario se ocupa justo antes de pulsar Confirmar, el `409` se explica y no se guarda nada. Una consulta de un solo dato («¿a qué hora es?») responde solo ese dato.

**Qué no se probó:** el comportamiento del modelo real de Groq. Las pruebas simulan sus respuestas. Si en el chat real el modelo se equivoca con frecuencia (por ejemplo, con fechas relativas), ajusten el texto de `PROMPT` en `chatbot_memoria.py`; lo demás está comprobado.

## 6. Las pruebas del laboratorio con los datos de la veterinaria

Usen una fecha futura de lunes a viernes (por ejemplo 2030-10-14). Duraciones: consulta general 30 min, vacunación y desparasitación 20, peluquería 60, cirugía menor 90.

| # | Qué hacer | Resultado esperado |
|---|---|---|
| 1 | Pedir servicios y disponibilidad desde Gradio | Datos reales del catálogo y horas libres |
| 2 | Completar una solicitud en varios turnos | Se ve el plan pendiente antes de confirmar |
| 3 | Confirmar | Una fila nueva en `reservas.db` con la mascota |
| 4 | Peluquería a las 10:00 y luego consulta general a las 10:30 | La segunda se rechaza (cruce), aunque la hora de inicio sea distinta |
| 5 | Consulta general a las **11:00** | Se acepta: empieza justo cuando termina la peluquería |
| 6 | Mover una reserva a un horario libre, y luego a uno ocupado | Cambia en el primer caso; en el segundo conserva sus datos |
| 7 | Cancelar la peluquería de las 10:00 | Vuelven a aparecer 10:00 y 10:30 como disponibles |
| 8 | Descartar una solicitud (ABORTAR / «no») | No se crea ninguna fila |
| 9 | Reiniciar el chat | La conversación empieza de nuevo; las filas siguen guardadas |
| 10 | Ventana normal + ventana privada | Cada una conserva su conversación; si ambas piden el mismo intervalo, solo una se acepta |
| 11 | Apagar y volver a encender la API | Las reservas siguen en la base |

Pruebas extra propias de la veterinaria: el **sábado** la última consulta general es a las 12:30 y una cirugía menor de 90 minutos no puede empezar después de las 11:30; el **domingo** no tiene horas libres.

## 7. Qué se comprobó antes de entregar y qué falta

**Comprobado:**
- Las 19 pruebas de `pruebas_almacen_sqlite.py` y la migración por línea de comandos.
- `probar_demo.py` completo (API y `/chat` de Flowise) contra SQLite real, usando un sustituto simplificado de FastAPI/Pydantic.
- `pruebas_chatbot.py` completo: reserva en varios turnos, memoria, consulta, cambio, cancelación, cruces, carrera al confirmar, respuestas sueltas, errores de Groq y de la API. Usa las funciones reales de `app_gradio.py`, el código real que habla con Groq (contra un servidor local de mentira) y SQLite real.
- El cliente HTTP real (`urllib`) hacia la API: éxito, 404, 409, 422, errores 5xx, parámetros en la URL, PUT y DELETE.
- Que cada prueba detecta fallos introducidos a propósito (cruces, cancelación, memoria, código recordado, `excluir`, fuga de la clave).

**No se pudo comprobar aquí** (no hay internet para instalar FastAPI ni Gradio, y no hay clave de Groq): las pruebas con FastAPI y Gradio **reales**, la pantalla de Gradio y las respuestas del modelo real de Groq. Esas las corren ustedes con los comandos del punto 2 y la tabla del punto 6.
