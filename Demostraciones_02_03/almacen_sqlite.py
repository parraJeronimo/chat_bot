"""Reservas SQLite para una agenda. Cada operación utiliza su propia conexión.

Versión adaptada a AnimaBot Veterinaria. Respecto al archivo entregado en el laboratorio:
- guarda también la mascota (columna `mascota`);
- admite un horario distinto por día (`horarios`), por ejemplo el sábado hasta las 13:00;
- usa la hora actual de la zona del negocio (`zona`) para no ofrecer horas que ya pasaron;
- permite un prefijo y un largo para el código de la reserva (`prefijo`, `largo_codigo`);
- `modificar` acepta cambios parciales y los resuelve dentro de la misma transacción.
Todos los parámetros nuevos son opcionales: las llamadas del laboratorio siguen funcionando igual.
"""

import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from uuid import uuid4


class ConflictoReserva(ValueError):
    pass


class ReservaNoEncontrada(ValueError):
    pass


# Orden en que se escriben y se comparan los campos de una reserva.
COLUMNAS = ("codigo", "cliente", "mascota", "servicio", "fecha", "hora", "duracion_minutos", "estado")


def minutos(hora):
    if not isinstance(hora, str) or not re.fullmatch(r"\d{2}:\d{2}", hora):
        raise ValueError("Usa una hora HH:MM")
    horas, minutos_hora = map(int, hora.split(":"))
    if not 0 <= horas <= 23 or not 0 <= minutos_hora <= 59:
        raise ValueError("Hora inválida")
    return horas * 60 + minutos_hora


def texto_hora(valor):
    return f"{valor // 60:02d}:{valor % 60:02d}"


