"""Prueba reproducible sin Groq ni Flowise. Usa una base SQLite temporal: no cambia las reservas de reservas.db."""
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient
import main


def probar():
    with TemporaryDirectory() as carpeta:
        original = main.agenda
        main.agenda = main.crear_agenda(Path(carpeta) / 'reservas.db')
        main.SESIONES.clear()
        try:
            with TestClient(main.app) as api:
                fecha = datetime.now(main.ZONA).date() + timedelta(days=2)
                while fecha.weekday() == 6:
                    fecha += timedelta(days=1)
                dia = fecha.isoformat()
                datos = dict(cliente='Laura', mascota='Firulais', servicio='consulta_general', fecha=dia, hora='09:00', confirmado=True)
                assert api.get('/servicios').status_code == 200
                assert '09:00' in api.get('/disponibilidad', params={'fecha': dia, 'servicio': 'consulta_general'}).json()['horarios']
                assert api.post('/reservas', json={**datos, 'confirmado': False}).status_code == 422
                assert api.post('/reservas', json={**datos, 'hora': '25:00'}).status_code == 422
                assert api.post('/reservas', json={**datos, 'servicio': 'inventado'}).status_code == 422
                assert api.post('/reservas', json={**datos, 'hora': '18:00'}).status_code == 422  # termina fuera del horario
                assert api.post('/reservas', json={**datos, 'fecha': '2000-01-01'}).status_code == 422
                domingo = fecha + timedelta(days=(6-fecha.weekday()) % 7)
                assert api.get('/disponibilidad', params={'fecha': domingo.isoformat(), 'servicio': 'consulta_general'}).json()['horarios'] == []
                # Dos peticiones compiten por el mismo horario: solo una se registra.
                with ThreadPoolExecutor(max_workers=2) as pool:
                    respuestas = list(pool.map(lambda _: api.post('/reservas', json=datos), range(2)))
                assert sorted(r.status_code for r in respuestas) == [201, 409]
                reserva = next(r.json() for r in respuestas if r.status_code == 201)
                codigo = reserva['codigo']
                assert len(main.agenda.listar()) == 1
                main.SESIONES.clear()  # La reserva sobrevive a perder el estado en memoria.
                assert api.get('/reservas/' + codigo).json()['estado'] == 'activa'
                # Reiniciar la API equivale a abrir otra agenda sobre el mismo archivo: las filas siguen ahí.
                main.agenda = main.crear_agenda(main.agenda.ruta)
                assert [r['codigo'] for r in api.get('/reservas').json()] == [codigo]
                assert api.get('/reservas/' + codigo).json()['mascota'] == 'Firulais'
                assert api.delete('/reservas/' + codigo).status_code == 422
                assert api.get('/reservas/INEXISTENTE').status_code == 404
                libres = api.get('/disponibilidad', params={'fecha': dia, 'servicio': 'vacunacion'}).json()['horarios']
                assert '09:00' not in libres and '09:30' in libres
                # Cruce de intervalos con distinta hora inicial: una peluquería (60 min) ocupa 10:00-11:00.
                peluqueria = api.post('/reservas', json={**datos, 'servicio': 'peluqueria', 'hora': '10:00'})
                assert peluqueria.status_code == 201 and peluqueria.json()['duracion_minutos'] == 60
                libres = api.get('/disponibilidad', params={'fecha': dia, 'servicio': 'consulta_general'}).json()['horarios']
                assert '10:00' not in libres and '10:30' not in libres and '11:00' in libres
                assert api.post('/reservas', json={**datos, 'hora': '10:30'}).status_code == 409  # se cruza
                # Al mover una cita, su propio horario cuenta como libre (parámetro opcional `excluir`).
                propias = api.get('/disponibilidad', params={'fecha': dia, 'servicio': 'peluqueria',
                                                             'excluir': peluqueria.json()['codigo']}).json()['horarios']
                assert '10:00' in propias and '10:30' in propias and '10:30' not in libres
                contigua = api.post('/reservas', json={**datos, 'hora': '11:00'})
                assert contigua.status_code == 201  # empieza justo cuando termina la peluquería
                # Se cancelan para dejar libres 10:00 y 11:00 en las pruebas siguientes.
                for creada in (peluqueria, contigua):
                    assert api.delete('/reservas/' + creada.json()['codigo'], params={'confirmado': True}).status_code == 200
                assert api.delete('/reservas/' + codigo, params={'confirmado': True}).json()['estado'] == 'cancelada'
                assert api.delete('/reservas/' + codigo, params={'confirmado': True}).status_code == 200
                assert '09:00' in api.get('/disponibilidad', params={'fecha': dia, 'servicio': 'consulta_general'}).json()['horarios']

                def chat(texto, extraccion=None, sesion='grupo-1'):
                    return api.post('/chat', json={'session_id': sesion, 'mensaje': texto, 'datos': extraccion or {}})

                extraccion = {k: v for k, v in datos.items() if k != 'confirmado'}
                extraccion['intencion'] = 'reservar'
                r = chat('Quiero reservar', extraccion).json()
                assert r['estado_sesion']['pendiente']['datos']['hora'] == '09:00'
                # Sin CONFIRMAR no hay fila nueva. Siguen 3: la reserva cancelada y las dos de la prueba de cruce.
                assert len(main.agenda.listar()) == 3
                assert 'No hay un resumen' in chat('CONFIRMAR', sesion='grupo-2').json()['respuesta']
                r = chat('Mejor a las 10:00', {'intencion': 'continuar', 'hora': '10:00'}).json()
                assert r['estado_sesion']['pendiente']['datos']['hora'] == '10:00'
                assert 'pendiente' in chat('Cuánto cuesta', {'intencion': 'informacion'}).json()['estado_sesion']
                assert 'pendiente' in chat('Sí', {}).json()['estado_sesion']  # Solo CONFIRMAR autoriza.
                r = chat('CONFIRMAR').json()
                assert 'Cita registrada' in r['respuesta']
                codigo2 = r['estado_sesion']['ultimo_codigo']
                assert api.get('/reservas/' + codigo2).json()['hora'] == '10:00'
                assert 'No hay un resumen' in chat('CONFIRMAR').json()['respuesta']
                assert len(main.agenda.listar()) == 4  # las 3 anteriores y la que acaba de confirmarse
                chat('/reset')
                assert api.get('/reservas/' + codigo2).json()['estado'] == 'activa'
                chat('Cancelar ' + codigo2, {'intencion': 'cancelar', 'codigo': codigo2})
                assert api.get('/reservas/' + codigo2).json()['estado'] == 'activa'
                assert 'Cita cancelada' in chat('CONFIRMAR').json()['respuesta']
                assert api.get('/reservas/' + codigo2).json()['estado'] == 'cancelada'
                assert chat('Datos maliciosos', {'intencion': 'continuar', 'confirmado': True}).status_code == 422

                # Reserva fresca y activa, independiente de las ya canceladas arriba, para probar
                # la consulta puntual y la modificación.
                nueva = dict(datos, hora='09:00')
                codigo3 = api.post('/reservas', json=nueva).json()['codigo']

                # --- Consultar un solo dato (mostrar solo lo que se pide) ---
                r = chat('¿A qué hora es mi cita?', {'intencion': 'consultar', 'codigo': codigo3, 'campo': 'hora'},
                         'grupo-campo').json()
                assert r['respuesta'] == f'La hora de tu cita es 09:00. Código: {codigo3}'
                r = chat('¿Y el precio?', {'intencion': 'continuar', 'campo': 'precio'}, 'grupo-campo').json()
                assert 'precio de tu cita' in r['respuesta'] and 'pendiente' not in r['estado_sesion']
                r = chat('Cuéntamela completa', {'intencion': 'continuar', 'campo': 'completo'}, 'grupo-campo').json()
                assert 'Estado: activa' in r['respuesta']

                # --- Modificar una reserva activa si hay disponibilidad ---
                sesion_mod = 'grupo-mod'
                r = chat('Quiero cambiar mi cita', {'intencion': 'modificar', 'codigo': codigo3}, sesion_mod).json()
                assert 'deseas cambiar' in r['respuesta']
                r = chat('A las 11:00 ese mismo día', {'intencion': 'continuar', 'hora': '11:00'}, sesion_mod).json()
                assert r['estado_sesion']['pendiente']['accion'] == 'modificar'
                r = chat('CONFIRMAR', sesion=sesion_mod).json()
                assert 'Cita modificada' in r['respuesta']
                assert api.get('/reservas/' + codigo3).json()['hora'] == '11:00'
                # Intentar mover la cita a un horario ya ocupado por otra reserva activa: debe rechazarse.
                # (Tras el CONFIRMAR anterior el estado se limpió, como ya ocurre con cancelar; se repite el código.)
                ocupar = dict(datos, hora='09:00')
                respuesta_bloqueador = api.post('/reservas', json=ocupar)
                assert respuesta_bloqueador.status_code == 201
                bloqueador = respuesta_bloqueador.json()
                r = chat('Cámbiala a las 09:00', {'intencion': 'modificar', 'codigo': codigo3, 'hora': '09:00'},
                         sesion_mod).json()
                assert 'no está disponible' in r['respuesta']
                assert api.get('/reservas/' + codigo3).json()['hora'] == '11:00'  # No se modificó.
                # Se libera la hora que se ocupó solo para esta prueba, para no afectar pruebas futuras.
                assert api.delete('/reservas/' + bloqueador['codigo'], params={'confirmado': True}).status_code == 200
                # Cita cancelada no se puede modificar.
                assert api.delete('/reservas/' + codigo3, params={'confirmado': True}).status_code == 200
                r = chat('Quiero cambiarla', {'intencion': 'modificar', 'codigo': codigo3}, 'grupo-mod-2').json()
                assert 'no está activa' in r['respuesta']
                print('OK: consulta puntual y modificación de reservas.')

                # --- Respuestas sueltas de una sola palabra (sin contexto para el LLM) ---
                # Reproduce el caso real: el mensaje "Arturo" llega sin datos útiles o mal
                # clasificado, justo cuando la API está esperando el nombre de la mascota.
                sesion_suelto = 'grupo-suelto'
                extra = {'intencion': 'reservar', 'cliente': 'Laura', 'servicio': 'consulta_general'}
                r = chat('Quiero una consulta general', extra, sesion_suelto).json()
                assert 'mascota' in r['respuesta'].casefold()
                # El LLM no reconoció nada útil y clasificó el mensaje como fuera de tema.
                r = chat('Arturo', {'intencion': 'fuera'}, sesion_suelto).json()
                assert r['estado_sesion'].get('mascota') == 'Arturo'
                assert 'fecha' in r['respuesta'].casefold()
                # Una frase de varias palabras nunca se adivina como nombre: sigue pidiendo la fecha.
                r = chat('como me llamo', {'intencion': 'continuar'}, sesion_suelto).json()
                assert 'fecha' in r['respuesta'].casefold() and r['estado_sesion'].get('mascota') == 'Arturo'
                print('OK: se recupera un dato aunque el LLM no vea el historial de la conversación.')

                # --- El LLM confunde nombre de cliente y de mascota en un mensaje suelto ---
                # Reproduce el reporte real: al responder la pregunta del cliente, el LLM llenó
                # tanto "cliente" como "mascota" con el mismo texto. No debe perderse la mascota.
                fecha_cruce = fecha + timedelta(days=1)
                while fecha_cruce.weekday() == 6:
                    fecha_cruce += timedelta(days=1)
                sesion_cruce = 'grupo-cruce'
                r = chat('Quiero una consulta general', {'intencion': 'reservar', 'servicio': 'consulta_general'},
                         sesion_cruce).json()
                assert 'mascota' in r['respuesta'].casefold()
                r = chat('Firulais', {'intencion': 'continuar', 'mascota': 'Firulais'}, sesion_cruce).json()
                assert r['estado_sesion']['mascota'] == 'Firulais' and 'fecha' in r['respuesta'].casefold()
                r = chat(f'El {fecha_cruce.isoformat()} a las 09:00',
                         {'intencion': 'continuar', 'fecha': fecha_cruce.isoformat(), 'hora': '09:00'},
                         sesion_cruce).json()
                assert 'nombre' in r['respuesta'].casefold()
                # El LLM confunde la respuesta y llena cliente Y mascota con el mismo valor.
                r = chat('Laura', {'intencion': 'fuera', 'cliente': 'Laura', 'mascota': 'Laura'}, sesion_cruce).json()
                assert r['estado_sesion']['cliente'] == 'Laura'
                assert r['estado_sesion']['mascota'] == 'Firulais'  # No se perdió con el cruce.
                r = chat('CONFIRMAR', sesion=sesion_cruce).json()
                registrado = api.get('/reservas/' + r['estado_sesion']['ultimo_codigo']).json()
                assert registrado['cliente'] == 'Laura' and registrado['mascota'] == 'Firulais'
                print('OK: no se cruzan el nombre del cliente y el de la mascota en un mensaje suelto.')

                # Un horario puede ocuparse entre el resumen y la confirmación.
                chat('Reservar', extraccion)
                assert api.post('/reservas', json=datos).status_code == 201
                assert chat('CONFIRMAR').status_code == 409
                assert 'pendiente' not in main.SESIONES['grupo-1']
                # Si la base falla, la API no confirma nada y no deja filas a medias.
                antes = main.agenda.listar()
                with patch.object(main.agenda, 'conexion', side_effect=sqlite3.OperationalError('Prueba de disco')):
                    assert api.post('/reservas', json={**datos, 'hora': '11:00'}).status_code == 503
                assert main.agenda.listar() == antes
                # Un archivo que no es una base SQLite tampoco se convierte en una confirmación exitosa.
                main.agenda.ruta.write_bytes(b'esto no es una base de datos')
                assert api.post('/reservas', json={**datos, 'hora': '11:00'}).status_code == 503
                assert api.get('/reservas/' + codigo2).status_code == 503
                print('OK: API, SQLite, confirmaciones, correcciones, sesiones, concurrencia, cancelación y fallos de almacenamiento.')
        finally:
            main.agenda = original
            main.SESIONES.clear()


if __name__ == '__main__':
    probar()
