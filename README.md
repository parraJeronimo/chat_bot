# AnimaBot Veterinaria · Chatbot con memoria, FastAPI y SQLite

Chatbot para una veterinaria ficticia. La persona escribe en una pantalla web (Gradio), un modelo de Groq interpreta lo que pide, y una API (FastAPI) guarda las citas en una base de datos SQLite. Con él puedes:

- preguntar por servicios, precios y horarios;
- ver qué horas hay libres;
- **reservar, consultar, modificar y cancelar** citas;
- conversar en varios mensajes: el chatbot **recuerda** tu nombre, el de tu mascota y los datos que ya diste.

Las operaciones que cambian datos (reservar, modificar, cancelar) **nunca se ejecutan solas**: el chatbot te muestra un resumen y esperas a pulsar **Confirmar operación**.

> Todos los datos del proyecto son ficticios (práctica de clase).

---

## Resumen rápido (si ya lo instalaste antes)

Abre **dos** terminales de PowerShell en la carpeta del proyecto.

**Terminal 1: la API**

```powershell
.\.venv\Scripts\python.exe -m uvicorn main:app --reload --port 8011
```

**Terminal 2: la pantalla**

```powershell
$env:CHATBOT_API_URL = "http://127.0.0.1:8011"
$env:GROQ_MODEL = "openai/gpt-oss-120b"
$claveGroqClase = Read-Host "API key de Groq" -AsSecureString
$env:GROQ_API_KEY = [System.Net.NetworkCredential]::new('', $claveGroqClase).Password
.\.venv\Scripts\python.exe app_gradio.py
```

Abre **http://127.0.0.1:7860** en el navegador. Si es tu primera vez, sigue los pasos completos desde la sección 1.

---

## Contenido

