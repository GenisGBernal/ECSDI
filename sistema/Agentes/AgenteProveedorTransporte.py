# -*- coding: utf-8 -*-
"""
filename: SimpleInfoAgent

Antes de ejecutar hay que añadir la raiz del proyecto a la variable PYTHONPATH

Agente que se registra como agente de hoteles y espera peticiones

@author: javier
"""

from datetime import datetime
from multiprocessing import Process, Queue
import logging
import argparse
import random
import uuid

from flask import Flask, request
from rdflib import XSD, Graph, Namespace, Literal
from rdflib.namespace import FOAF, RDF
import requests

from AgentUtil.ACL import ACL
from AgentUtil.FlaskServer import shutdown_server
from AgentUtil.ACLMessages import build_message, send_message, get_message_properties
from AgentUtil.Agent import Agent
from AgentUtil.Logging import config_logger
from AgentUtil.DSO import DSO
from AgentUtil.Util import gethostname
import socket

from AgentUtil.ACLMessages import registerAgent
from AgentUtil.OntoNamespaces import ECSDI

from amadeus import Client, ResponseError


__author__ = 'javier'

AMADEUS_KEY = '8zfjCOSbBMc4MgaOkibZ4ydWXxR4mljG'
AMADEUS_SECRET = 'yGTFfTOPGHNzIIZe'

amadeus = Client(
    client_id=AMADEUS_KEY,
    client_secret=AMADEUS_SECRET
)

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
    port = 9006
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
AgenteProveedorTransporte = Agent('AgenteProveedorTransporte',
                                    agn.AgenteProveedorTransporte,
                                    'http://%s:%d/comm' % (hostaddr, port),
                                    'http://%s:%d/Stop' % (hostaddr, port))

# Directory agent address
AgenteDirectorio = Agent('AgenteDirectorio',
                       agn.Directory,
                       'http://%s:%d/Register' % (dhostname, dport),
                       'http://%s:%d/Stop' % (dhostname, dport))

# Global actividadesDB triplestore
transporteDB = Graph()

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

    gr = registerAgent(AgenteProveedorTransporte, AgenteDirectorio, DSO.AgenteProveedorTransporte, getMessageCount())
    return gr

def obtener_transporte(sujeto, gm):
    fecha_llegada = gm.value(subject=sujeto, predicate=ECSDI.DiaDePartida)
    fecha_salida = gm.value(subject=sujeto, predicate=ECSDI.DiaDeRetorno)
    lugar_partida = gm.value(subject=sujeto, predicate=ECSDI.LugarDePartida)

    logger.info("Fecha llegada: " + fecha_llegada)
    logger.info("Fecha salida: " + fecha_salida)
    logger.info("Lugar de partida: " + str(lugar_partida))

    logger.info("Fecha llegada: " + fecha_llegada.toPython())
    logger.info("Fecha salida: " + fecha_salida.toPython())
    logger.info("Lugar de partida: " + str(lugar_partida).toPython())

    remote_transporte_search(fecha_llegada, fecha_salida, lugar_partida)

    gr = fetch_queried_data(fecha_llegada, fecha_salida, lugar_partida)

    IAA = Namespace('IAActions')
    gr.bind('foaf', FOAF)
    gr.bind('iaa', IAA)
    sujeto = ECSDI['Transporte-' + str(getMessageCount())]
    gr.add((sujeto, RDF.type, ECSDI.viaje_transporte))

    print(gr.serialize(format='turtle'))

    return build_message(gr, ACL['inform'], sender=AgenteProveedorActividades.uri, msgcnt=getMessageCount(), content=sujeto)

def fetch_queried_data(fechaLlegada, fechaSalida, lugarDePartida, lugarDeLlegada):
    global transporteDB

    search_count = 0

    flights_matching = f"""
    SELECT ?billete ?identificador ?precio
    WHERE {{
        ?billete rdf:type ECSDI:BilleteIdaVuelta;
                ECSDI:identifcador ?identificador;
                ECSDI:precio ?precio;
                ECSDI.LugarDePartida ?lugarDePartida_param))
                ECSDI.LugarDeLlegada ?lugarDeLlegada_param))
                ECSDI.DiaDePartida, ?fechaSalida_param))
                ECSDI.DiaDeRetorno, ?fechaLlegada_param))
    }}
    """
    logger.info(flights_matching)

    # Execute the query
    results = transporteDB.query(
        flights_matching,
        initNs={'ECSDI': ECSDI, 'rdf': RDF},
        initBindings={'lugarDePartida_param': lugarDePartida,
                        'lugarDeLlegada_param': lugarDeLlegada,
                        'fechaSalida_param': fechaSalida,
                        'fechaLlegada_param': fechaLlegada})

    gr = Graph()
    # Process the results
    for row in results:
        search_count += 1
        billete = row['billete']
        identificador = row['identificador']
        precio = row['precio']

        # Do something with the billete, identificador, and precio values
        logger.info('Billete:', billete)
        logger.info('Identificador:', identificador)
        logger.info('Precio:', precio)
        logger.info('---')

    return results

