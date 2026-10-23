"""Pruebas del almacén SQLite. No necesitan FastAPI, Gradio ni Groq: solo Python.

    .\\.venv\\Scripts\\python.exe pruebas_almacen_sqlite.py

Usan una base temporal; no tocan reservas.db ni reservas.json del proyecto.
"""

import json
import sqlite3
import threading
import unittest
from datetime import date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from almacen_sqlite import AgendaSQLite, ConflictoReserva, ReservaNoEncontrada

BASE = Path(__file__).resolve().parent
NEGOCIO = json.loads((BASE / "negocio.json").read_text(encoding="utf-8-sig"))

# Fechas fijas y lejanas para que las pruebas no dependan del día en que se ejecuten.
LUNES = "2030-10-14"
MARTES = "2030-10-15"
SABADO = "2030-10-19"
DOMINGO = "2030-10-20"
assert [date.fromisoformat(f).weekday() for f in (LUNES, MARTES, SABADO, DOMINGO)] == [0, 1, 5, 6]


def nueva_agenda(ruta):
    return AgendaSQLite(ruta, NEGOCIO["servicios"], horarios=NEGOCIO["horarios"],
                        paso=NEGOCIO["paso_minutos"], prefijo="AB-", largo_codigo=12)


class PruebasAgenda(unittest.TestCase):
    def setUp(self):
        self.carpeta = TemporaryDirectory()
        self.ruta = Path(self.carpeta.name) / "reservas.db"
        self.agenda = nueva_agenda(self.ruta)

    def tearDown(self):
        self.carpeta.cleanup()

    def reservar(self, servicio, hora, fecha=LUNES, cliente="Laura", mascota="Firulais"):
        return self.agenda.crear(cliente, servicio, fecha, hora, mascota)

    def horas(self, servicio, fecha=LUNES, excluir=""):
        return self.agenda.disponibilidad(fecha, servicio, excluir)["horas"]

    # --- Laboratorio, sección 11 -------------------------------------------------------
    def test_guarda_la_fila_con_mascota_y_codigo(self):  # punto 3
        r = self.reservar("consulta_general", "09:00")
        self.assertRegex(r["codigo"], r"^AB-[0-9A-F]{12}$")
        self.assertEqual((r["cliente"], r["mascota"], r["estado"], r["duracion_minutos"]),
                         ("Laura", "Firulais", "activa", 30))
        con = sqlite3.connect(self.ruta)
        fila = con.execute("SELECT codigo, cliente, mascota, fecha, hora, estado FROM reservas").fetchone()
        con.close()
        self.assertEqual(fila, (r["codigo"], "Laura", "Firulais", LUNES, "09:00", "activa"))

    def test_servicio_largo_bloquea_otro_que_empieza_a_media_hora(self):  # punto 4
        self.reservar("peluqueria", "10:00")  # 60 min: ocupa 10:00-11:00
        self.assertNotIn("10:30", self.horas("consulta_general"))
        with self.assertRaises(ConflictoReserva):
            self.reservar("consulta_general", "10:30", cliente="Andrés", mascota="Rocky")
        self.assertEqual(len(self.agenda.listar()), 1)  # nada quedó guardado

    def test_reserva_que_empieza_justo_al_terminar_la_anterior(self):  # punto 5
        self.reservar("peluqueria", "10:00")
        r = self.reservar("consulta_general", "11:00", cliente="Andrés", mascota="Rocky")
        self.assertEqual(r["hora"], "11:00")
        r = self.reservar("cirugia_menor", "08:00", cliente="Sara", mascota="Luna")  # 08:00-09:30
        self.assertEqual(r["duracion_minutos"], 90)

    def test_modificar_a_libre_y_a_ocupado(self):  # punto 6
        a = self.reservar("consulta_general", "09:00")
        self.reservar("consulta_general", "10:00", cliente="Andrés", mascota="Rocky")
        libre = self.agenda.modificar(a["codigo"], "consulta_general", LUNES, "11:00")
        self.assertEqual(libre["hora"], "11:00")
        self.assertIn("09:00", self.horas("consulta_general"))  # el intervalo anterior quedó libre
        with self.assertRaises(ConflictoReserva):
            self.agenda.modificar(a["codigo"], "consulta_general", LUNES, "10:00")
        self.assertEqual(self.agenda.consultar(a["codigo"]), libre)  # conserva sus datos anteriores

    def test_cancelar_libera_el_intervalo(self):  # punto 7
        r = self.reservar("peluqueria", "10:00")
        antes = self.horas("consulta_general")
        self.assertNotIn("10:00", antes)
        self.assertNotIn("10:30", antes)
        self.assertEqual(self.agenda.cancelar(r["codigo"])["estado"], "cancelada")
        despues = self.horas("consulta_general")
        self.assertIn("10:00", despues)
        self.assertIn("10:30", despues)
        with self.assertRaises(ConflictoReserva):  # cancelar dos veces se informa
            self.agenda.cancelar(r["codigo"])
        self.assertEqual(self.agenda.consultar(r["codigo"])["estado"], "cancelada")  # la fila se conserva

    def test_las_reservas_continuan_tras_reiniciar(self):  # punto 11
        r = self.reservar("consulta_general", "09:00")
        reiniciada = nueva_agenda(self.ruta)  # equivale a apagar y volver a encender la API
        self.assertEqual(reiniciada.consultar(r["codigo"]), r)
        self.assertEqual(len(reiniciada.listar()), 1)

    def test_dos_solicitudes_simultaneas_al_mismo_intervalo(self):  # punto 10
        resultados, barrera = [], threading.Barrier(2)

        def intentar(cliente):
            barrera.wait()
            try:
                self.agenda.crear(cliente, "consulta_general", LUNES, "09:00", "Firulais")
                resultados.append("aceptada")
            except ConflictoReserva:
                resultados.append("rechazada")

        hilos = [threading.Thread(target=intentar, args=(n,)) for n in ("Laura", "Andrés")]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join()
        self.assertEqual(sorted(resultados), ["aceptada", "rechazada"])
        self.assertEqual(len(self.agenda.listar()), 1)

    # --- Reglas propias de la veterinaria ----------------------------------------------
    def test_el_sabado_cierra_a_las_13(self):
        self.assertEqual(self.horas("consulta_general", SABADO)[-1], "12:30")
        self.assertEqual(self.horas("cirugia_menor", SABADO)[-1], "11:30")  # 90 min: termina 13:00
        self.reservar("consulta_general", "12:30", SABADO)
        for servicio, hora in (("consulta_general", "13:00"), ("cirugia_menor", "12:00")):
            with self.assertRaises(ValueError):
                self.reservar(servicio, hora, SABADO, cliente="Andrés", mascota="Rocky")
        self.assertEqual(self.horas("consulta_general", MARTES)[-1], "17:30")  # entre semana, hasta las 18:00

    def test_domingo_cerrado(self):
        self.assertEqual(self.horas("consulta_general", DOMINGO), [])  # consultar no es un error
        with self.assertRaises(ValueError):
            self.reservar("consulta_general", "09:00", DOMINGO)

    def test_datos_invalidos(self):
        casos = [("consulta_general", "09:15", LUNES),  # no cae en pasos de 30 minutos
                 ("consulta_general", "07:30", LUNES),  # antes de abrir
                 ("consulta_general", "25:00", LUNES),
                 ("inventado", "09:00", LUNES),
                 ("consulta_general", "09:00", "2000-01-03")]  # fecha pasada
        for servicio, hora, fecha in casos:
            with self.subTest(servicio=servicio, hora=hora, fecha=fecha):
                with self.assertRaises(ValueError):
                    self.reservar(servicio, hora, fecha)
        with self.assertRaises(ValueError):
            self.agenda.crear("L", "consulta_general", LUNES, "09:00", "Firulais")  # nombre demasiado corto
        self.assertEqual(self.agenda.listar(), [])

    def test_hoy_no_se_ofrecen_ni_aceptan_horas_que_ya_pasaron(self):
        self.agenda.ahora = lambda: datetime(2030, 10, 16, 10, 10)  # miércoles 10:10
        hoy = "2030-10-16"
        libres = self.horas("consulta_general", hoy)
        self.assertEqual(libres[0], "10:30")
        with self.assertRaises(ValueError):
            self.reservar("consulta_general", "10:00", hoy)
        self.assertEqual(self.reservar("consulta_general", "10:30", hoy)["hora"], "10:30")

    def test_modificar_parcial(self):
        r = self.reservar("consulta_general", "09:00")
        m = self.agenda.modificar(r["codigo"], mascota="Toby")  # solo cambia la mascota
        self.assertEqual((m["mascota"], m["cliente"], m["hora"]), ("Toby", "Laura", "09:00"))
        m = self.agenda.modificar(r["codigo"], servicio="peluqueria")  # cambia la duración
        self.assertEqual((m["servicio"], m["duracion_minutos"], m["mascota"]), ("peluqueria", 60, "Toby"))
        self.assertNotIn("09:30", self.horas("consulta_general"))
        with self.assertRaises(ReservaNoEncontrada):
            self.agenda.modificar("AB-NOEXISTE", hora="10:00")
        self.agenda.cancelar(r["codigo"])
        with self.assertRaises(ConflictoReserva):  # una cita cancelada no se modifica
            self.agenda.modificar(r["codigo"], hora="10:00")

    def test_una_reserva_no_choca_consigo_misma_al_modificar(self):
        r = self.reservar("peluqueria", "10:00")
        m = self.agenda.modificar(r["codigo"], "peluqueria", LUNES, "10:30")  # se solapa con su propio intervalo
        self.assertEqual(m["hora"], "10:30")

    # --- Base creada con el archivo original del laboratorio ---------------------------
    def test_base_del_laboratorio_sin_mascota_se_actualiza(self):
        ruta = Path(self.carpeta.name) / "antigua.db"
        con = sqlite3.connect(ruta)
        con.execute("""CREATE TABLE reservas (codigo TEXT PRIMARY KEY, cliente TEXT NOT NULL,
            servicio TEXT NOT NULL, fecha TEXT NOT NULL, hora TEXT NOT NULL,
            duracion_minutos INTEGER NOT NULL CHECK (duracion_minutos > 0),
            estado TEXT NOT NULL CHECK (estado IN ('activa', 'cancelada')))""")
        con.execute("INSERT INTO reservas VALUES ('VIEJA1', 'Laura', 'consulta_general', ?, '09:00', 30, 'activa')",
                    (LUNES,))
        con.commit()
        con.close()
        agenda = nueva_agenda(ruta)
        self.assertEqual(agenda.consultar("VIEJA1")["mascota"], "")  # la fila se conserva
        self.assertEqual(agenda.crear("Andrés", "consulta_general", LUNES, "09:30", "Rocky")["mascota"], "Rocky")

    # --- Migración desde reservas.json -------------------------------------------------
    def escribir_json(self, registros, nombre="origen.json"):
        ruta = Path(self.carpeta.name) / nombre
        ruta.write_text(json.dumps(registros), encoding="utf-8")
        return ruta

    def registro(self, codigo, hora="09:00", estado="activa", fecha=LUNES, **extra):
        return {"codigo": codigo, "cliente": "Laura", "mascota": "Firulais", "servicio": "consulta_general",
                "fecha": fecha, "hora": hora, "estado": estado, "precio_cop": 60000, "duracion_minutos": 30,
                "creada_en": "2026-09-01T10:00:00-05:00", "cancelada_en": None, **extra}

    def test_migracion_del_formato_anterior_es_idempotente(self):
        ruta = self.escribir_json([self.registro("AB-1", "09:00"),
                                   self.registro("AB-2", "10:00", "cancelada", fecha="2026-01-05"),
                                   self.registro("AB-3", "09:00", fecha=MARTES)])
        self.assertEqual(self.agenda.importar_json(ruta), {"importadas": 3, "ya_existentes": 0})
        self.assertEqual(self.agenda.importar_json(ruta), {"importadas": 0, "ya_existentes": 3})
        self.assertEqual(len(self.agenda.listar()), 3)
        self.assertEqual(self.agenda.consultar("AB-1")["mascota"], "Firulais")
        self.assertNotIn("09:00", self.horas("consulta_general"))  # lo importado ocupa el intervalo

    def test_migracion_con_cruce_se_revierte_completa(self):
        ruta = self.escribir_json([self.registro("AB-1", "09:00"), self.registro("AB-2", "09:00")])
        with self.assertRaises(ConflictoReserva):
            self.agenda.importar_json(ruta)
        self.assertEqual(self.agenda.listar(), [])  # ni siquiera la primera quedó guardada

    def test_migracion_con_codigo_repetido_y_datos_distintos(self):
        self.agenda.importar_json(self.escribir_json([self.registro("AB-1", "09:00")]))
        with self.assertRaises(ConflictoReserva):
            self.agenda.importar_json(self.escribir_json([self.registro("AB-1", "10:00")], "otro.json"))
        self.assertEqual(self.agenda.consultar("AB-1")["hora"], "09:00")

    def test_migracion_de_la_lista_vacia_del_proyecto(self):
        ruta = BASE / "reservas.json"
        self.assertEqual(self.agenda.importar_json(ruta), {"importadas": 0, "ya_existentes": 0})

    def test_modificar_datos_de_una_reserva_historica(self):
        self.agenda.importar_json(self.escribir_json([self.registro("AB-1", fecha="2026-01-05")]))
        m = self.agenda.modificar("AB-1", cliente="Laura Gómez")  # el horario no cambia: no se revalida
        self.assertEqual(m["cliente"], "Laura Gómez")


if __name__ == "__main__":
    unittest.main(verbosity=2)
