"""Pruebas del chatbot completo sin Groq real y sin internet.

    .\\.venv\\Scripts\\python.exe pruebas_chatbot.py

- Un servidor local de mentira hace de Groq: en cada turno devuelve el plan que le indica la prueba. Así se
  comprueba el código real que arma la petición, la envía y lee la respuesta.
- La API es main.py con una base SQLite temporal (no toca reservas.db).
- La pantalla es app_gradio.py: se llaman sus funciones enviar(), confirmar(), descartar() y reiniciar().
Con un modelo real el texto de cada plan lo decide Groq; lo que se prueba aquí es todo lo demás: la memoria,
las validaciones, la disponibilidad y las confirmaciones.
"""

import json
import os
import re
import threading
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import HTTPError, URLError

os.environ["GROQ_API_KEY"] = "clave-de-prueba-123"  # app_gradio.py lee esto al importarse
os.environ["GROQ_MODEL"] = "modelo-de-prueba"

from fastapi.testclient import TestClient

import app_gradio
import chatbot_memoria
import consulta_llm
import main

CLAVE = os.environ["GROQ_API_KEY"]


class GroqFalso(BaseHTTPRequestHandler):
    respuestas = []   # cola: un plan (dict), un código HTTP de error (int) o un texto que no es JSON (str)
    peticiones = []   # lo que llegó: ruta, cabeceras y cuerpo

    def do_POST(self):
        cuerpo = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        GroqFalso.peticiones.append({"ruta": self.path, "cabeceras": dict(self.headers), "cuerpo": cuerpo})
        siguiente = GroqFalso.respuestas.pop(0)
        if isinstance(siguiente, int):
            salida, estado = b'{"error": "fallo de prueba"}', siguiente
        else:
            contenido = siguiente if isinstance(siguiente, str) else json.dumps(siguiente)
            salida = json.dumps({"choices": [{"message": {"role": "assistant", "content": contenido}}]}).encode()
            estado = 200
        self.send_response(estado)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(salida)))
        self.end_headers()
        self.wfile.write(salida)

    def log_message(self, *args):
        pass


class Sesion:
    """Una ventana del navegador: su estado lo guarda Gradio; aquí se guarda en este objeto."""

    def __init__(self):
        self.estado = app_gradio.nuevo_estado()

    def decir(self, texto, plan):
        """La persona escribe `texto` y el «modelo» responde con `plan`. Devuelve lo que ve en pantalla."""
        GroqFalso.respuestas.append(plan)
        self.estado = app_gradio.enviar(texto, self.estado)[1]
        return self.pantalla()

    def pantalla(self):
        return self.estado["pantalla"][-1]["content"]

    def confirmar(self):
        self.estado = app_gradio.confirmar(self.estado)[1]
        return self.pantalla()

    def descartar(self):
        self.estado = app_gradio.descartar(self.estado)[1]
        return self.pantalla()

    def error_al_decir(self, texto, plan):
        GroqFalso.respuestas.append(plan)
        try:
            app_gradio.enviar(texto, self.estado)
        except app_gradio.gr.Error as error:
            return str(getattr(error, "message", error))
        raise AssertionError("Se esperaba un error")


def filas(estado=None):
    return [f for f in main.agenda.listar() if estado is None or f["estado"] == estado]


