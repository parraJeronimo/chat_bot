"""Peticiones a Groq y a la FastAPI de AnimaBot Veterinaria. Solo usa la biblioteca estándar.

Variables de entorno:
  CHATBOT_API_URL  dirección de la FastAPI (por defecto http://127.0.0.1:8011)
  GROQ_API_URL     solo para pruebas; por defecto la dirección oficial de Groq
La clave de Groq llega como argumento: nunca se guarda en el historial, en archivos ni en mensajes de error.

Un «plan» es un diccionario con la acción que se va a hacer y sus datos:
  {"accion": "reservar", "cliente": "Laura", "mascota": "Firulais", "servicio": "vacunacion",
   "fecha": "2030-10-14", "hora": "10:00"}
Acciones que solo leen: servicios, disponibilidad, consultar.
Acciones que escriben: reservar, modificar, cancelar (exigen confirmar=True).
"""

import json
import os
from datetime import date
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

BASE = Path(__file__).resolve().parent
NEGOCIO = json.loads((BASE / "negocio.json").read_text(encoding="utf-8-sig"))
SERVICIOS = NEGOCIO["servicios"]
ESCRIBEN = {"reservar", "modificar", "cancelar"}
TIEMPO_LIMITE = 30
AGENTE = "AnimaBot-Laboratorio/1.0"  # Algunos servicios rechazan el agente por defecto de urllib.
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
         "octubre", "noviembre", "diciembre"]


# --- Peticiones HTTP ---------------------------------------------------------------------------
def url_api():
    return os.getenv("CHATBOT_API_URL", "http://127.0.0.1:8011").rstrip("/")


def _enviar(url, cuerpo=None, metodo="GET", cabeceras=None):
    datos = json.dumps(cuerpo).encode("utf-8") if cuerpo is not None else None
    encabezados = {"Accept": "application/json", "User-Agent": AGENTE}
    if datos is not None:
        encabezados["Content-Type"] = "application/json"
    encabezados.update(cabeceras or {})
    peticion = Request(url, data=datos, method=metodo, headers=encabezados)
    with urlopen(peticion, timeout=TIEMPO_LIMITE) as respuesta:
        return respuesta.status, json.loads(respuesta.read().decode("utf-8"))


def llamar_api(metodo, ruta, cuerpo=None, consulta=None):
    """Llama a la FastAPI y devuelve (estado, datos).

    Los errores 4xx son resultados normales del negocio (404 no existe, 409 horario ocupado, 422 datos
    inválidos) y se devuelven como {"detail": ...}. Los 5xx y los fallos de red se propagan como excepción.
    """
    url = url_api() + ruta + ("?" + urlencode(consulta) if consulta else "")
    try:
        return _enviar(url, cuerpo, metodo)
    except HTTPError as error:
        if error.code >= 500:
            raise
        texto = error.read().decode("utf-8", "replace")
        try:
            detalle = json.loads(texto).get("detail", texto)
        except (ValueError, AttributeError):
            detalle = texto
        return error.code, {"detail": detalle}


def pedir_plan_groq(mensajes, clave, modelo):
    """Envía el historial a Groq y devuelve el plan (un diccionario) con el que respondió el modelo."""
    url = os.getenv("GROQ_API_URL", "https://api.groq.com/openai/v1/chat/completions")
    cuerpo = {"model": modelo, "messages": mensajes, "temperature": 0, "max_tokens": 400,
              "response_format": {"type": "json_object"}}
    _, datos = _enviar(url, cuerpo, "POST", {"Authorization": "Bearer " + clave})
    plan = json.loads(datos["choices"][0]["message"]["content"])
    if not isinstance(plan, dict):
        raise ValueError("El modelo no devolvió un objeto JSON")
    return plan


# --- Textos para la persona ---------------------------------------------------------------------
def pesos(valor):
    return f"${valor:,}".replace(",", ".") + " COP"


def fecha_legible(iso):
    dia = date.fromisoformat(iso)
    return f"{DIAS[dia.weekday()]} {dia.day} de {MESES[dia.month - 1]} de {dia.year}"


def nombre_servicio(clave):
    return SERVICIOS.get(clave, {}).get("nombre", clave)


def texto_error(datos):
    detalle = datos.get("detail", "") if isinstance(datos, dict) else ""
    if isinstance(detalle, list):  # errores de validación de FastAPI
        detalle = "; ".join(str(d.get("msg", d)) if isinstance(d, dict) else str(d) for d in detalle)
    return str(detalle).strip().rstrip(".") or "solicitud no válida"


def texto_reserva(r):
    precio = pesos(r["precio_cop"]) if r.get("precio_cop") is not None else "precio no disponible"
    return (f"• Código: **{r['codigo']}**\n"
            f"• Servicio: {nombre_servicio(r['servicio'])} ({r['duracion_minutos']} min, {precio})\n"
            f"• Mascota: {r.get('mascota') or 'sin registrar'}\n"
            f"• Cliente: {r['cliente']}\n"
            f"• Fecha: {fecha_legible(r['fecha'])}\n"
            f"• Hora: {r['hora']}\n"
            f"• Estado: {r['estado']}")


def dato_puntual(r, campo):
    """Una sola línea con el dato que se pidió, en vez de toda la cita."""
    textos = {
        "fecha": f"La fecha de tu cita es {fecha_legible(r['fecha'])}.",
        "hora": f"La hora de tu cita es {r['hora']}.",
        "servicio": f"El servicio reservado es {nombre_servicio(r['servicio'])}.",
        "precio": f"El precio de tu cita es {pesos(r['precio_cop'])}." if r.get("precio_cop") is not None else None,
        "estado": f"El estado de tu cita es {r['estado']}.",
        "cliente": f"La cita está a nombre de {r['cliente']}.",
        "mascota": f"La mascota registrada es {r.get('mascota') or 'ninguna'}.",
        "duracion": f"La cita dura {r['duracion_minutos']} minutos.",
    }
    return textos.get(campo)


