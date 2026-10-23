# Demostraciones del primer corte · AnimaBot Veterinaria

> **Actualización del Laboratorio 08–09.** Desde esta versión las reservas ya no se guardan en
> `reservas.json`: viven en **`reservas.db` (SQLite)** mediante `almacen_sqlite.py`. Las menciones de este
> documento al archivo JSON, al bloqueo de escritura y a «un solo worker» describen la versión anterior.
> Las rutas de la API, los cuerpos de las peticiones y el flujo de `/chat` para Flowise se conservan.
> Para ejecutar y probar la versión actual sigue **`LEEME_Laboratorio_08_09.md`**.

Este paquete contiene dos flujos importables en **Flowise 2.2.8**, una API FastAPI y datos ficticios. La demo 2 muestra conversación y memoria. La demo 3 muestra reservas reales dentro del archivo local de práctica.

## 0. Novedades de esta versión

Este paquete ya incluía guardado de reservas por fecha, consulta de estado por código, memoria de
sesión y cancelación (ver la tabla siguiente); lo que se agregó ahora es:

- **Modificar una reserva activa** (`PUT /reservas/{codigo}` en `main.py` y la intención `modificar`
  en el chat de la demo 3): cambia fecha, hora, servicio, cliente o mascota, validando disponibilidad
  igual que al crear una cita. Si el nuevo horario está ocupado, se rechaza y la cita no se toca.
- **Responder solo el dato puntual que se pide** (campo `campo` en la extracción): si preguntan
  «¿a qué hora es mi cita AB-...?» o «¿cuánto vale?», la API responde solo esa línea en vez del
  resumen completo. Preguntar por «toda la cita» sigue devolviendo el resumen completo.
- El prompt de extracción de `Demo_03_Flowise_FastAPI.json` ya quedó actualizado con la intención
  `modificar` y el campo `campo`; no hay que editarlo a mano.
- Se agregaron pruebas de esto en `probar_demo.py` (sección final del archivo).
- **Corrección de robustez:** el nodo que extrae los datos con Groq (`LLM Chain`) analiza cada
  mensaje solo, sin ver el historial de la conversación — así es como funciona ese nodo en
  Flowise, no es una falla de configuración. Por eso una respuesta suelta como «Arturo» o
  «Princesa» puede llegar sin datos útiles, o incluso clasificada como «fuera de tema», y antes se
  perdía o hacía repetir la misma pregunta. Ahora `main.py` reconoce cuándo el mensaje es una sola
  palabra (compatible con un nombre) justo cuando se esperaba el nombre del cliente o de la
  mascota, y la usa en vez de perderla. Fecha, hora y servicio no se adivinan así porque exigen un
  formato exacto o una opción de una lista fija; ahí sigue aplicando la recomendación de escribir
  mensajes explícitos («mi mascota se llama Arturo», «el 2026-09-18 a las 16:00»).
- **Corrección de un cruce cliente/mascota:** al responder con una sola palabra, el LLM a veces
  llenaba **a la vez** el campo `cliente` y el campo `mascota` con el mismo texto (por ejemplo,
  guardaba el nombre de la mascota también como nombre del cliente en `reservas.json`). Ahora
  `main.py` detecta cuándo los dos campos llegan idénticos en el mismo mensaje y se queda solo con
  el que realmente hacía falta completar, sin pisar el dato que ya tenías guardado.

Lo que ya existía y **no hacía falta agregar**, para que quede claro:

| Lo que pediste | Dónde ya estaba |
|---|---|
| Guardar reservas por fecha | `POST /reservas` en `main.py`, que escribe en `reservas.json` |
| Un código para consultar el estado de la reserva | `GET /reservas/{codigo}` y la intención `consultar` del chat |
| Recordar al usuario y sus datos durante la conversación | `SESIONES` en `main.py` (por `session_id`) en la demo 3, y Buffer Memory en la demo 2 |
| Eliminar reservas | `DELETE /reservas/{codigo}` (cancelación, conserva el registro con `estado=cancelada`) |

Nota: el registro de citas vive en `reservas.json`, no en un archivo `.js`; no existe ni hace falta un `reservas.js` en este proyecto.

## 1. Qué archivo usamos para cada cosa

