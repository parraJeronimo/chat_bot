"""Referencia para adaptar el main.py del equipo al almacenamiento SQLite.

Usa negocio.json con servicios como diccionario y duracion_minutos por servicio.
Mantén las rutas y reglas de tu negocio cuando lleves esta integración a tu main.py.
"""

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from datetime import date

from almacen_sqlite import AgendaSQLite, ConflictoReserva, ReservaNoEncontrada

BASE = Path(__file__).resolve().parent
SERVICIOS = json.loads((BASE / "negocio.json").read_text(encoding="utf-8-sig"))["servicios"]
agenda = AgendaSQLite(BASE / "reservas.db", SERVICIOS)
app = FastAPI(title="Reservas del equipo · SQLite")


class ReservaNueva(BaseModel):
    cliente: str = Field(min_length=2)
    servicio: str
    fecha: date
    hora: str
    confirmada: bool


class CambioReserva(BaseModel):
    servicio: str
    fecha: date
    hora: str


def responder(funcion, *args):
    try:
        return funcion(*args)
    except ReservaNoEncontrada as error:
        raise HTTPException(404, str(error)) from error
    except ConflictoReserva as error:
        raise HTTPException(409, str(error)) from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.get("/api/servicios")
def servicios():
    return SERVICIOS


@app.get("/api/disponibilidad")
def disponibilidad(fecha: date, servicio: str):
    return responder(agenda.disponibilidad, fecha.isoformat(), servicio)


@app.get("/api/reservas")
def reservas():
    return agenda.listar()


@app.get("/api/reservas/{codigo}")
def consultar(codigo: str):
    return responder(agenda.consultar, codigo)


@app.post("/api/reservas", status_code=201)
def crear(datos: ReservaNueva):
    if not datos.confirmada:
        raise HTTPException(400, "La operación debe estar confirmada")
    return responder(agenda.crear, datos.cliente, datos.servicio, datos.fecha.isoformat(), datos.hora)


@app.put("/api/reservas/{codigo}")
def modificar(codigo: str, datos: CambioReserva):
    return responder(agenda.modificar, codigo, datos.servicio, datos.fecha.isoformat(), datos.hora)


@app.delete("/api/reservas/{codigo}")
def cancelar(codigo: str):
    return responder(agenda.cancelar, codigo)