1. [Cómo está organizado el proyecto](#1-cómo-está-organizado-el-proyecto)
2. [Antes de empezar](#2-antes-de-empezar)
3. [Preparar el proyecto (una sola vez)](#3-preparar-el-proyecto-una-sola-vez)
4. [Conseguir la clave de Groq y elegir el modelo](#4-conseguir-la-clave-de-groq-y-elegir-el-modelo)
5. [Comprobar que todo funciona (pruebas automáticas)](#5-comprobar-que-todo-funciona-pruebas-automáticas)
6. [Encender el chatbot](#6-encender-el-chatbot)
7. [La pantalla, botón por botón](#7-la-pantalla-botón-por-botón)
8. [Cómo escribirle al chatbot](#8-cómo-escribirle-al-chatbot)
9. [Guion de prueba completo, paso a paso](#9-guion-de-prueba-completo-paso-a-paso)
10. [Frases que dan problemas y cómo escribirlas mejor](#10-frases-que-dan-problemas-y-cómo-escribirlas-mejor)
11. [Reglas del negocio (por qué a veces se rechaza una hora)](#11-reglas-del-negocio-por-qué-a-veces-se-rechaza-una-hora)
12. [Ver los datos guardados en SQLite](#12-ver-los-datos-guardados-en-sqlite)
13. [Apagar, volver a encender y qué se conserva](#13-apagar-volver-a-encender-y-qué-se-conserva)
14. [Solución de problemas](#14-solución-de-problemas)
15. [Seguridad de la clave](#15-seguridad-de-la-clave)

---

## 1. Cómo está organizado el proyecto

```
 Tu navegador (http://127.0.0.1:7860)
        │
        ▼
 app_gradio.py ──► chatbot_memoria.py ──► Groq (el modelo interpreta tu mensaje)
   (pantalla)        (memoria y decisiones)
                           │
                           ▼
                    consulta_llm.py ──► main.py (FastAPI, http://127.0.0.1:8011)
                  (peticiones HTTP)            │
                                               ▼
                                      almacen_sqlite.py ──► reservas.db
```

| Archivo | Para qué sirve |
|---|---|
| `app_gradio.py` | La pantalla del chat y sus botones |
| `chatbot_memoria.py` | La memoria: historial, datos que ya diste, qué falta preguntar |
| `consulta_llm.py` | Habla con Groq y con la API; `ejecutar()` es lo que llama el botón Confirmar |
| `main.py` | La API: servicios, disponibilidad, reservas |
| `almacen_sqlite.py` | Guarda las reservas y evita que dos citas se crucen |
| `negocio.json` | Catálogo de servicios, precios, duraciones y horarios |
| `reservas.db` | **La base de datos.** Se crea sola al encender la API |
| `pruebas_almacen_sqlite.py`, `probar_demo.py`, `pruebas_chatbot.py` | Pruebas automáticas (sección 5) |
| `LEEME_Laboratorio_08_09.md`, `Bitacora_Laboratorio_08_09.md` | Guía técnica del laboratorio y plantilla de bitácora |

**Quién hace qué en cada mensaje:** el modelo de Groq solo *interpreta* lo que escribes (qué quieres hacer y con qué datos). Todo lo demás lo decide el programa: qué dato falta, si el horario está libre, el resumen que ves y los textos que lees. Por eso las respuestas del chatbot siempre tienen el mismo estilo, aunque tú escribas de formas distintas.

---

## 2. Antes de empezar

Necesitas:

- **Windows con PowerShell.**
- **Python 3.10 o superior.** Compruébalo:

  ```powershell
  python --version
  ```

  Debe mostrar algo como `Python 3.12.4`. Si da error o abre la Microsoft Store, instala Python desde python.org marcando la casilla **«Add python.exe to PATH»**, cierra PowerShell y vuelve a abrirlo.
- **Internet** (para instalar paquetes y para hablar con Groq).
- **Una cuenta de Groq** y una API key (sección 4).

---

## 3. Preparar el proyecto (una sola vez)

### 3.1 Entrar a la carpeta del proyecto

Todos los comandos de este documento se ejecutan **dentro de la carpeta que contiene `main.py`**. Cambia la ruta por la tuya:

```powershell
cd "C:\Users\TU_USUARIO\Downloads\Veterinaria_Laboratorio_08_09_SQLite\Demostraciones_02_03"
dir
```

El comando `dir` debe listar, entre otros, `main.py`, `app_gradio.py`, `chatbot_memoria.py`, `consulta_llm.py`, `almacen_sqlite.py` y `negocio.json`. Si no los ves, no estás en la carpeta correcta.

### 3.2 Crear el entorno virtual

```powershell
python -m venv .venv
```

Espera a que termine sin mostrar errores y comprueba que se creó:

```powershell
dir .venv\Scripts\python.exe
```

> **Si ves el error «`.\.venv\Scripts\python.exe` no se reconoce»**, es porque este paso no se hizo o se hizo en otra carpeta. La carpeta `.venv` **no viaja** dentro del zip: hay que crearla en cada carpeta nueva.

### 3.3 Instalar las dependencias

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install "gradio>=6,<7"
```

Tarda uno o dos minutos (Gradio es el paquete más pesado). El aviso *«A new release of pip is available»* se puede ignorar.

### 3.4 Comprobar la instalación

```powershell
.\.venv\Scripts\python.exe -c "import fastapi, uvicorn, gradio; print('Todo instalado')"
```

Debe imprimir `Todo instalado`.

> **Por qué escribimos `.\.venv\Scripts\python.exe` y no solo `python`:** así usamos siempre el Python con los paquetes del proyecto, sin necesidad de «activar» el entorno ni de cambiar permisos de PowerShell.

---

## 4. Conseguir la clave de Groq y elegir el modelo

### 4.1 Crear la API key

1. Entra a **https://console.groq.com** e inicia sesión.
2. Ve a **API Keys** y pulsa **Create API Key**.
3. Ponle un nombre (por ejemplo, `laboratorio`) y **cópiala en ese momento**: Groq solo la muestra una vez. Empieza por `gsk_`.

Si tu profesor te dio una clave para la clase, usa esa.

### 4.2 El modelo

Usa **`openai/gpt-oss-120b`**.

> El modelo `llama-3.3-70b-versatile`, que usaban las demos de Flowise, **fue retirado por Groq el 16 de agosto de 2026** y responde con error. Si algún día `openai/gpt-oss-120b` también se retira, busca uno vigente en la sección de modelos de la consola de Groq y cambia solo el valor de `GROQ_MODEL`.

---

## 5. Comprobar que todo funciona (pruebas automáticas)

Antes de abrir el chat, corre las tres pruebas. **No necesitan clave de Groq ni internet** y usan una base de datos temporal (no tocan tus reservas).

```powershell
.\.venv\Scripts\python.exe pruebas_almacen_sqlite.py
.\.venv\Scripts\python.exe probar_demo.py
.\.venv\Scripts\python.exe pruebas_chatbot.py
```

Qué debes ver:

| Comando | Resultado correcto |
|---|---|
| `pruebas_almacen_sqlite.py` | Una lista de pruebas con `ok` y al final `Ran 19 tests` y `OK` |
| `probar_demo.py` | 4 líneas que empiezan por `OK:` |
| `pruebas_chatbot.py` | 9 líneas que empiezan por `OK:`; la última dice `OK: chatbot completo` |

Si aparece la palabra `Traceback` o `AssertionError`, algo está mal: copia el mensaje completo antes de seguir.

---

## 6. Encender el chatbot

Necesitas **dos terminales de PowerShell abiertas al mismo tiempo**, las dos dentro de la carpeta del proyecto (sección 3.1). Una ejecuta la API y la otra la pantalla. **No cierres ninguna mientras uses el chatbot.**

### 6.1 Terminal 1: la API

```powershell
.\.venv\Scripts\python.exe -m uvicorn main:app --reload --port 8011
```

Cuando esté lista verás líneas como:

```
INFO:     Uvicorn running on http://127.0.0.1:8011 (Press CTRL+C to quit)
INFO:     Application startup complete.
```

Comprueba en el navegador:

- **http://127.0.0.1:8011/docs** muestra la documentación de la API.
- **http://127.0.0.1:8011/reservas** muestra las reservas guardadas (al principio, `[]`).

Aquí se crea el archivo `reservas.db` si todavía no existe.

### 6.2 Terminal 2: la pantalla (Gradio)

Abre una segunda ventana de PowerShell, entra a la misma carpeta y ejecuta, en este orden:

```powershell
$env:CHATBOT_API_URL = "http://127.0.0.1:8011"
$env:GROQ_MODEL = "openai/gpt-oss-120b"
$claveGroqClase = Read-Host "API key de Groq" -AsSecureString
$env:GROQ_API_KEY = [System.Net.NetworkCredential]::new('', $claveGroqClase).Password
.\.venv\Scripts\python.exe app_gradio.py
```

- Al ejecutar `Read-Host`, PowerShell te pide la clave. **Pégala y pulsa Enter**: no verás nada en pantalla mientras la pegas, es normal.
- Cuando todo está bien, la terminal muestra algo como `Running on local URL:  http://127.0.0.1:7860`.

**Importante sobre estas variables:**

- Solo existen en **esa ventana** de PowerShell. Si la cierras, hay que repetir los cinco comandos.
- Solo se leen **al arrancar** `app_gradio.py`. Si cambias una, cierra Gradio con `Ctrl+C` y vuelve a ejecutarlo.

### 6.3 Abrir el chatbot

En el navegador abre **http://127.0.0.1:7860**. Verás el título *Chatbot del equipo*.

---

## 7. La pantalla, botón por botón

| Elemento | Qué hace |
|---|---|
| **Conversación** | Muestra lo que escribes y lo que responde el chatbot |
| **Tu mensaje** | Donde escribes. Se envía con **Enter** o con el botón **Enviar** |
| Línea de estado (debajo del cuadro) | *«Listo.»* = puedes escribir. *«Revisa el resumen y confirma o descarta.»* = hay una operación esperando tu decisión |
| **Enviar** | Envía tu mensaje |
| **Confirmar operación** | Ejecuta la operación que el chatbot te mostró en el resumen (reservar, modificar o cancelar). Es lo único que escribe en la base de datos |
| **Descartar solicitud** | Olvida la operación propuesta sin ejecutar nada |
| **Reiniciar conversación** | Borra la pantalla y **la memoria** de la conversación. Las reservas ya guardadas **no** se borran |
| **Revisar historial del laboratorio** | Panel desplegable con *«Mensajes para Groq»*: exactamente lo que se envía al modelo, útil para entender qué recuerda el chatbot |

### Cómo se hace una operación que cambia datos

1. Escribes lo que quieres (por ejemplo, reservar).
2. El chatbot te pide lo que falte y, cuando tiene todo, muestra un **resumen** (*«Revisa tu solicitud…»*). **Todavía no se guardó nada.**
3. Pulsas **Confirmar operación** (se guarda) o **Descartar solicitud** (no se guarda).
4. El chatbot responde con el resultado, por ejemplo *«Cita registrada ✅»* con el **código de la cita**.

Reglas de la pantalla:

- Mientras hay una operación pendiente **no puedes enviar otro mensaje**: primero confirma o descarta.
- Después de **Confirmar** la línea de estado dice *«Operación respondida por FastAPI. Revisa el resultado.»* Eso **no significa que haya salido bien**: puede ser un aviso, por ejemplo que el horario se ocupó justo antes. Lee siempre el mensaje del chat.

---

## 8. Cómo escribirle al chatbot

### 8.1 Principios generales

1. **Escribe natural.** No hace falta ningún formato especial. «Quiero una cita de consulta general para mi perro Firulais» funciona.
2. **Puedes dar todo junto o por partes.** Cuando falte algo, el chatbot lo pregunta, y puedes contestar con **una sola palabra** (por ejemplo, solo el nombre de la mascota).
3. **No repitas lo que ya dijiste.** Recuerda tu nombre, el de tu mascota, el servicio, la fecha y la hora mientras no cierres o reinicies la conversación.
4. **Lee la línea «Llevo: …».** Cada vez que el chatbot te hace una pregunta, empieza resumiendo lo que ya entendió, por ejemplo: `Llevo: Vacunación · mascota Princesa · lunes 19 de octubre de 2026.` Si algo está mal ahí, corrígelo en tu siguiente mensaje.
5. **Una cosa a la vez** cuando pidas operaciones distintas. No pidas «reserva una cita y cancela la otra» en el mismo mensaje.
6. **Cuando el chatbot no te entienda, sé más explícito.** Escribe la fecha completa, la hora con dos puntos (`10:30`) y el nombre completo del servicio.

### 8.2 Los servicios y cómo nombrarlos

**No tienes que escribir códigos internos como `consulta_general`.** El chatbot entiende mayúsculas, tildes y espacios, y varias formas de nombrar cada servicio:

| Servicio | Duración | Precio (COP) | Formas que entiende (ejemplos) |
|---|---|---|---|
| Consulta general | 30 min | $60.000 | «consulta general», «Consulta», «chequeo», «revisión» |
| Vacunación | 20 min | $45.000 | «vacunación», «vacuna», «vacunas», «vacunar» |
| Desparasitación | 20 min | $35.000 | «desparasitación», «desparasitar», «desparasitante» |
| Peluquería y baño | 60 min | $55.000 | «peluquería y baño», «peluquería», «baño», «bañar» |
| Cirugía menor | 90 min | $280.000 | «cirugía menor», «cirugía», «operación» |

Detalles útiles:

- Si en un mismo mensaje nombras **dos servicios** («vacunación y desparasitación»), el chatbot **no adivina**: te pregunta cuál quieres. Pide un servicio por cita.
- La palabra «consultar» (ver una cita) no se confunde con el servicio «consulta general».
- Si un nombre no se reconoce, escríbelo tal como aparece en la primera columna de la tabla.

### 8.3 Fechas

Estas formas funcionan:

| Cómo la escribes | Ejemplo |
|---|---|
| Año-mes-día (**la más segura**) | `2030-10-14` |
| Día/mes/año | `14/10/2030` o `14-10-2030` |
| Relativa | «mañana», «el viernes», «el próximo lunes» |

- Las fechas relativas las interpreta el modelo usando la fecha de hoy. Normalmente acierta, pero **si el chatbot entiende un día distinto al que querías, escribe la fecha completa** (`2030-10-14`).
- Fechas que ya pasaron se rechazan. El día va antes que el mes (`14/10`, no `10/14`).

### 8.4 Horas

- Escríbelas como **`10:30`** (24 horas) o «4 pm». Con dos puntos nunca hay ambigüedad.
- Las horas son de **30 en 30 minutos**: `09:00`, `09:30`, `10:00`… No existe `09:15`.
- Evita «en la tarde» o «a las 10» sin más: el chatbot necesita una hora exacta.

### 8.5 El código de la cita

Al confirmar una reserva recibes un código como **`AB-1A2B3C4D5E6F`** (`AB-` más 12 caracteres). Úsalo para consultar, modificar o cancelar.

- Cópialo y pégalo: no lo retipees.
- **También puedes decir «mi cita»** («cancela mi cita», «¿a qué hora es mi cita?»): el chatbot usa la **última cita de la que se habló en esta conversación**. Si reinicias la conversación, esa memoria se pierde y tendrás que dar el código.

### 8.6 Qué escribir para cada cosa

**Preguntar por los servicios**

| Escribe | Obtienes |
|---|---|
| «¿Qué servicios tienen?» | El catálogo completo, la ubicación y los horarios de atención |
| «¿Cuánto cuesta la vacunación?» | Solo ese servicio: `Vacunación: $45.000 COP, 20 minutos` |
| «¿Cuál es el horario?» | El catálogo completo con los horarios (el chatbot no muestra los horarios solos) |

**Ver qué horas hay libres** (necesita servicio y fecha; si falta uno, lo pregunta)

- «¿Qué horas hay libres para vacunación el 2030-10-14?»
- «Disponibilidad de peluquería el próximo lunes»

**Reservar** (sección 9 tiene un ejemplo completo)

- Todo en un mensaje: «Quiero una vacunación para mi perrita Princesa el 2030-10-14 a las 10:30, a nombre de Laura».
- Por partes: «Quiero una cita» → servicio → mascota → fecha → hora → nombre.

**Consultar una cita**

| Escribe | Obtienes |
|---|---|
| «Muéstrame mi cita» o «Consulta la cita AB-…» | La cita completa |
| «¿A qué hora es mi cita?» | Solo la hora |
| «¿Cuánto cuesta mi cita?», «¿En qué estado está?» | Solo ese dato |

**Modificar una cita** (se puede cambiar fecha, hora, servicio, cliente o mascota)

- «Cámbiala para las 11:00»
- «Cambia mi cita al 2030-10-15 a las 09:00»
- «Cámbiala a peluquería»
- «Cambia el nombre de la mascota a Toby» (**di qué dato cambia**: no escribas solo «Toby»)

El chatbot comprueba la disponibilidad **antes** de pedir confirmación. Si el nuevo horario está ocupado, te lo dice, muestra los libres y **tu cita queda como estaba**. El resumen muestra el antes y el después (`10:30 → 11:00`).

**Cancelar una cita**

- «Cancela mi cita» o «Cancela la cita AB-…»
- Muestra el resumen y espera tu confirmación. Al cancelar, el horario **vuelve a quedar libre**. Las citas canceladas no se borran: quedan en la base con estado `cancelada`.

**Otros temas**

Si preguntas algo ajeno a la veterinaria («explícame una integral»), responde amablemente que solo puede ayudar con servicios y citas.

---

## 9. Guion de prueba completo, paso a paso

Sigue esta conversación en orden. Si hoy es posterior a la fecha de los ejemplos, usa una fecha futura de lunes a viernes.

| # | Tú haces | El chatbot responde (resumen) |
|---|---|---|
| 1 | Escribes: `¿Cuánto cuesta una vacunación?` | `Vacunación: $45.000 COP, 20 minutos` (solo ese servicio) |
| 2 | `Quiero una vacunación para mi perrita Princesa` | `Llevo: Vacunación · mascota Princesa.` y pregunta la fecha |
| 3 | `el próximo lunes` | Lista los **horarios libres** y pregunta la hora |
| 4 | `a las 10:30` | Pregunta *«¿A nombre de quién registro la cita?»* |
| 5 | `Laura` | Muestra el resumen: Vacunación, Princesa, Laura, fecha, `10:30 a 10:50`, $45.000. **Aún no se guardó nada** |
| 6 | Pulsas **Confirmar operación** | `Cita registrada ✅` con el **código `AB-…`** |
| 7 | `¿A qué hora es mi cita?` | `La hora de tu cita es 10:30. Código: AB-…` (solo la hora) |
| 8 | `Cámbiala para las 11:00` | Resumen del cambio `10:30 → 11:00` |
| 9 | Pulsas **Confirmar operación** | `Cita modificada ✅` |
| 10 | `Cancela mi cita` | Resumen: *«Vas a cancelar esta cita…»* |
| 11 | Pulsas **Descartar solicitud** | `Solicitud descartada…` (la cita sigue activa) |
| 12 | `Cancela mi cita` y luego **Confirmar operación** | `Cita cancelada. El horario quedó libre.` |
| 13 | `¿Qué horas hay libres para vacunación el próximo lunes?` | Ya aparecen de nuevo `10:30` y `11:00` |
| 14 | `Ahora una desparasitación el martes a las 9:00` | Resumen con **Princesa y Laura ya puestos** (memoria): no vuelve a preguntarlos |
| 15 | Pulsas **Descartar solicitud** | No se guarda nada |

Para comprobar lo guardado en cada momento, abre **http://127.0.0.1:8011/reservas** (sección 12).

**Probar un cruce de horarios** (dos citas que se pisan):

1. Reserva una **peluquería** el lunes a las **10:00** (dura 60 min: ocupa 10:00 a 11:00) y confirma.
2. Pide una **consulta general** el mismo lunes a las **10:30**. El chatbot responde que esa hora no está disponible, muestra los horarios libres y **no pide confirmación**.
3. Pide la consulta a las **11:00**: se acepta, porque empieza justo cuando termina la peluquería.

---

## 10. Frases que dan problemas y cómo escribirlas mejor

| En vez de escribir… | Escribe… | Por qué |
|---|---|---|
| «Quiero reservar para la próxima semana» | «Quiero reservar el lunes 2030-10-14» | «La próxima semana» no es un día. Hace falta una fecha concreta |
| «A las 10» | `10:00` (o «10 am») | «10» sin minutos ni am/pm puede entenderse mal |
| «Mañana en la tarde» | `a las 15:00` | Necesita una hora exacta |
| «Vacunación y desparasitación» (en una misma cita) | Primero una, luego otra | Cada cita es de un solo servicio; si pones dos, te pregunta cuál |
| «Cámbiala» (sin decir qué) | «Cámbiala para las 11:00» | Si no dices qué cambia, te muestra la cita y pregunta qué quieres cambiar |
| «Toby» (para cambiar la mascota de una cita existente) | «Cambia el nombre de la mascota a Toby» | Al modificar, una palabra suelta no dice qué dato cambia. (Al **reservar**, una palabra suelta sí sirve para contestar una pregunta) |
| «Cancela la cita de Firulais» | «Cancela mi cita» o «Cancela la cita AB-…» | La búsqueda es por código, no por nombre de mascota |
| «Cancela mi cita» **después de reiniciar** | «Cancela la cita AB-…» | Al reiniciar se pierde la memoria de «mi cita» |
| Escribir con el servicio entre comillas o con guion bajo | Como lo dirías hablando | Ya no hace falta `consulta_general`: sirve «consulta general» |
| Intentar escribir con una operación pendiente | Pulsar **Confirmar** o **Descartar** | Con un resumen pendiente la pantalla no deja enviar otro mensaje |
| Pegar tu API key en el chat | **Nunca** | Quedaría en el historial y en pantalla (sección 15) |

**Cuando el chatbot repite la misma pregunta:** no entendió tu respuesta. Haz esto, en orden:

1. Lee la línea `Llevo: …` para ver qué entendió.
2. Responde de forma más explícita: «mi mascota se llama Arturo», «el 2030-10-14», «a las 10:30», «consulta general».
3. Si sigue igual, abre **Revisar historial del laboratorio** y mira el último mensaje del asistente (`"servicio"`, `"fecha"`, `"hora"`…): ahí se ve el plan que armó.

---

## 11. Reglas del negocio (por qué a veces se rechaza una hora)

- **Horario de atención:** lunes a viernes **08:00–18:00**, sábado **08:00–13:00**, **domingo cerrado**.
- **Pasos de 30 minutos:** las citas empiezan en `:00` o `:30`.
- **La atención debe terminar dentro del horario.** Por eso el último inicio depende de la duración:

  | Servicio | Primera hora | Última hora (lun–vie) | Última hora (sábado) |
  |---|---|---|---|
  | Consulta general (30 min) | 08:00 | 17:30 | 12:30 |
  | Vacunación (20 min) | 08:00 | 17:30 | 12:30 |
  | Desparasitación (20 min) | 08:00 | 17:30 | 12:30 |
  | Peluquería y baño (60 min) | 08:00 | 17:00 | 12:00 |
  | Cirugía menor (90 min) | 08:00 | 16:30 | 11:30 |

- **Una sola agenda:** dos citas **no pueden cruzarse**, aunque sean de servicios distintos. Una cita que empieza justo cuando otra termina **sí** se acepta.
- **No se reserva en el pasado:** ni fechas que ya pasaron, ni horas de hoy que ya empezaron.
- **Doble comprobación:** el chatbot revisa la disponibilidad antes de mostrarte el resumen, y la base de datos vuelve a revisarla al confirmar. Si alguien ocupó el horario justo en medio, verás *«No se pudo completar… No se guardó ningún cambio»* y podrás elegir otra hora.

---

## 12. Ver los datos guardados en SQLite

Las reservas están en el archivo **`reservas.db`**, dentro de la carpeta del proyecto.

**Opción 1: el navegador** (con la API encendida)

Abre **http://127.0.0.1:8011/reservas**. Verás todas las reservas en formato JSON, incluidas las canceladas.

**Opción 2: PowerShell, sin instalar nada**

```powershell
.\.venv\Scripts\python.exe -c "import sqlite3; con = sqlite3.connect('reservas.db'); [print(f) for f in con.execute('SELECT codigo, cliente, mascota, servicio, fecha, hora, estado FROM reservas ORDER BY fecha, hora')]"
```

Una reserva se ve así:

```
('AB-1A2B3C4D5E6F', 'Laura', 'Princesa', 'vacunacion', '2030-10-14', '10:30', 'activa')
```

Para ver solo las activas, cambia `ORDER BY fecha, hora` por `WHERE estado='activa' ORDER BY fecha, hora`.

**Opción 3: herramienta visual**

Instala **DB Browser for SQLite** (gratis, sqlitebrowser.org), pulsa **Open Database** y elige `reservas.db`. En **Browse Data** ves la tabla `reservas`. Es la mejor opción para las capturas de la bitácora.

**Columnas de la tabla `reservas`:** `codigo`, `cliente`, `mascota`, `servicio`, `fecha`, `hora`, `duracion_minutos`, `estado` (`activa` o `cancelada`).

Cuidados:

- Solo **mira**: no edites datos a mano con la API encendida.
- **No borres `reservas.db`** mientras la API corre. Si lo borras con todo apagado, se crea uno vacío en el próximo arranque.

---

## 13. Apagar, volver a encender y qué se conserva

**Apagar:** en cada terminal pulsa **`Ctrl+C`**.

**Volver a encender:** repite la sección 6. Recuerda que las variables de PowerShell (`GROQ_API_KEY`, etc.) se pierden al cerrar la ventana de la Terminal 2.

| Qué | ¿Se conserva? |
|---|---|
| Las reservas (en `reservas.db`) | **Sí**, aunque apagues todo |
| La conversación en pantalla y la memoria del chatbot | **No** si pulsas *Reiniciar conversación*, recargas la página o reinicias Gradio |
| Cada ventana del navegador | Tiene **su propia** conversación y memoria (una ventana privada es una conversación nueva) |

---

## 14. Solución de problemas

### Mensajes de la pantalla

| Mensaje | Qué significa y qué hacer |
|---|---|
| *«Escribe una solicitud antes de enviarla.»* | El cuadro está vacío |
| *«Confirma o descarta la solicitud pendiente primero.»* | Hay un resumen esperando: pulsa **Confirmar operación** o **Descartar solicitud** |
| *«Configura GROQ_API_KEY y GROQ_MODEL e inicia de nuevo.»* | Faltan variables en la Terminal 2. Ciérrala con `Ctrl+C`, repite la sección 6.2 y abre Gradio otra vez |
| *«Error HTTP 400. Revisa Groq o FastAPI.»* (o 401, 404, 429) | Casi siempre viene de Groq. **Mira la Terminal 2**: hay una línea que empieza por `[Groq]` con el motivo real (ver tabla siguiente) |
| *«No pude conectar con Groq o FastAPI.»* | Sin internet, o la Terminal 1 (API) está apagada o en otro puerto. Revisa que siga abierta y muestre *Application startup complete* |
| *«La respuesta no tiene el formato esperado.»* | El modelo devolvió algo que no se pudo leer. Vuelve a enviar el mensaje. Si se repite, revisa la línea `[Groq]` de la Terminal 2 |
| *«FastAPI respondió con HTTP … Revisa el detalle en /docs.»* | Falló la API al confirmar. Mira la Terminal 1 y consulta la reserva antes de repetir la operación |
| *«No recibí respuesta. Consulta la reserva antes de repetir la operación.»* | Se agotó el tiempo de espera. Revisa en `/reservas` si la operación llegó a guardarse antes de repetirla |
| *«No hay una operación pendiente.»* / *«No hay una solicitud pendiente para descartar.»* | Pulsaste Confirmar o Descartar sin que hubiera un resumen |

### Códigos de error de Groq (línea `[Groq]` en la Terminal 2)

| Código | Significado | Solución |
|---|---|---|
| `model_decommissioned` o modelo no encontrado | El modelo ya no existe | Cambia `GROQ_MODEL` por un modelo vigente y reinicia Gradio |
| `invalid_api_key` (HTTP 401) | La clave está mal escrita o fue revocada | Crea otra en console.groq.com y vuelve a ponerla |
| HTTP 429 | Demasiadas peticiones en poco tiempo | Espera un minuto y reintenta |
| `finish_reason=length` | La respuesta del modelo salió cortada | Avísale a quien mantiene el proyecto (límite `max_completion_tokens` en `consulta_llm.py`) |

### Problemas de instalación y arranque

| Problema | Solución |
|---|---|
| `.\.venv\Scripts\python.exe` no se reconoce | No existe `.venv` en esta carpeta. Haz la sección 3.2 y 3.3 |
| `python` no se reconoce | Python no está instalado o no está en el PATH (sección 2) |
| `ModuleNotFoundError: No module named 'gradio'` (o `fastapi`) | Falta instalar paquetes: sección 3.3. Verifica con la 3.4 |
| `[Errno 10048]` / el puerto 8011 o 7860 ya está en uso | Hay otra copia corriendo. Ciérrala con `Ctrl+C`, o usa otro puerto: arranca la API con `--port 8012` y pon `$env:CHATBOT_API_URL = "http://127.0.0.1:8012"` |
| La página 7860 no abre | La Terminal 2 no terminó de arrancar o mostró un error; léelo |
| No aparece `reservas.db` | Enciende la API (Terminal 1) desde esta carpeta |
| Cambié `main.py` y no veo el cambio | La API se recarga sola con `--reload`; si no, ciérrala con `Ctrl+C` y vuelve a encenderla |

### El chatbot hace algo raro

| Síntoma | Qué revisar |
|---|---|
| Repite una pregunta que ya contestaste | Sección 10: lee `Llevo: …` y responde de forma más explícita |
| Entiende otro día que el que dijiste | Escribe la fecha completa: `2030-10-14` |
| Dice que un horario no está disponible y tú lo ves libre | Mira la duración del servicio: puede cruzarse con otra cita (sección 11) |
| «Mi cita» no funciona | Reiniciaste la conversación: usa el código `AB-…` |
| Después de confirmar, no encuentras la cita | Mira `/reservas`; si el mensaje del chat explicó un fallo, no se guardó |

---

## 15. Seguridad de la clave

- La API key es **personal**: quien la tenga puede gastar tu cuota de Groq.
- **No la escribas** en ningún archivo, no la pegues en el chat ni la dejes visible en capturas de pantalla o en la bitácora.
- Por eso se pide con `Read-Host -AsSecureString`: no queda en el historial de comandos ni se ve al escribirla.
- Si se te escapa en algún sitio, **bórrala** en console.groq.com (API Keys) y crea otra.
- La clave no se guarda en el historial de la conversación ni aparece en pantalla (las pruebas automáticas lo comprueban). La base de datos solo guarda reservas.

---

**Más información técnica:** `LEEME_Laboratorio_08_09.md` (cambios al almacén, rutas de la API y las 11 pruebas del laboratorio) y `Bitacora_Laboratorio_08_09.md` (plantilla de entrega).