| Archivo | Uso |
|---|---|
| `Demo_02_Groq_Memoria.json` | Importar en Flowise: GroqChat, Buffer Memory y Conversation Chain |
| `Demo_03_Flowise_FastAPI.json` | Importar en otro chatflow: extracción con Groq y conexión a la API |
| `main.py` | API de servicios, disponibilidad, reservas y estado de la conversación |
| `negocio.json` | Servicios, precios, duración, horarios y condiciones ficticias |
| `reservas.json` | Registro persistente; inicialmente contiene `[]` |
| `prompt_sistema.txt` | Prompt y contexto ya incluidos en el flujo de la demo 2 |
| `puente_flowise.js` | Código ya incluido en el nodo final de la demo 3; no hay que ejecutarlo aparte |
| `requirements.txt` | Dependencias de Python |
| `probar_demo.py` | Prueba automática sin Groq; utiliza archivos temporales |

Importar no incluye credenciales. Debes seleccionar tu clave de Groq en **cada flujo**. La API no necesita una clave de Groq: el consumo del modelo se hace desde Flowise.

## 2. Preparar Groq y Flowise

Sigue el apartado «Cuenta de Groq y API key» de [los fundamentos](../../Clases/Clase_02_Fundamentos.md). El modelo preseleccionado es `llama-3.3-70b-versatile`; cambia por otro modelo de chat autorizado si tu cuenta no lo permite.