def texto_horarios(horarios):
    """Agrupa los días consecutivos con el mismo horario: «lunes a viernes 08:00–18:00; sábado 08:00–13:00»."""
    grupos = []
    for dia in sorted(int(d) for d in horarios):
        abre, cierra = horarios[str(dia)]
        if grupos and grupos[-1][2:] == [abre, cierra] and grupos[-1][1] == dia - 1:
            grupos[-1][1] = dia
        else:
            grupos.append([dia, dia, abre, cierra])
    return "; ".join(f"{DIAS[a]}{' a ' + DIAS[b] if b != a else ''} {abre}–{cierra}"
                     for a, b, abre, cierra in grupos)


def texto_catalogo(negocio, servicio=None):
    """Con `servicio` responde solo ese servicio; sin él, el catálogo, la ubicación y los horarios."""
    def linea(s):
        return f"• {s['nombre']}: {pesos(s['precio_cop'])}, {s['duracion_minutos']} minutos"
    if servicio and servicio in negocio["servicios"]:
        return linea(negocio["servicios"][servicio]).replace("• ", "")
    servicios = "\n".join(linea(s) for s in negocio["servicios"].values())
    return (f"{servicios}\n\n{negocio['ubicacion']}\nHorarios: {texto_horarios(negocio['horarios'])}\n"
            f"{negocio['condiciones']}")


# --- Lo que llama el botón Confirmar y las consultas -----------------------------------------------
def _resultado(mensaje, datos):
    return {"tipo": "resultado", "mensaje": mensaje, "datos": datos}


def fallo(estado, datos, accion):
    """Un 4xx de la API se explica a la persona; no se trata como una caída del sistema."""
    detalle = texto_error(datos)
    if estado == 404:
        mensaje = "No encontré una cita con ese código. Revisa que esté bien escrito."
    elif estado == 409:
        mensaje = (f"No se pudo completar: {detalle}. No se guardó ningún cambio. "
                   "Pide la disponibilidad y elige otro horario." if accion != "cancelar"
                   else f"No se pudo completar: {detalle}.")
    else:
        mensaje = f"No se pudo completar: {detalle}. No se guardó ningún cambio."
    return _resultado(mensaje, {"error": detalle, "http": estado})


def ejecutar(plan, confirmar=False):
    """Ejecuta un plan en la FastAPI. Las operaciones que escriben exigen confirmar=True."""
    accion = plan.get("accion")
    if accion in ESCRIBEN and not confirmar:
        raise ValueError("Esta operación necesita confirmación")
    codigo = quote(str(plan.get("codigo") or ""), safe="")

    if accion == "servicios":
        estado, datos = llamar_api("GET", "/servicios")
        return _resultado(texto_catalogo(datos, plan.get("servicio")), datos) if estado == 200 else fallo(estado, datos, accion)
    if accion == "disponibilidad":
        estado, datos = llamar_api("GET", "/disponibilidad",
                                   consulta={"fecha": plan["fecha"], "servicio": plan["servicio"]})
        if estado != 200:
            return fallo(estado, datos, accion)
        horas = ", ".join(datos["horarios"]) or None
        mensaje = (f"Horarios libres para {nombre_servicio(plan['servicio'])} ({datos['duracion_minutos']} min) "
                   f"el {fecha_legible(plan['fecha'])}: {horas}." if horas else
                   f"No hay horarios libres para {nombre_servicio(plan['servicio'])} el {fecha_legible(plan['fecha'])}.")
        return _resultado(mensaje, datos)
    if accion == "consultar":
        estado, datos = llamar_api("GET", "/reservas/" + codigo)
        if estado != 200:
            return fallo(estado, datos, accion)
        puntual = dato_puntual(datos, plan.get("campo")) if plan.get("campo") not in (None, "completo") else None
        return _resultado(f"{puntual} Código: {datos['codigo']}" if puntual else "Esta es tu cita:\n" + texto_reserva(datos), datos)
    if accion == "reservar":
        cuerpo = {campo: plan[campo] for campo in ("cliente", "mascota", "servicio", "fecha", "hora")}
        estado, datos = llamar_api("POST", "/reservas", {**cuerpo, "confirmado": True})
        if estado != 201:
            return fallo(estado, datos, accion)
        return _resultado("Cita registrada ✅\n" + texto_reserva(datos) +
                          "\n\nGuarda el código para consultarla, modificarla o cancelarla.", datos)
    if accion == "modificar":
        cambios = {c: plan[c] for c in ("servicio", "fecha", "hora", "cliente", "mascota") if plan.get(c)}
        estado, datos = llamar_api("PUT", "/reservas/" + codigo, {**cambios, "confirmado": True})
        return _resultado("Cita modificada ✅\n" + texto_reserva(datos), datos) if estado == 200 else fallo(estado, datos, accion)
    if accion == "cancelar":
        estado, datos = llamar_api("DELETE", "/reservas/" + codigo, consulta={"confirmado": "true"})
        return _resultado("Cita cancelada. El horario quedó libre.\n" + texto_reserva(datos), datos) if estado == 200 else fallo(estado, datos, accion)
    raise ValueError(f"Acción desconocida: {accion!r}")
