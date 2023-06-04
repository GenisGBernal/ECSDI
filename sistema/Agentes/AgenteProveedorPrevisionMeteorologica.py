# -*- coding: utf-8 -*-
"""
filename: SimpleInfoAgent

Antes de ejecutar hay que añadir la raiz del proyecto a la variable PYTHONPATH

Agente que se registra como agente de hoteles y espera peticiones

@author: javier
"""

import asyncio
import datetime
from multiprocessing import Process, Queue
import logging
import argparse
import multiprocessing
import random

from flask import Flask, request, render_template
from rdflib import XSD, Graph, Namespace, Literal
from rdflib.namespace import FOAF, RDF
import requests

from AgentUtil.ACL import ACL
from AgentUtil.FlaskServer import shutdown_server
from AgentUtil.ACLMessages import build_message, send_message, get_message_properties, getAgentInfo
from AgentUtil.Agent import Agent
from AgentUtil.Logging import config_logger
from AgentUtil.DSO import DSO
from AgentUtil.Util import gethostname
import socket

from AgentUtil.ACLMessages import registerAgent
from AgentUtil.OntoNamespaces import ECSDI

from amadeus import Client, ResponseError

WEATHER_END_POINT = 'https://api.open-meteo.com/v1/forecast'

__author__ = 'javier'

# Definimos los parametros de la linea de comandos
parser = argparse.ArgumentParser()
parser.add_argument('--open', help="Define si el servidor esta abierto al exterior o no", action='store_true',
                    default=False)
parser.add_argument('--verbose', help="Genera un log de la comunicacion del servidor web", action='store_true',
                        default=False)
parser.add_argument('--port', type=int, help="Puerto de comunicacion del agente")
parser.add_argument('--dhost', help="Host del agente de directorio")
parser.add_argument('--dport', type=int, help="Puerto de comunicacion del agente de directorio")

# Logging
logger = config_logger(level=1)

# parsing de los parametros de la linea de comandos
args = parser.parse_args()

# Configuration stuff
if args.port is None:
    port = 9010
else:
    port = args.port

if args.open:
    hostname = '0.0.0.0'
    hostaddr = gethostname()
else:
    hostaddr = hostname = socket.gethostname()

print('DS Hostname =', hostaddr)

if args.dport is None:
    dport = 9000
else:
    dport = args.dport

if args.dhost is None:
    dhostname = socket.gethostname()
else:
    dhostname = args.dhost

# Flask stuff
app = Flask(__name__)
if not args.verbose:
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)

# Configuration constants and variables
agn = Namespace("http://www.agentes.org#")

# Contador de mensajes
mss_cnt = 0

def getMessageCount():
    global mss_cnt
    mss_cnt += 1
    return mss_cnt

# Datos del Agente
AgenteProveedorPrevisionMeteorologica = Agent('AgenteProveedorActivdades',
                                    agn.AgenteProveedorPrevisionMeteorologica,
                                    'http://%s:%d/comm' % (hostaddr, port),
                                    'http://%s:%d/Stop' % (hostaddr, port))

# Directory agent address
AgenteDirectorio = Agent('AgenteDirectorio',
                       agn.Directory,
                       'http://%s:%d/Register' % (dhostname, dport),
                       'http://%s:%d/Stop' % (dhostname, dport))

# Global actividadesDB triplestore
previsionMeterologicaDB = Graph()
previsionMeterologicaDB.bind('ECSDI', ECSDI)

# Cola de comunicacion entre procesos
cola1 = Queue()


def register_message():
    """
    Envia un mensaje de registro al servicio de registro
    usando una performativa Request y una accion Register del
    servicio de directorio

    :param gmess:
    :return:
    """

    logger.info('Nos registramos')

    gr = registerAgent(AgenteProveedorPrevisionMeteorologica, AgenteDirectorio, DSO.AgenteProveedorPrevisionMeteorologica, getMessageCount())
    return gr

@app.route("/stop")
def stop():
    """
    Entrypoint que para el agente

    :return:
    """
    tidyup()
    shutdown_server()
    return "Parando Servidor"


def tidyup():
    """
    Acciones previas a parar el agente

    """
    global cola1
    cola1.put(0)

