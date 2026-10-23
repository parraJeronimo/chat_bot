"""API de AnimaBot Veterinaria con las reservas guardadas en SQLite (Laboratorio 08–09). Usar datos ficticios.

Las reservas viven en reservas.db a través de AgendaSQLite: la comprobación del intervalo y el guardado
ocurren en una misma transacción, de modo que dos peticiones al mismo horario nunca se aceptan las dos.
Solo el estado de /chat (el puente de Flowise) vive en memoria.
"""

import json
import re
import sqlite3
from datetime import date
from pathlib import Path
from threading import RLock
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from almacen_sqlite import AgendaSQLite, ConflictoReserva, ReservaNoEncontrada

BASE = Path(__file__).resolve().parent
NEGOCIO = json.loads((BASE / "negocio.json").read_text(encoding="utf-8-sig"))
ZONA = ZoneInfo(NEGOCIO["zona_horaria"])
SERVICIOS = NEGOCIO["servicios"]
if NEGOCIO["capacidad"] != 1 or NEGOCIO["paso_minutos"] <= 0:
    raise ValueError("Este ejemplo admite capacidad 1 y un paso positivo.")
if any(s["duracion_minutos"] <= 0 or s["precio_cop"] < 0 for s in SERVICIOS.values()):
    raise ValueError("Revisar precios y duraciones del negocio.")


def crear_agenda(ruta):
    """Una agenda con el horario de negocio.json: lunes a viernes 08:00–18:00 y sábado 08:00–13:00."""
    return AgendaSQLite(ruta, SERVICIOS, horarios=NEGOCIO["horarios"], paso=NEGOCIO["paso_minutos"],
                        zona=ZONA, prefijo="AB-", largo_codigo=12)


# La ruta basada en __file__ deja reservas.db junto a este archivo aunque la terminal se abra en otra carpeta.
agenda = crear_agenda(BASE / "reservas.db")

# Solo protege SESIONES (el estado en memoria de /chat). Las reservas las protege SQLite.
LOCK = RLock()
SESIONES: dict[str, dict] = {}
app = FastAPI(title="AnimaBot · API de clase", version="2.0.0",
              description="Datos ficticios. API local sin autenticación; no publicar en Internet.")