def remote_transporte_search(fechaLlegada, fechaSalida, lugarDePartida, lugarDeLlegada):
    global transporteDB

    # cityDeparture = 'LON'
    # cityArrival = 'BCN'
    # departureDate='2023-09-01'
    # returnDate='2023-09-15'
    cityDeparture = lugarDePartida.toPython()
    cityArrival = lugarDeLlegada.toPython()
    departureDate= fechaSalida.toPython()
    returnDate= fechaLlegada.toPython()
    transport = 'avion'
    currency='EUR'

    response = amadeus.shopping.flight_offers_search.get(
        originLocationCode=cityDeparture,
        destinationLocationCode=cityArrival,
        departureDate=departureDate,
        returnDate=returnDate,
        adults=1,
        currencyCode=currency,
        max=20)

    logger.info("TOTAL NUMBER OF FLIGHTS: " + str(len(response.data)))

    transporte = ECSDI[transport]
    # ciudadSalida = ECSDI[cityDeparture]
    # ciudadLlegada = ECSDI[cityArrival]
    # fechaSalida = ECSDI[departureDate]
    # fechaLlegada = ECSDI[returnDate]

    transporteDB.add((fechaSalida, RDF.type, ECSDI.Fecha))
    transporteDB.add((fechaLlegada, RDF.type, ECSDI.Fecha))
    transporteDB.add((lugarDePartida, RDF.type, ECSDI.Ciudad))
    transporteDB.add((lugarDeLlegada, RDF.type, ECSDI.Ciudad))
    transporteDB.add((transporte, RDF.type, ECSDI.Transporte))

    for f in response.data:
        flight_id = str(uuid.uuid4())
        flight_price= float(f['price']['grandTotal'])

        identificador = ECSDI[flight_id]

        transporteDB.add((ECSDI[identificador], ECSDI.identifcador, Literal(flight_id, datatype=XSD.string)))
        transporteDB.add((ECSDI[identificador], RDF.type, ECSDI.BilleteIdaVuelta))
        transporteDB.add((ECSDI[identificador], ECSDI.precio, Literal(flight_price, datatype=XSD.float)))
        transporteDB.add((ECSDI[identificador], ECSDI.viaje_transporte, transporte))
        transporteDB.add((ECSDI[identificador], ECSDI.LugarDePartida, lugarDePartida))
        transporteDB.add((ECSDI[identificador], ECSDI.LugarDeLlegada, lugarDeLlegada))
        transporteDB.add((ECSDI[identificador], ECSDI.DiaDePartida, fechaSalida))
        transporteDB.add((ECSDI[identificador], ECSDI.DiaDeRetorno, fechaLlegada))

    logger.info(transporteDB.serialize(format='turtle'))


@app.route("/iface", methods=['GET', 'POST'])
def browser_iface():
    """
    Permite la comunicacion con el agente via un navegador
    via un formulario
    """
    return 'Nothing to see here'


@app.route("/stop")
def stop():
    """
    Entrypoint que para el agente

    :return:
    """
    tidyup()
    shutdown_server()
    return "Parando Servidor"


@app.route("/comm")
def comunicacion():
    """
    Entrypoint de comunicacion del agente
    Simplemente retorna un objeto fijo que representa una
    respuesta a una busqueda de hotel

    Asumimos que se reciben siempre acciones que se refieren a lo que puede hacer
    el agente (buscar con ciertas restricciones, reservar)
    Las acciones se mandan siempre con un Request
    Prodriamos resolver las busquedas usando una performativa de Query-ref
    """
    global dsgraph
    global mss_cnt

    logger.info('Peticion de informacion recibida')

    # Extraemos el mensaje y creamos un grafo con el
    message = request.args['content']
    gm = Graph()
    gm.parse(data=message, format='xml')

    msgdic = get_message_properties(gm)

    gr = None

    # Comprobamos que sea un mensaje FIPA ACL
    if msgdic is None:
        # Si no es, respondemos que no hemos entendido el mensaje
        gr = build_message(Graph(), ACL['not-understood'], sender=AgenteProveedorTransporte.uri, msgcnt=getMessageCount())
    else:
        # Obtenemos la performativa
        perf = msgdic['performative']

        if perf != ACL.request:
            # Si no es un request, respondemos que no hemos entendido el mensaje
            gr = build_message(Graph(), ACL['not-understood'], sender=AgenteProveedorTransporte.uri, msgcnt=getMessageCount())
        else:
            # Extraemos el objeto del contenido que ha de ser una accion de la ontologia de acciones del agente
            # de registro

            # Averiguamos el tipo de la accion
            if 'content' in msgdic:
                sujeto = msgdic['content']
                accion = gm.value(subject=sujeto, predicate=RDF.type)

                if accion == ECSDI.QuieroTransporte:
                    logger.info('Peticion de Transporte')
                    gr = obtener_transporte(sujeto, gm)
                else:
                    # Si no es ninguna de las acciones conocontentcidas, respondemos que no hemos entendido el mensaje
                    gr = build_message(Graph(), ACL['not-understood'], sender=AgenteProveedorTransporte.uri, msgcnt=getMessageCount())

            else:
                print('No content')
                gr = build_message(Graph(), ACL['not-understood'], sender=AgenteProveedorTransporte.uri, msgcnt=getMessageCount())
    logger.info('Respondemos a la peticion')

    return gr.serialize(format='xml')


def tidyup():
    """
    Acciones previas a parar el agente

    """
    global cola1
    cola1.put(0)


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

    ab1 = Process(target=agentbehavior1, args=(cola1,))
    ab1.start()

    # Ponemos en marcha el servidor
    app.run(host=hostname, port=port)

    # Esperamos a que acaben los behaviors
    ab1.join()
    logger.info('The End')