@app.route("/iface", methods=['GET', 'POST'])
def browser_iface():

    if request.method == 'GET':
        return render_template('forzar_lluvia.html')
    else:
        forzar_lluvia_manana = request.form['forzar_lluvia_manana'] == '1'
        forzar_lluvia_tarde = request.form['forzar_lluvia_tarde'] == '1'
        forzar_lluvia_noche = request.form['forzar_lluvia_noche'] == '1'

        logger.info("Fornzando lluvia por la: Mañana " + str(forzar_lluvia_manana) + " - Tarde " + str(forzar_lluvia_tarde) + " - Noche " + str(forzar_lluvia_noche))

        obtener_prevision_meteorologica_para_el_dia(
            forzar_lluvia_manana=forzar_lluvia_manana,
            forzar_lluvia_tarde=forzar_lluvia_tarde,
            forzar_lluvia_noche=forzar_lluvia_noche)

        return render_template('forzar_lluvia.html', success_message="Lluvia forzada")


    

def hay_lluvia(codigo):
    return codigo > 40


def obtener_prevision_meteorologica_para_el_dia(forzar_lluvia_manana=False, forzar_lluvia_tarde=False, forzar_lluvia_noche=False):

    agenteGestorDeViajes = getAgentInfo(DSO.AgenteGestorDeViajes, AgenteDirectorio, AgenteProveedorPrevisionMeteorologica, getMessageCount())

    fecha_hoy = datetime.date.today()

    logger.info("Obteniendo previsión dia para hoy dia:" + str(fecha_hoy))

    r = requests.get(WEATHER_END_POINT, params={
        'latitude': 41.397896,
        'longitude': 2.165111,
        'start_date': str(fecha_hoy),
        'end_date': str(fecha_hoy),
        'hourly':'weathercode'
    })

    tiempo_por_horas = r.json()['hourly']['weathercode']

    
    hay_lluvia_matina = True if forzar_lluvia_manana else hay_lluvia(tiempo_por_horas[10])
    hay_lluvia_tarde = True if forzar_lluvia_tarde else hay_lluvia(tiempo_por_horas[18])
    hay_lluvia_noche = True if forzar_lluvia_noche else hay_lluvia(tiempo_por_horas[22])

    gmess = Graph()
    IAA = Namespace('IAActions')
    gmess.bind('foaf', FOAF)
    gmess.bind('iaa', IAA)
    gmess.bind('ECSDI', ECSDI)
    sujeto = ECSDI['PrevisionDeTiempo-' + str(getMessageCount())]
    gmess.add((sujeto, RDF.type, ECSDI.prevision))
    gmess.add((sujeto, ECSDI.hay_lluvia_matina, Literal(hay_lluvia_matina, datatype=XSD.boolean)))
    gmess.add((sujeto, ECSDI.hay_lluvia_tarde, Literal(hay_lluvia_tarde, datatype=XSD.boolean)))
    gmess.add((sujeto, ECSDI.hay_lluvia_noche, Literal(hay_lluvia_noche, datatype=XSD.boolean)))

    msg = build_message(gmess, perf=ACL.request,
                        sender=AgenteProveedorPrevisionMeteorologica.uri,
                        receiver=agenteGestorDeViajes.uri,
                        msgcnt=getMessageCount(),
                        content=sujeto)

    logger.info("Enviando predicción meteorologica")
    gr = send_message(msg, agenteGestorDeViajes.address)


async def temporizador():
    while True:
        obtener_prevision_meteorologica_para_el_dia()
        await asyncio.sleep(60*60*24)


def agentbehavior2():
    """
    Un comportamiento del agente

    :return:
    """

    loop = asyncio.get_event_loop()
    loop.run_until_complete(temporizador())



def agentbehavior1(cola):
    """
    Un comportamiento del agente

    :return:
    """
    # Registramos el agente
    gr = register_message()

    # Escuchando la cola hasta que llegue un 0
    fin = False
    while not fin:
        while cola.empty():
            pass
        v = cola.get()
        if v == 0:
            fin = True
        else:
            print(v)



if __name__ == '__main__':
    # Ponemos en marcha los behaviors
    # ab1 = Process(target=agentbehavior1, args=(cola1,))
    # ab1.start()

    ab2 = multiprocessing.Process(target=agentbehavior2)
    ab2.start()

    # Ponemos en marcha el servidor
    app.run(host=hostname, port=port)

    # Esperamos a que acaben los behaviors
    # ab1.join()
    ab2.join()
    logger.info('The End')