class DatosReserva(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    cliente: str = Field(min_length=2, max_length=80)
    mascota: str = Field(min_length=1, max_length=60)
    servicio: str = Field(min_length=1, max_length=40)
    fecha: date
    hora: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")


class CrearReserva(DatosReserva):
    confirmado: Literal[True]


class ModificarReserva(BaseModel):
    """Cambios parciales sobre una reserva existente. Todo es opcional salvo la confirmación."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    cliente: str | None = Field(default=None, min_length=2, max_length=80)
    mascota: str | None = Field(default=None, min_length=1, max_length=60)
    servicio: str | None = Field(default=None, min_length=1, max_length=40)
    fecha: date | None = None
    hora: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    confirmado: Literal[True]


class Extraccion(BaseModel):
    """La interpretación del LLM es entrada no confiable: se valida antes de usarla."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    intencion: Literal["informacion", "reservar", "consultar", "cancelar", "modificar", "continuar", "fuera"] = "continuar"
    cliente: str | None = Field(default=None, min_length=2, max_length=80)
    mascota: str | None = Field(default=None, min_length=1, max_length=60)
    servicio: str | None = Field(default=None, max_length=40)
    fecha: date | None = None
    hora: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    codigo: str | None = Field(default=None, max_length=50)
    # Campo puntual que el cliente pregunta sobre una cita ya existente (por ejemplo, solo la hora).
    # "completo" o ausente significa responder con el resumen entero, como antes.
    campo: Literal["completo", "fecha", "hora", "servicio", "precio", "estado",
                    "cliente", "mascota", "duracion"] | None = None


class Mensaje(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str = Field(min_length=1, max_length=150)
    mensaje: str = Field(min_length=1, max_length=2000)
    datos: Extraccion = Field(default_factory=Extraccion)


def llamar_agenda(funcion, *args):
    """Convierte las excepciones del almacén en respuestas HTTP (equivale a responder() de main_sqlite_ejemplo.py).

    Se llama distinto porque en este archivo responder() ya existe: es la respuesta del chat.
    """
    try:
        return funcion(*args)
    except ReservaNoEncontrada as exc:
        raise HTTPException(404, "No existe una cita con ese código.") from exc
    except ConflictoReserva as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except sqlite3.Error as exc:
        raise HTTPException(503, "No se pudo usar la base de datos. No se confirmó la operación.") from exc


def servicio_valido(servicio):
    if servicio not in SERVICIOS:
        raise HTTPException(422, "Servicio desconocido. Opciones: " + ", ".join(SERVICIOS))
    return SERVICIOS[servicio]


def presentar(r):
    """SQLite no guarda el precio: se toma del catálogo para conservar la respuesta que ya usaban los clientes."""
    return {**r, "precio_cop": SERVICIOS.get(r["servicio"], {}).get("precio_cop", 0)}


def horarios_libres(fecha, servicio, excluir=""):
    """Horas libres para un servicio. `excluir` es el código de una reserva que se está modificando."""
    servicio_valido(servicio)
    return llamar_agenda(agenda.disponibilidad, fecha.isoformat(), servicio, excluir)["horas"]


@app.get("/servicios")
def servicios():
    return NEGOCIO


@app.get("/disponibilidad")
def disponibilidad(fecha: date, servicio: str, excluir: str = ""):
    """`excluir` (opcional) es el código de una cita que se quiere mover: su propio horario cuenta como libre."""
    servicio_valido(servicio)
    r = llamar_agenda(agenda.disponibilidad, fecha.isoformat(), servicio, excluir.strip().upper())
    return {"fecha": r["fecha"], "servicio": r["servicio"], "duracion_minutos": r["duracion_minutos"],
            "horarios": r["horas"]}


@app.get("/reservas")
def reservas():
    return [presentar(r) for r in llamar_agenda(agenda.listar)]


@app.post("/reservas", status_code=201)
def crear(datos: CrearReserva):
    servicio_valido(datos.servicio)
    return presentar(llamar_agenda(agenda.crear, datos.cliente, datos.servicio, datos.fecha.isoformat(),
                                   datos.hora, datos.mascota))


@app.get("/reservas/{codigo}")
def consultar(codigo: str):
    return presentar(llamar_agenda(agenda.consultar, codigo.strip().upper()))


@app.put("/reservas/{codigo}")
def modificar(codigo: str, cambios: ModificarReserva):
    """Cambia fecha, hora, servicio, cliente o mascota de una cita activa, validando disponibilidad."""
    if cambios.servicio:
        servicio_valido(cambios.servicio)
    fecha = cambios.fecha.isoformat() if cambios.fecha else None
    return presentar(llamar_agenda(agenda.modificar, codigo.strip().upper(), cambios.servicio, fecha,
                                   cambios.hora, cambios.cliente, cambios.mascota))


@app.delete("/reservas/{codigo}")
def cancelar(codigo: str, confirmado: bool = Query(False)):
    if not confirmado:
        raise HTTPException(422, "Se requiere confirmación para cancelar.")
    codigo = codigo.strip().upper()
    try:
        return presentar(llamar_agenda(agenda.cancelar, codigo))
    except HTTPException as exc:
        if exc.status_code != 409:
            raise
        # Cancelar una cita que ya estaba cancelada no es un error: se devuelve su estado actual.
        return presentar(llamar_agenda(agenda.consultar, codigo))


def resumen(r):
    return f"{r['cliente']} (mascota: {r['mascota']}): {r['servicio']}, {r['fecha']} a las {r['hora']}"


def pesos(valor):
    return f"${valor:,}".replace(",", ".") + " COP"


def dato_puntual(r, campo):
    """Texto con un único dato de la reserva, para cuando el cliente pide solo eso (no todo el resumen)."""
    textos = {
        "fecha": f"La fecha de tu cita es {r['fecha']}.",
        "hora": f"La hora de tu cita es {r['hora']}.",
        "servicio": f"El servicio reservado es {SERVICIOS[r['servicio']]['nombre']}.",
        "precio": f"El precio de tu cita es {pesos(r['precio_cop'])}.",
        "estado": f"El estado de tu cita es {r['estado']}.",
        "cliente": f"La cita está a nombre de {r['cliente']}.",
        "mascota": f"La mascota registrada es {r['mascota']}.",
        "duracion": f"La cita dura {r['duracion_minutos']} minutos.",
    }
    return textos.get(campo)


def responder(estado, texto):
    return {"respuesta": texto, "estado_sesion": estado.copy()}


@app.post("/chat")
def chat(entrada: Mensaje):
    """Puente de Flowise. El estado y la confirmación se controlan aquí, sin agentes."""
    with LOCK:
        estado = SESIONES.setdefault(entrada.session_id, {})
        mensaje = entrada.mensaje.strip().casefold()
        if mensaje == "/reset":
            estado.clear()
            return responder(estado, "Solicitud reiniciada. Las citas ya registradas se conservan.")
        if mensaje in {"no", "abortar"}:
            estado.clear()
            return responder(estado, "Solicitud descartada. No se cambió ninguna cita.")
        try:
            # Solo la palabra exacta confirma el resumen guardado: el LLM no puede autorizarlo.
            if mensaje == "confirmar":
                pendiente = estado.get("pendiente")
                if not pendiente:
                    return responder(estado, "No hay un resumen pendiente. Primero completa la solicitud.")
                if pendiente["accion"] == "crear":
                    resultado = crear(CrearReserva(**pendiente["datos"], confirmado=True))
                    texto = "Cita registrada. " + resumen(resultado)
                elif pendiente["accion"] == "modificar":
                    resultado = modificar(pendiente["codigo"], ModificarReserva(**pendiente["cambios"], confirmado=True))
                    texto = "Cita modificada. " + resumen(resultado)
                else:
                    resultado = cancelar(pendiente["codigo"], confirmado=True)
                    texto = "Cita cancelada. " + resumen(resultado)
                estado.clear()
                estado["ultimo_codigo"] = resultado["codigo"]
                return responder(estado, texto + ". Código: " + resultado["codigo"])

            datos = entrada.datos.model_dump(mode="json", exclude_none=True)
            intencion = datos.pop("intencion")

            # La extracción del LLM no ve el historial: analiza cada mensaje solo, sin saber qué
            # pregunta acabamos de hacer. Ante una sola palabra, a veces confunde si es el nombre
            # del cliente o el de su mascota y llena los dos campos con el mismo valor; un mismo
            # texto no puede responder a dos preguntas distintas, así que aquí se resuelve el
            # cruce a favor del dato que de verdad faltaba.
            if datos.get("cliente") and datos.get("mascota") and datos["cliente"] == datos["mascota"]:
                if estado.get("mascota") and not estado.get("cliente"):
                    datos.pop("mascota", None)  # ya había mascota; esto responde a "cliente".
                elif estado.get("cliente") and not estado.get("mascota"):
                    datos.pop("cliente", None)  # ya había cliente; esto responde a "mascota".
                elif not estado.get("mascota"):
                    datos.pop("cliente", None)  # nada aún: primero se completa la mascota.

            # Como esta API sí sabe qué dato puntual pidió en el turno anterior, si el mensaje es
            # una sola palabra compatible con un nombre y coincide con lo que faltaba, se usa
            # directamente en vez de perder el dato o repetir la misma pregunta. Fecha, hora y
            # servicio no entran aquí: exigen un formato exacto o una opción de una lista, y no
            # conviene adivinarlos de texto libre.
            if estado.get("intencion") == "reservar" and estado.get("servicio") and not estado.get("mascota"):
                esperando = "mascota"
            elif (estado.get("intencion") == "reservar" and estado.get("servicio") and estado.get("mascota")
                  and estado.get("fecha") and estado.get("hora") and not estado.get("cliente")):
                esperando = "cliente"
            else:
                esperando = None
            if esperando and intencion in {"continuar", "fuera"}:
                texto_bruto = entrada.mensaje.strip()
                if re.fullmatch(r"[A-Za-zÀ-ÿñÑ]{2,30}", texto_bruto):
                    # Un mensaje de una sola palabra solo puede responder una pregunta a la vez:
                    # si el LLM también puso esta misma palabra en el otro campo de nombre, se
                    # descarta esa asignación cruzada.
                    otro_campo = "cliente" if esperando == "mascota" else "mascota"
                    if datos.get(otro_campo) == texto_bruto:
                        datos.pop(otro_campo, None)
                    datos[esperando] = texto_bruto
                    intencion = "continuar"

            if intencion == "fuera":
                # No se descartan datos ya extraídos aunque el mensaje se haya clasificado como
                # fuera de tema: si el LLM sí identificó algo aprovechable, no se pierde.
                estado.update(datos)
                return responder(estado, "Soy el asistente de AnimaBot Veterinaria. Puedo ayudarte con "
                                 "información de servicios y citas para tu mascota, no con otros temas.")
            if intencion == "informacion":
                # Si preguntó por un servicio puntual, responder solo con ese dato en vez de todo el catálogo.
                if datos.get("servicio"):
                    info = servicio_valido(datos["servicio"])
                    return responder(estado, f"{info['nombre']}: {pesos(info['precio_cop'])}, "
                                     f"{info['duracion_minutos']} minutos. Si estabas agendando una cita, "
                                     "conservé tus datos.")
                catalogo = "; ".join(f"{s['nombre']}: {pesos(s['precio_cop'])}, {s['duracion_minutos']} minutos"
                                     for s in SERVICIOS.values())
                dias = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
                horarios = "; ".join(f"{dias[int(dia)]}: {horas[0]}–{horas[1]}" for dia, horas in NEGOCIO["horarios"].items())
                return responder(estado, catalogo + ". " + NEGOCIO["ubicacion"] + ". Horarios: "
                                 + horarios + ". " + NEGOCIO["condiciones"]
                                 + " Si estabas agendando una cita, conservé tus datos.")
            if intencion in {"reservar", "consultar", "cancelar", "modificar"}:
                if estado.get("intencion") != intencion:
                    estado.clear()
                estado["intencion"] = intencion
            if not estado.get("intencion"):
                estado["intencion"] = "reservar" if datos else "inicio"
            if estado["intencion"] == "inicio":
                estado.clear()
                return responder(estado, "Hola, soy AnimaBot, el asistente de la veterinaria. Puedo informarte "
                                 "sobre servicios, agendar, consultar o cancelar una cita para tu mascota. "
                                 "¿Qué necesitas?")
            if any(estado.get(k) != v for k, v in datos.items()):
                estado.pop("pendiente", None)
            estado.update(datos)
            accion = estado["intencion"]
            if accion in {"consultar", "cancelar"}:
                if not estado.get("codigo"):
                    return responder(estado, "Escribe el código de la cita, por ejemplo AB-...")
                r = consultar(estado["codigo"])
                if accion == "consultar":
                    campo = estado.get("campo")
                    texto_puntual = dato_puntual(r, campo) if campo and campo != "completo" else None
                    if texto_puntual:
                        return responder(estado, texto_puntual + " Código: " + r["codigo"])
                    return responder(estado, resumen(r) + ". Estado: " + r["estado"] + ". Código: " + r["codigo"])
                if r["estado"] == "cancelada":
                    return responder(estado, "Esta cita ya está cancelada.")
                estado["pendiente"] = {"accion": "cancelar", "codigo": r["codigo"]}
                return responder(estado, "Vas a cancelar: " + resumen(r) + ". Escribe CONFIRMAR o ABORTAR.")

            if accion == "modificar":
                if not estado.get("codigo"):
                    return responder(estado, "Escribe el código de la cita que deseas modificar, por ejemplo AB-...")
                original = consultar(estado["codigo"])
                if original["estado"] != "activa":
                    estado.clear()
                    return responder(estado, "Esa cita no está activa; no se puede modificar.")
                if not any(estado.get(k) for k in ("fecha", "hora", "servicio", "cliente", "mascota")):
                    return responder(estado, "¿Qué deseas cambiar de la cita " + original["codigo"]
                                     + "? Puedes indicar nueva fecha, hora, servicio, cliente o mascota.")
                nuevo_servicio = estado.get("servicio", original["servicio"])
                servicio_valido(nuevo_servicio)
                nueva_fecha = date.fromisoformat(estado.get("fecha", original["fecha"]))
                nueva_hora = estado.get("hora", original["hora"])
                mismo_horario = (nuevo_servicio == original["servicio"] and nueva_fecha.isoformat() == original["fecha"]
                                  and nueva_hora == original["hora"])
                if not mismo_horario:
                    libres = horarios_libres(nueva_fecha, nuevo_servicio, original["codigo"])
                    if nueva_hora not in libres:
                        estado.pop("pendiente", None)
                        opciones = ", ".join(libres) if libres else "ningún horario libre ese día"
                        return responder(estado, "Ese horario no está disponible. Horarios libres: " + opciones)
                cambios = {k: estado[k] for k in ("cliente", "mascota", "servicio", "fecha", "hora") if estado.get(k)}
                estado["pendiente"] = {"accion": "modificar", "codigo": original["codigo"], "cambios": cambios}
                propuesta = {**original, **cambios}
                return responder(estado, "Cambio propuesto para " + original["codigo"] + ": " + resumen(propuesta)
                                 + ". Escribe CONFIRMAR o ABORTAR.")

            if not estado.get("servicio"):
                opciones = ", ".join(SERVICIOS)
                return responder(estado, "¿Qué servicio necesita tu mascota? Opciones: " + opciones)
            servicio_valido(estado["servicio"])
            if not estado.get("mascota"):
                return responder(estado, "¿Cómo se llama tu mascota?")
            if not estado.get("fecha"):
                return responder(estado, "Indica la fecha completa en formato AAAA-MM-DD.")
            fecha = date.fromisoformat(estado["fecha"])
            libres = horarios_libres(fecha, estado["servicio"])
            if not libres:
                estado.pop("pendiente", None)
                return responder(estado, "No hay horarios disponibles para esa fecha. Indica otra fecha.")
            if not estado.get("hora") or estado["hora"] not in libres:
                estado.pop("pendiente", None)
                return responder(estado, "Elige una hora disponible: " + ", ".join(libres))
            if not estado.get("cliente"):
                return responder(estado, "¿A nombre de quién preparo la cita?")
            solicitud = DatosReserva(**{k: estado[k] for k in DatosReserva.model_fields}).model_dump(mode="json")
            estado["pendiente"] = {"accion": "crear", "datos": solicitud}
            precio = servicio_valido(solicitud["servicio"])["precio_cop"]
            return responder(estado, "Solicitud: " + resumen(solicitud) + f". Precio: {pesos(precio)}. "
                             "Por el momento puedo preparar la solicitud, pero no queda guardada hasta que "
                             "escribas CONFIRMAR. Escribe ABORTAR para descartarla. Aún no se ha registrado.")
        except HTTPException as exc:
            estado.pop("pendiente", None)
            return JSONResponse(status_code=exc.status_code, content=responder(estado, exc.detail))
        except (ValidationError, ValueError):
            estado.pop("pendiente", None)
            return JSONResponse(status_code=422, content=responder(estado, "Revisa los datos: fecha AAAA-MM-DD y hora HH:MM."))