def probar():
    servidor = ThreadingHTTPServer(("127.0.0.1", 0), GroqFalso)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    os.environ["GROQ_API_URL"] = f"http://127.0.0.1:{servidor.server_port}/openai/v1/chat/completions"

    hoy = datetime.now(main.ZONA).date()
    lunes = hoy + timedelta(days=(0 - hoy.weekday()) % 7)
    if (lunes - hoy).days < 2:
        lunes += timedelta(days=7)
    martes = lunes + timedelta(days=1)
    LUNES, MARTES = lunes.isoformat(), martes.isoformat()

    original = main.agenda
    api_original = consulta_llm.llamar_api
    with TemporaryDirectory() as carpeta, TestClient(main.app) as api:
        main.agenda = main.crear_agenda(Path(carpeta) / "reservas.db")

        def llamar_api(metodo, ruta, cuerpo=None, consulta=None):
            """Hace lo mismo que consulta_llm.llamar_api, pero contra main.py sin abrir un puerto."""
            enviar = {"GET": api.get, "POST": api.post, "PUT": api.put, "DELETE": api.delete}[metodo]
            argumentos = {}
            if cuerpo is not None:
                argumentos["json"] = cuerpo
            if consulta:
                argumentos["params"] = consulta
            respuesta = enviar(ruta, **argumentos)
            if respuesta.status_code >= 500:
                raise HTTPError(ruta, respuesta.status_code, "error del servidor", {}, None)
            return respuesta.status_code, respuesta.json()

        consulta_llm.llamar_api = chatbot_memoria.llamar_api = llamar_api
        try:
            # ---- 1. Una reserva completa en varios turnos, con memoria -------------------------------------
            s = Sesion()
            texto = s.decir("Quiero vacunar a mi perrita Princesa",
                            {"accion": "reservar", "servicio": "vacunacion", "mascota": "Princesa"})
            assert "fecha" in texto.lower() and "Princesa" in texto and "Llevo:" in texto, texto
            # El modelo se descuida y no repite servicio ni mascota: Python los recuerda.
            texto = s.decir("el lunes", {"accion": "reservar", "fecha": LUNES})
            assert "Vacunación" in texto and "Princesa" in texto and "Horarios libres" in texto, texto
            texto = s.decir("a las 10:30 am", {"accion": "reservar", "hora": "10:30"})
            assert "nombre de quién" in texto, texto
            # Respuesta de una sola palabra, mal clasificada por el modelo y con el mismo nombre en dos campos.
            texto = s.decir("Laura", {"accion": "conversar", "respuesta": "Hola", "cliente": "Laura", "mascota": "Laura"})
            pendiente = s.estado["pendiente"]
            assert pendiente == {"accion": "reservar", "cliente": "Laura", "mascota": "Princesa",
                                 "servicio": "vacunacion", "fecha": LUNES, "hora": "10:30"}, pendiente
            assert "Revisa tu solicitud" in texto and "10:30 a 10:50" in texto and "$45.000 COP" in texto, texto
            assert filas() == []  # sin Confirmar no se guarda nada
            try:  # con una operación pendiente, la pantalla no deja enviar otro mensaje
                app_gradio.enviar("otra cosa", s.estado)
                raise AssertionError("Debía pedir confirmar o descartar primero")
            except app_gradio.gr.Error as error:
                assert "pendiente" in str(getattr(error, "message", error))
            texto = s.confirmar()
            codigo = re.search(r"AB-[0-9A-F]{12}", texto).group(0)
            assert "Cita registrada" in texto and filas()[0]["codigo"] == codigo and filas()[0]["mascota"] == "Princesa"
            assert s.estado["pendiente"] is None

            # ---- 2. Consultar sin repetir el código, y mostrar solo lo que se pide --------------------------
            texto = s.decir("muéstrame mi cita", {"accion": "consultar"})
            assert codigo in texto and "Hora: 10:30" in texto, texto
            texto = s.decir("¿a qué hora es?", {"accion": "consultar", "campo": "hora"})
            assert texto == f"La hora de tu cita es 10:30. Código: {codigo}", texto

            # ---- 3. Modificar con comprobación de disponibilidad, y descartar --------------------------------
            texto = s.decir("cámbiala para las 11:00", {"accion": "modificar", "hora": "11:00"})
            assert "10:30 → **11:00**" in texto and s.estado["pendiente"]["accion"] == "modificar", texto
            assert "Cita modificada" in s.confirmar() and filas()[0]["hora"] == "11:00"
            s.decir("cancela mi cita", {"accion": "cancelar"})
            assert "Solicitud descartada" in s.descartar() and filas()[0]["estado"] == "activa"

            # ---- 4. Cancelar libera el horario ----------------------------------------------------------------
            s.decir("cancela mi cita", {"accion": "cancelar"})
            assert "Cita cancelada" in s.confirmar() and filas()[0]["estado"] == "cancelada"
            texto = s.decir("¿qué horas hay libres para vacunar el lunes?",
                            {"accion": "disponibilidad", "servicio": "vacunacion", "fecha": LUNES})
            assert "11:00" in texto and "10:30" in texto, texto
            texto = s.decir("cancela mi cita", {"accion": "cancelar"})
            assert "ya estaba cancelada" in texto, texto

            # ---- 5. La sesión recuerda a la persona y a su mascota en una reserva nueva ------------------------
            texto = s.decir("ahora una desparasitación el martes a las 9",
                            {"accion": "reservar", "servicio": "desparasitacion", "fecha": MARTES, "hora": "09:00"})
            assert "Laura" in texto and "Princesa" in texto and s.estado["pendiente"]["accion"] == "reservar", texto
            s.descartar()
            assert len(filas("activa")) == 0
            print("OK: reserva en varios turnos, memoria del cliente y la mascota, consulta, cambio y cancelación.")

            # ---- 6. Cruces de intervalos: lo decide la API, no el modelo -----------------------------------------
            pelu = {"accion": "reservar", "servicio": "peluqueria", "mascota": "Rocky", "cliente": "Andrés",
                    "fecha": LUNES, "hora": "10:00"}
            a = Sesion()
            a.decir("peluquería a las 10", pelu)
            a.confirmar()
            codigo_pelu = filas("activa")[0]["codigo"]
            b = Sesion()  # otra ventana: su conversación es independiente
            texto = b.decir("consulta a las 10:30", {"accion": "reservar", "servicio": "consulta_general",
                                                     "mascota": "Luna", "cliente": "Sara", "fecha": LUNES, "hora": "10:30"})
            assert "no están disponibles" in texto and b.estado["pendiente"] is None, texto
            libres = texto.split("Horarios libres")[1]
            assert "10:00" not in libres and "10:30" not in libres and "11:00" in libres, texto
            assert len(filas("activa")) == 1
            texto = b.decir("mejor a las 11:00", {"accion": "reservar", "hora": "11:00"})  # el modelo solo trae la hora
            assert b.estado["pendiente"]["hora"] == "11:00" and b.estado["pendiente"]["cliente"] == "Sara", texto
            b.confirmar()
            codigo_consulta = [f for f in filas("activa") if f["servicio"] == "consulta_general"][0]["codigo"]
            # Mover la consulta a un horario ocupado: se avisa y la cita no cambia.
            texto = b.decir("pásala a las 10:30", {"accion": "modificar", "codigo": codigo_consulta, "hora": "10:30"})
            assert "no está disponible" in texto and "sigue igual (11:00)" in texto and b.estado["pendiente"] is None, texto
            assert main.agenda.consultar(codigo_consulta)["hora"] == "11:00"
            # Mover la peluquería 30 minutos antes: se cruza con su propio horario, pero eso no cuenta.
            texto = a.decir("adelántala a las 9:30", {"accion": "modificar", "codigo": codigo_pelu, "hora": "09:30"})
            assert a.estado["pendiente"]["hora"] == "09:30", texto
            assert "Cita modificada" in a.confirmar() and main.agenda.consultar(codigo_pelu)["hora"] == "09:30"
            print("OK: cruces de intervalos, ventanas independientes y modificación sin chocar consigo misma.")

            # ---- 7. Un horario ocupado entre el resumen y el botón Confirmar -----------------------------------------
            c = Sesion()
            c.decir("vacunación el martes a las 15", {"accion": "reservar", "servicio": "vacunacion", "mascota": "Toby",
                                                       "cliente": "Marta", "fecha": MARTES, "hora": "15:00"})
            main.agenda.crear("Otra persona", "vacunacion", MARTES, "15:00", "Max")  # alguien llega primero
            texto = c.confirmar()
            assert "No se pudo completar" in texto and "No se guardó ningún cambio" in texto, texto
            assert c.estado["pendiente"] is None and len([f for f in filas("activa") if f["fecha"] == MARTES]) == 1
            print("OK: si el horario se ocupa antes de confirmar, no se guarda nada y se explica.")

            # ---- 8. Respuestas sueltas y temas ajenos ---------------------------------------------------------------
            d = Sesion()
            d.decir("quiero consulta", {"accion": "reservar", "servicio": "consulta_general"})
            texto = d.decir("Arturo", {"accion": "conversar", "respuesta": "¿En qué te ayudo?"})
            assert d.estado["historial"][-1]["content"].count('"mascota": "Arturo"') == 1 and "fecha" in texto.lower(), texto
            texto = d.decir("como me llamo", {"accion": "conversar", "respuesta": "No tengo ese dato todavía."})
            assert texto == "No tengo ese dato todavía." and chatbot_memoria.identidad(d.estado["historial"]) == {"mascota": "Arturo"}
            texto = d.decir("explícame una integral", {"accion": "conversar",
                                                       "respuesta": "Solo puedo ayudarte con servicios y citas."})
            assert "servicios y citas" in texto
            print("OK: respuestas sueltas de una palabra y preguntas fuera del tema.")

            # ---- 9. Información: solo lo que se pregunta ------------------------------------------------------------
            e = Sesion()
            texto = e.decir("¿cuánto cuesta vacunar?", {"accion": "servicios", "servicio": "vacunacion"})
            assert texto == "Vacunación: $45.000 COP, 20 minutos", texto
            texto = e.decir("¿qué servicios tienen?", {"accion": "servicios"})
            assert "Peluquería" in texto and "lunes a viernes 08:00–18:00" in texto and "sábado 08:00–13:00" in texto, texto
            print("OK: información limitada a lo que se pregunta.")

            # ---- 10. Lo que viaja a Groq y lo que no debe aparecer en ningún sitio -----------------------------------
            ultima = GroqFalso.peticiones[-1]
            cabeceras = {k.lower(): v for k, v in ultima["cabeceras"].items()}
            assert ultima["ruta"].endswith("/chat/completions") and cabeceras["authorization"] == "Bearer " + CLAVE
            assert cabeceras["user-agent"].startswith("AnimaBot") and ultima["cuerpo"]["model"] == "modelo-de-prueba"
            assert ultima["cuerpo"]["response_format"] == {"type": "json_object"} and ultima["cuerpo"]["temperature"] == 0
            mensajes = ultima["cuerpo"]["messages"]
            assert all(set(m) == {"role", "content"} for m in mensajes) and mensajes[0]["role"] == "system"
            assert datetime.now(main.ZONA).date().isoformat() in mensajes[0]["content"]  # el modelo sabe qué día es hoy
            # El modelo ve los planes anteriores y qué dato se le había pedido a la persona (esa es la memoria).
            assert any('"esperando": "mascota"' in m["content"] for p in GroqFalso.peticiones
                       for m in p["cuerpo"]["messages"] if m["role"] == "assistant")
            todo = json.dumps([s.estado, d.estado, a.estado, b.estado, c.estado, e.estado], ensure_ascii=False)
            assert CLAVE not in todo  # la clave nunca queda en el historial ni en pantalla
            largo = [{"role": "system", "content": "s"}] + [{"role": "user", "content": "x"}] * 90
            assert len(chatbot_memoria.recortar(largo)) == 41 and chatbot_memoria.recortar(largo)[0]["role"] == "system"
            print("OK: petición a Groq correcta, memoria visible para el modelo y clave fuera del historial.")

            # ---- 11. Reiniciar y fallos de Groq o de la API -------------------------------------------------------------
            n = len(filas())
            nueva = app_gradio.reiniciar()[1]
            assert len(nueva["historial"]) == 1 and nueva["pantalla"] == [] and len(filas()) == n  # las reservas siguen
            f = Sesion()
            f.decir("hola, soy Laura", {"accion": "conversar", "respuesta": "¡Hola, Laura!", "cliente": "Laura"})
            antes = json.dumps(f.estado)
            assert "Error HTTP 401" in f.error_al_decir("hola", 401)  # clave inválida
            assert "formato esperado" in f.error_al_decir("hola", "esto no es JSON")
            assert json.dumps(f.estado) == antes  # un turno fallido no ensucia el historial

            def api_caida(*args, **kwargs):
                raise URLError("sin conexión")
            consulta_llm.llamar_api = chatbot_memoria.llamar_api = api_caida
            assert "No pude conectar" in f.error_al_decir("¿qué servicios hay?", {"accion": "servicios"})
            assert json.dumps(f.estado) == antes
            try:
                consulta_llm.ejecutar({"accion": "reservar", "cliente": "X"})
                raise AssertionError("Una reserva no se ejecuta sin confirmar")
            except ValueError:
                pass
            print("OK: reinicio, errores de Groq y de la API sin perder el historial.")
        finally:
            consulta_llm.llamar_api = chatbot_memoria.llamar_api = api_original
            main.agenda = original
    servidor.shutdown()
    print("OK: chatbot completo (memoria, consultas, confirmaciones y errores).")


if __name__ == "__main__":
    probar()