class AgendaSQLite:
    def __init__(self, ruta, servicios, apertura="09:00", cierre="18:00",
                 dias=(0, 1, 2, 3, 4, 5), paso=30, horarios=None, zona=None,
                 prefijo="", largo_codigo=8):
        self.ruta = Path(ruta).resolve()
        self.servicios = servicios
        self.paso, self.zona = paso, zona
        self.prefijo, self.largo_codigo = prefijo, largo_codigo
        if not isinstance(paso, int) or paso <= 0:
            raise ValueError("Revisa el horario y el paso de la agenda")
        if horarios is None:
            horarios = {dia: (apertura, cierre) for dia in dias}
        # día de la semana (lunes = 0) -> (minuto de apertura, minuto de cierre). Un día sin entrada está cerrado.
        self.horario = {int(dia): (minutos(abre), minutos(cierra)) for dia, (abre, cierra) in horarios.items()}
        if not self.horario or any(abre >= cierra for abre, cierra in self.horario.values()):
            raise ValueError("Revisa el horario y el paso de la agenda")
        self.dias = tuple(sorted(self.horario))
        with self.conexion(escritura=True) as con:
            con.execute("""CREATE TABLE IF NOT EXISTS reservas (
                codigo TEXT PRIMARY KEY,
                cliente TEXT NOT NULL,
                mascota TEXT NOT NULL DEFAULT '',
                servicio TEXT NOT NULL,
                fecha TEXT NOT NULL,
                hora TEXT NOT NULL,
                duracion_minutos INTEGER NOT NULL CHECK (duracion_minutos > 0),
                estado TEXT NOT NULL CHECK (estado IN ('activa', 'cancelada'))
            )""")
            # Una base creada con el archivo original no tiene `mascota`: se agrega sin perder filas.
            columnas = {fila["name"] for fila in con.execute("PRAGMA table_info(reservas)")}
            if "mascota" not in columnas:
                con.execute("ALTER TABLE reservas ADD COLUMN mascota TEXT NOT NULL DEFAULT ''")
            con.execute("CREATE INDEX IF NOT EXISTS idx_fecha_estado ON reservas(fecha, estado)")

    @contextmanager
    def conexion(self, escritura=False):
        con = sqlite3.connect(self.ruta, timeout=10, isolation_level=None)
        con.row_factory = sqlite3.Row
        try:
            if escritura:
                # La comprobación del horario y el guardado van en la misma transacción.
                con.execute("BEGIN IMMEDIATE")
            yield con
            if escritura:
                con.commit()
        except Exception:
            if escritura:
                con.rollback()
            raise
        finally:
            con.close()

    def ahora(self):
        return datetime.now(self.zona) if self.zona else datetime.now()

    def nuevo_codigo(self):
        return f"{self.prefijo}{uuid4().hex[:self.largo_codigo].upper()}"

    def duracion(self, servicio):
        if servicio not in self.servicios:
            raise ValueError("Servicio desconocido")
        valor = self.servicios[servicio].get("duracion_minutos")
        if type(valor) is not int or valor <= 0:
            raise ValueError("El catálogo debe indicar duracion_minutos como entero positivo")
        return valor

    def validar_fecha(self, fecha, permitir_pasado=False, permitir_cerrado=False):
        valor = date.fromisoformat(fecha)
        if valor.isoformat() != fecha:
            raise ValueError("Usa fecha AAAA-MM-DD")
        if not permitir_pasado and valor < self.ahora().date():
            raise ValueError("No se puede reservar en una fecha pasada")
        if not permitir_cerrado and valor.weekday() not in self.horario:
            raise ValueError("El negocio está cerrado ese día")
        return valor

    def validar_intervalo(self, fecha, hora, duracion, permitir_pasado=False):
        valor = self.validar_fecha(fecha, permitir_pasado)
        inicio = minutos(hora)
        apertura, cierre = self.horario[valor.weekday()]
        if inicio < apertura or inicio + duracion > cierre:
            raise ValueError("La atención debe terminar dentro del horario del negocio")
        if (inicio - apertura) % self.paso:
            raise ValueError(f"Selecciona una hora en pasos de {self.paso} minutos")
        ahora = self.ahora()
        if not permitir_pasado and valor == ahora.date() and inicio <= ahora.hour * 60 + ahora.minute:
            raise ValueError("Esa hora ya pasó. Elige una hora posterior")
        return inicio

    def ocupado(self, con, fecha, inicio, duracion, excluir=""):
        filas = con.execute(
            "SELECT hora, duracion_minutos FROM reservas WHERE fecha=? AND estado='activa' AND codigo<>?",
            (fecha, excluir),
        ).fetchall()
        # Una sola agenda: dos intervalos que se cruzan no pueden estar activos.
        return any(inicio < minutos(fila["hora"]) + fila["duracion_minutos"]
                   and inicio + duracion > minutos(fila["hora"]) for fila in filas)

    def disponibilidad(self, fecha, servicio, excluir=""):
        # Un día cerrado no es un error al consultar: simplemente no tiene horas libres.
        valor = self.validar_fecha(fecha, permitir_cerrado=True)
        duracion = self.duracion(servicio)
        horas = []
        if valor.weekday() in self.horario:
            apertura, cierre = self.horario[valor.weekday()]
            ahora = self.ahora()
            # Hoy, las horas que ya empezaron no se ofrecen.
            pasado = ahora.hour * 60 + ahora.minute if valor == ahora.date() else -1
            with self.conexion() as con:
                horas = [texto_hora(inicio)
                         for inicio in range(apertura, cierre - duracion + 1, self.paso)
                         if inicio > pasado and not self.ocupado(con, fecha, inicio, duracion, excluir)]
        return {"fecha": fecha, "servicio": servicio, "duracion_minutos": duracion,
                "horas": horas}

    def listar(self):
        with self.conexion() as con:
            return [dict(fila) for fila in con.execute("SELECT * FROM reservas ORDER BY fecha, hora, codigo")]

    def obtener(self, con, codigo):
        fila = con.execute("SELECT * FROM reservas WHERE codigo=?", (codigo,)).fetchone()
        if fila is None:
            raise ReservaNoEncontrada("Reserva no encontrada")
        return dict(fila)

    def consultar(self, codigo):
        with self.conexion() as con:
            return self.obtener(con, codigo)

    def crear(self, cliente, servicio, fecha, hora, mascota=""):
        if not isinstance(cliente, str) or len(cliente.strip()) < 2:
            raise ValueError("Indica el nombre del cliente")
        if not isinstance(mascota, str):
            raise ValueError("Indica el nombre de la mascota")
        duracion = self.duracion(servicio)
        inicio = self.validar_intervalo(fecha, hora, duracion)
        codigo = self.nuevo_codigo()
        with self.conexion(escritura=True) as con:
            if self.ocupado(con, fecha, inicio, duracion):
                raise ConflictoReserva("El intervalo solicitado se cruza con una reserva activa")
            con.execute(
                "INSERT INTO reservas (codigo, cliente, mascota, servicio, fecha, hora, duracion_minutos, estado) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 'activa')",
                (codigo, cliente.strip(), mascota.strip(), servicio, fecha, hora, duracion),
            )
            return self.obtener(con, codigo)

    def modificar(self, codigo, servicio=None, fecha=None, hora=None, cliente=None, mascota=None):
        """Cambia los datos indicados; lo que llegue como None se conserva."""
        if cliente is not None and (not isinstance(cliente, str) or len(cliente.strip()) < 2):
            raise ValueError("Indica el nombre del cliente")
        if mascota is not None and (not isinstance(mascota, str) or not mascota.strip()):
            raise ValueError("Indica el nombre de la mascota")
        with self.conexion(escritura=True) as con:
            actual = self.obtener(con, codigo)
            if actual["estado"] != "activa":
                raise ConflictoReserva("La reserva ya no está activa")
            nuevo = {"servicio": servicio if servicio is not None else actual["servicio"],
                     "fecha": fecha if fecha is not None else actual["fecha"],
                     "hora": hora if hora is not None else actual["hora"]}
            if any(nuevo[campo] != actual[campo] for campo in nuevo):
                duracion = self.duracion(nuevo["servicio"])
                inicio = self.validar_intervalo(nuevo["fecha"], nuevo["hora"], duracion)
                if self.ocupado(con, nuevo["fecha"], inicio, duracion, excluir=codigo):
                    raise ConflictoReserva("El nuevo intervalo está ocupado")
            else:
                # El horario no cambia: solo se corrigen datos de la persona o la mascota.
                duracion = actual["duracion_minutos"]
            con.execute(
                "UPDATE reservas SET cliente=?, mascota=?, servicio=?, fecha=?, hora=?, duracion_minutos=? "
                "WHERE codigo=?",
                (cliente.strip() if cliente is not None else actual["cliente"],
                 mascota.strip() if mascota is not None else actual["mascota"],
                 nuevo["servicio"], nuevo["fecha"], nuevo["hora"], duracion, codigo),
            )
            return self.obtener(con, codigo)

    def cancelar(self, codigo):
        with self.conexion(escritura=True) as con:
            actual = self.obtener(con, codigo)
            if actual["estado"] != "activa":
                raise ConflictoReserva("La reserva ya está cancelada")
            con.execute("UPDATE reservas SET estado='cancelada' WHERE codigo=?", (codigo,))
            return self.obtener(con, codigo)

    def importar_json(self, ruta):
        registros = json.loads(Path(ruta).read_text(encoding="utf-8-sig"))
        if isinstance(registros, dict):
            registros = registros.get("reservas")
        if not isinstance(registros, list):
            raise ValueError("Adapta el JSON a una lista de reservas o a {'reservas': [...]}")
        nuevos = existentes = 0
        with self.conexion(escritura=True) as con:
            for registro in registros:
                if not isinstance(registro, dict):
                    raise ValueError("Cada reserva debe ser un objeto")
                try:
                    datos = {campo: registro[campo] for campo in
                             ("codigo", "cliente", "servicio", "fecha", "hora", "estado")}
                except KeyError as error:
                    raise ValueError(f"Adapta el campo que falta: {error}") from error
                if any(not isinstance(valor, str) or not valor.strip() for valor in datos.values()):
                    raise ValueError("Los campos de la reserva deben ser textos no vacíos")
                mascota = registro.get("mascota", "")
                if not isinstance(mascota, str):
                    raise ValueError("La mascota de la reserva debe ser texto")
                duracion = registro.get("duracion_minutos", self.duracion(datos["servicio"]))
                if type(duracion) is not int or duracion <= 0:
                    raise ValueError("Duración inválida en el JSON")
                if datos["estado"] not in {"activa", "cancelada"}:
                    raise ValueError("Adapta el estado a activa o cancelada")
                # Importamos el histórico aunque su fecha haya pasado.
                fecha = date.fromisoformat(datos["fecha"])
                if fecha.isoformat() != datos["fecha"]:
                    raise ValueError("Fecha inválida en el JSON")
                inicio = minutos(datos["hora"])
                if inicio + duracion > 24 * 60:
                    raise ValueError("La reserva histórica termina fuera del día")
                fila = {**datos, "mascota": mascota.strip(), "duracion_minutos": duracion}
                previa = con.execute("SELECT * FROM reservas WHERE codigo=?", (datos["codigo"],)).fetchone()
                if previa is not None:
                    if dict(previa) != fila:
                        raise ConflictoReserva("El código ya existe con datos distintos; revisa la migración")
                    existentes += 1
                    continue
                if datos["estado"] == "activa" and self.ocupado(con, datos["fecha"], inicio, duracion):
                    raise ConflictoReserva("El JSON contiene un intervalo activo que se cruza con otro")
                con.execute("INSERT INTO reservas (codigo, cliente, mascota, servicio, fecha, hora, "
                            "duracion_minutos, estado) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                            tuple(fila[campo] for campo in COLUMNAS))
                nuevos += 1
        return {"importadas": nuevos, "ya_existentes": existentes}


if __name__ == "__main__":
    import argparse
    base = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="Importar reservas JSON a SQLite")
    parser.add_argument("--migrar", required=True, type=Path)
    parser.add_argument("--negocio", type=Path, default=base / "negocio.json")
    parser.add_argument("--base", type=Path, default=base / "reservas.db")
    args = parser.parse_args()
    catalogo = json.loads(args.negocio.read_text(encoding="utf-8-sig"))["servicios"]
    agenda = AgendaSQLite(args.base, catalogo)
    try:
        print(json.dumps(agenda.importar_json(args.migrar), ensure_ascii=False, indent=2))
    except ValueError as error:
        parser.exit(1, f"Migración detenida: {error}\n")