Si recibiste únicamente el ZIP: registra tu cuenta en [Groq Console](https://console.groq.com/), crea la clave en [API Keys](https://console.groq.com/keys) y configúrala en **GroqChat → Connect Credential → Create New → Groq API Key**. Los fundamentos y la guía de Clase 01 son documentos del repositorio que se entregan por separado.

En Flowise:

1. Entrar a **Chatflows** y crear un flujo nuevo.
2. Abrir el menú del canvas y elegir **Load Chatflow / Import**; la etiqueta puede variar según la versión.
3. Seleccionar `Demo_02_Groq_Memoria.json` desde esta carpeta. No importar el ZIP ni `negocio.json`.
4. Abrir **GroqChat**, crear o seleccionar la credencial **Groq API** y comprobar el modelo.
5. Guardar con el nombre `Demo 2 - AnimaBot` y abrir el chat de prueba.

No fijar un `Session Id` común en Buffer Memory: la plantilla lo deja vacío para que Flowise gestione la conversación. No introducir la clave en el prompt ni en el JSON.

Si Flowise no está instalado, seguir la instalación de la [Clase 01](../../Clases/Clase_01_Guia_Docente.md). Las plantillas se prepararon para 2.2.8; una versión diferente puede requerir actualizar los nodos.

## 3. Demostración 2: secuencia de mensajes

Enviar, en este orden:

1. `¿Cuánto cuesta la consulta general y cuánto dura?`
2. `Me llamo Laura.`
3. `¿Cómo me llamo?`
4. `¿Tienen descuentos para estudiantes?`
5. `Explícame cómo resolver una integral.`
6. `Reserva una cita para mi mascota mañana.`

Debe responder con los precios del contexto, utilizar el nombre en la misma conversación, reconocer información ausente y explicar que esta demo aún no registra reservas. Abrir una conversación nueva o limpiar el historial y repetir la pregunta del nombre: no debe recuperar el nombre de la sesión anterior.

Este flujo usa una copia pequeña del contexto en el prompt. Si modificas `negocio.json`, debes actualizar también ese contexto en la demo 2. En la demo 3, los datos de negocio se leen desde la API.

## 4. Iniciar FastAPI en Windows

Necesitas Python 3.10 o posterior. Abre PowerShell **en la carpeta de este paquete** y ejecuta:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8011 --workers 1
```

La instalación de dependencias solo se hace la primera vez. En los siguientes encuentros basta con el último comando. Mantén esa terminal abierta; para detener el servidor usa `Ctrl+C`.

Abrir [documentación de la API](http://localhost:8011/docs). Si el puerto está ocupado, elige otro y actualízalo también dentro del nodo final de Flowise.

Usamos `0.0.0.0` para permitir la conexión desde Docker Desktop. Esta API es para práctica local, con datos ficticios y sin autenticación; no la publiques. Si solo usas Flowise con npm en el mismo equipo, puedes iniciar con `--host 127.0.0.1`.

**Un solo worker:** el bloqueo de escritura de JSON protege peticiones concurrentes dentro de un proceso. No ejecutes varias instancias sobre el mismo archivo. La capacidad del ejemplo es una mascota atendida a la vez; ampliar a varios veterinarios requiere adaptar la lógica.

## 5. Probar la API desde `/docs`

En cada operación pulsa **Try it out** y luego **Execute**. Usa una fecha futura de lunes a sábado; los domingos están cerrados. Si reutilizas una fecha escrita en esta guía después de que haya pasado, cámbiala.

1. **GET `/servicios`:** observar el catálogo y los horarios. Los días son `0=lunes` hasta `6=domingo`; un día ausente está cerrado.
2. **GET `/disponibilidad`:** ingresar una fecha futura y `consulta_general`. Copiar una hora realmente disponible.
3. **POST `/reservas`:** cambiar fecha y hora del ejemplo por la selección anterior:

```json
{
  "cliente": "Laura",
  "mascota": "Firulais",
  "servicio": "consulta_general",
  "fecha": "2026-09-18",
  "hora": "16:00",
  "confirmado": true
}
```

4. Copiar el `codigo` de la respuesta y abrir `reservas.json`. La operación ya debe estar guardada.
5. **GET `/reservas/{codigo}`:** consultar ese código.
6. Intentar crear otra reserva en la misma hora: debe devolver `409` y no duplicarla.
7. **PUT `/reservas/{codigo}`:** con la cita del paso 3 todavía activa, envía solo el campo que quieras
   cambiar, por ejemplo `{"hora": "17:00", "confirmado": true}`. Si esa hora está libre, la cita se
   actualiza; si está ocupada, la API responde `409` y no cambia nada.
8. **DELETE `/reservas/{codigo}`:** ingresar el código y `confirmado=true` después de revisar la operación. Se conserva el registro con `estado=cancelada`.
9. Consultar nuevamente la disponibilidad y verificar que el espacio se liberó.

En `/docs`, el campo `confirmado=true` representa la aprobación que da quien está probando. En el chat, la API exige primero un resumen pendiente y luego la palabra **CONFIRMAR**.

## 6. Qué guarda la API

`negocio.json` contiene la configuración. Los cambios requieren reiniciar la API.

`reservas.json` contiene una lista de registros con:

| Campo | Significado |
|---|---|
| `codigo` | Identificador generado por la API |
| `cliente`, `mascota`, `servicio`, `fecha`, `hora` | Datos de la cita |
| `precio_cop`, `duracion_minutos` | Precio y duración al momento del registro |
| `estado` | `activa` o `cancelada` |
| `creada_en` | Fecha y hora de creación, con zona horaria |
| `cancelada_en` | Fecha y hora de cancelación, o `null` |

La API no guarda la clave de Groq ni el historial de mensajes en ese archivo. El estado de las solicitudes de la demo 3 vive en memoria, separado por sesión; al reiniciar la API se pierde lo pendiente y se conservan las reservas.

No se sobrescribe un archivo de reservas ilegible con una lista vacía. Ante ese error se devuelve `503` para poder revisar y recuperar el archivo. Para empezar una práctica desde cero, detén la API, conserva una copia de las evidencias que necesites y reemplaza manualmente el contenido por `[]`.

## 7. Demostración 3: conectar Flowise con FastAPI

Importa `Demo_03_Flowise_FastAPI.json` en **otro chatflow** y selecciona la credencial en GroqChat. El flujo ya incluye estas conexiones:

```text
GroqChat ───────┐
               ├─ LLM Chain: Output Prediction ─ Custom JS Function: Ending Node
Prompt Template┘                                  ↓
                                           POST FastAPI /chat
                                                  ↓
                                         Estado + reservas.json
```

El modelo extrae intención y datos del mensaje; la API mantiene el estado, valida y ejecuta. El resultado final es el texto devuelto por la API. No usamos agentes, herramientas elegidas autónomamente ni RAG.

En el nodo **Custom JS Function**, abre **Javascript Function** y revisa la primera constante:

| Dónde se ejecuta Flowise | `API_URL` |
|---|---|
| Docker Desktop y FastAPI en Windows | `http://host.docker.internal:8011` — ya configurado |
| npm y FastAPI en el mismo Windows | `http://127.0.0.1:8011` |

La dirección se interpreta desde el proceso de Flowise, no desde el navegador. Dentro del contenedor, `localhost` se refiere al propio contenedor. Esta guía presupone que ambos componentes están en tu computador; una instancia remota no puede acceder directamente a tu API local.

Guardar el flujo como `Demo 3 - Citas AnimaBot`. Usar una fecha futura, un servicio válido y horas de 24 horas. Mensajes sugeridos:

1. `Quiero una consulta general para mi mascota Firulais el 2026-09-18.`
2. Elegir una hora de la lista devuelta, por ejemplo `16:00`.
3. `Me llamo Laura.`
4. Leer el resumen; enviar `Mejor a las 15:00` para demostrar una corrección, solo si esa hora está disponible.
5. Enviar `CONFIRMAR`. Comprobar el código y el archivo.
6. `Consulta la cita AB-...` usando el código real recibido.
7. `¿A qué hora es la cita AB-...?` para ver que responde solo la hora, no todo el resumen.
8. `Quiero cambiar la cita AB-... para las 10:00` (una hora distinta y disponible ese mismo día).
9. Leer el resumen del cambio y enviar `CONFIRMAR`. Consultar de nuevo por código y comprobar la nueva hora.
10. `Quiero cancelar la cita AB-...`.
11. Leer el resumen y enviar `CONFIRMAR`.
12. Consultar nuevamente por código y comprobar que dice `cancelada`. Si intentas modificarla después de cancelada, la API lo rechaza.

Controles: **CONFIRMAR** aprueba el resumen vigente; **ABORTAR** o **NO** descartan la solicitud; **/reset** limpia el estado sin borrar reservas. El botón de borrar conversación de Flowise no sustituye `/reset` para una sesión de API que conserve su identificador.

Al igual que para consultar o cancelar, para **modificar** hay que dar el código explícito en el
mismo mensaje que pide el cambio; si ya se confirmó una operación antes, el estado de la sesión se
limpia y hay que repetir el código.

La plantilla pide fechas completas, no resuelve «mañana» ni expresiones relativas. Al consultar o cancelar se proporciona el código explícito. El LLM puede extraer mal un dato: el resumen permite corregirlo y la API rechaza formatos o servicios inválidos. Ante una pregunta ambigua, reescribe con datos explícitos.

La demo 3 es un flujo determinista de casillas (servicio, mascota, fecha, hora, cliente/código), no un chat de preguntas y respuestas libres: preguntas como «¿cómo me llamo?» no las responde aquí, porque no está diseñada para eso. Esa prueba de memoria conversacional es justamente lo que muestra la demo 2. Lo que sí hace la demo 3 es recordar, durante la misma sesión, los datos que ya diste para la reserva (servicio, mascota, fecha, hora, cliente, código), y usarlos sin volver a pedirlos.

### Limitaciones conocidas al probar

- Una pregunta puramente informativa («¿cuánto cuesta la vacunación?») no queda guardada como el
  servicio de una reserva en curso; es solo informativa. Si después quieres agendar ese servicio,
  dilo explícito («resérvame una vacunación»).
- Al **modificar** una cita, si respondes con una sola palabra suelta sin aclarar si es el nuevo
  nombre del cliente o de la mascota (por ejemplo, solo «Toby»), el sistema no lo adivina — a
  propósito, porque equivocarse ahí cambiaría datos de una cita real ya existente. Sé explícito:
  «cambia el nombre de la mascota a Toby».
- Si dices el nombre del cliente y de la mascota exactamente igual en el mismo mensaje (por
  coincidencia real, no por error del LLM), el sistema se queda con uno y preguntará el otro en el
  siguiente turno; no se pierde el dato, solo toma un paso más.

## 8. Verificación y problemas frecuentes

Para ejecutar las pruebas sin Groq ni Flowise:

```powershell
.\.venv\Scripts\python.exe probar_demo.py
```

La prueba usa un archivo temporal: no borra las reservas de la clase. Comprueba concurrencia, disponibilidad, confirmaciones, correcciones, separación de sesiones, cancelación, fechas y errores de almacenamiento.

| Resultado o problema | Qué revisar |
|---|---|
| Error del proveedor antes de recibir respuesta | Credencial, permisos del modelo y límites en Groq |
| No recuerda el nombre en la demo 2 | Conexión de Buffer Memory y continuidad de la sesión |
| No conecta a la API en la demo 3 | Terminal iniciada, puerto 8011 y `API_URL` según Docker/npm |
| `422` | Formatos, servicio permitido y campos requeridos |
| `404` | Código de reserva inexistente |
| `409` | Horario ocupado, fuera del horario o no seleccionable, o intento de modificar/cancelar una cita ya cancelada |
| `503` | Lectura o escritura del archivo; no asumir éxito |
| Se interrumpe la conexión al confirmar | Verificar el archivo y consultar por código antes de repetir |

Las pruebas de integración usan el mismo Flowise 2.2.8 y un modelo local simulado para no necesitar secretos. Esto comprueba importación, memoria y conexión HTTP; **no sustituye la prueba real con tu clave y el modelo de Groq antes de la clase**.

## 9. Evidencia breve para mostrar en clase

Captura del chatflow; consulta con contexto y memoria; resumen antes de confirmar; respuesta con código real; registro JSON; consulta; cancelación; horario liberado; prueba de error. Revisar que ninguna captura ni exportación contenga claves.
