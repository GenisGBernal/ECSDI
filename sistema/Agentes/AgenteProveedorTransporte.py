# -*- coding: utf-8 -*-
"""
filename: AgenteProveedorTransporte

Antes de ejecutar hay que añadir la raiz del proyecto a la variable PYTHONPATH

Agente que obtiene metodos de transporte

@author: daniel
"""

from datetime import datetime
from multiprocessing import Process, Queue
import logging
import argparse
import random
import uuid
from multiprocessing import Process, Queue
import logging
import argparse
import random

from flask import Flask, request
from rdflib import XSD, Graph, Namespace, Literal
from rdflib.namespace import FOAF, RDF

from AgentUtil.ACL import ACL
from AgentUtil.FlaskServer import shutdown_server
from AgentUtil.ACLMessages import build_message, send_message, getAgentInfo, get_message_properties
from AgentUtil.Agent import Agent
from AgentUtil.Logging import config_logger
from AgentUtil.DSO import DSO
from AgentUtil.Util import gethostname
import socket

from AgentUtil.ACLMessages import registerAgent
from AgentUtil.OntoNamespaces import ECSDI

from amadeus import Client, ResponseError

__author__ = 'javier'

AMADEUS_KEY = 'EiHVAHxxhgGwlEPZTZ4flG42U1x5QvMI'
AMADEUS_SECRET = 'n32zEDo4N2CAAtLB'

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

# Global transporteDB triplestore
transporteDB = Graph()

transporte = ECSDI['avion']

# Cola de comunicacion entre procesos
cola1 = Queue()


def register_message():
    """
    Envia un mensaje de registro al servicio de registro
    usando una performativa Request y una accion Register del
    servicio de directorio

    :return:
    """

    logger.info('Nos registramos')

    gr = registerAgent(AgenteProveedorTransporte, AgenteDirectorio, DSO.AgenteProveedorTransporte, getMessageCount())
    return gr


def generadorVuelosEnElPasado(dia_partida, dia_retorno, lugar_partida, lugar_llegada):
    flight_id = str(uuid.uuid4())
    flight_price = 100

    identificador = ECSDI[flight_id]

    transporteDB.add((ECSDI[identificador], ECSDI.identificador, Literal(flight_id, datatype=XSD.string)))
    transporteDB.add((ECSDI[identificador], ECSDI.precio, Literal(flight_price, datatype=XSD.float)))
    transporteDB.add((ECSDI[identificador], ECSDI.viaje_transporte, transporte))
    transporteDB.add((ECSDI[identificador], ECSDI.LugarVueloDePartida, Literal(lugar_partida, datatype=XSD.string)))
    transporteDB.add((ECSDI[identificador], ECSDI.LugarVueloDeLlegada, Literal(lugar_llegada, datatype=XSD.string)))
    transporteDB.add((ECSDI[identificador], ECSDI.DiaVueloDePartida, Literal(dia_partida, datatype=XSD.string)))
    transporteDB.add((ECSDI[identificador], ECSDI.DiaVueloDeRetorno, Literal(dia_retorno, datatype=XSD.string)))


def obtener_transporte(sujeto, gm):
    logger.info("Entramos en OBTENER_TRANSPORTE---------------------------")
    logger.info(gm.serialize(format='turtle'))

    dia_partida = gm.value(subject=sujeto, predicate=ECSDI.DiaDePartida)
    dia_retorno = gm.value(subject=sujeto, predicate=ECSDI.DiaDeRetorno)
    lugar_partida = gm.value(subject=sujeto, predicate=ECSDI.LugarDePartida)
    lugar_llegada = gm.value(subject=sujeto, predicate=ECSDI.LugarDeLlegada)

    logger.info("Dia partida: " + str(dia_partida))
    logger.info("Dia retorno: " + str(dia_retorno))
    logger.info("Lugar de partida: " + str(lugar_partida))
    logger.info("Lugar de llegada: " + str(lugar_llegada))

    remote_transporte_search(dia_partida, dia_retorno, lugar_partida, lugar_llegada)

    gr = fetch_queried_data(dia_partida, dia_retorno, lugar_partida, lugar_llegada)

    IAA = Namespace('IAActions')
    gr.bind('foaf', FOAF)
    gr.bind('iaa', IAA)
    sujeto = ECSDI['Transporte-' + str(getMessageCount())]
    gr.add((sujeto, RDF.type, ECSDI.viaje_transporte))

    logger.info(gr.serialize(format='turtle'))

    return build_message(gr, ACL['inform'], sender=AgenteProveedorTransporte.uri, msgcnt=getMessageCount(),
                         content=sujeto)


def fetch_queried_data(dia_partida, dia_retorno, lugar_partida, lugar_llegada):
    logger.info("Entramos en FETCH_QUEIRED_DATA---------------------------")

    global transporteDB

    logger.info(transporteDB.serialize(format='turtle'))

    flights_matching = f"""
             SELECT ?identificador ?precio
        WHERE {{
            ?billete ECSDI:viaje_transporte ?viaje_transporte_param ;
                     ECSDI:identificador ?identificador ;
                     ECSDI:precio ?precio ;
                     ECSDI:DiaVueloDePartida ?dia_partida_param ;
                     ECSDI:DiaVueloDeRetorno ?dia_retorno_param ;
                     ECSDI:LugarVueloDePartida ?lugar_partida_param ;
                     ECSDI:LugarVueloDeLlegada ?lugar_llegada_param .
            FILTER (?viaje_transporte_param = <{transporte}>
                    && ?dia_partida_param = "{dia_partida}"
                    && ?dia_retorno_param = "{dia_retorno}"
                    && ?lugar_partida_param = "{lugar_partida}"
                    && ?lugar_llegada_param = "{lugar_llegada}")
        }}
        """
    logger.info(flights_matching)

    resultsQuery = transporteDB.query(
        flights_matching,
        initNs={'ECSDI': ECSDI})

    gr = Graph()
    search_count = 0
    logger.info('Vuelos encontrados: ' + str(len(resultsQuery)))
    for row in resultsQuery:
        search_count += 1
        identificador = row['identificador']
        precio = row['precio']

        logger.info('Identificador:', identificador)
        logger.info('Precio:', precio)
        logger.info('---')
        gr.add((ECSDI[identificador], ECSDI.identificador, Literal(identificador, datatype=XSD.string)))
        gr.add((ECSDI[identificador], ECSDI.viaje_transporte, transporte))
        gr.add((ECSDI[identificador], ECSDI.precio, Literal(precio, datatype=XSD.float)))
        gr.add((ECSDI[identificador], ECSDI.LugarVueloDePartida, Literal(lugar_partida, datatype=XSD.string)))
        gr.add((ECSDI[identificador], ECSDI.LugarVueloDeLlegada, Literal(lugar_llegada, datatype=XSD.string)))
        gr.add((ECSDI[identificador], ECSDI.DiaVueloDePartida, Literal(dia_partida, datatype=XSD.string)))
        gr.add((ECSDI[identificador], ECSDI.DiaVueloDeRetorno, Literal(dia_retorno, datatype=XSD.string)))

    logger.info(gr.serialize(format='turtle'))
    logger.info("salimos de FETCH_QUEIRED_DATA---------------------------")

    return gr


def remote_transporte_search(dia_partida, dia_retorno, lugar_partida, lugar_llegada):
    logger.info("Entramos en REMOTE_TRANSPORT_SEARACH----------------------")
    global transporteDB

    # cityDeparture = 'LON'
    # cityArrival = 'BCN'
    # departureDate='2023-09-01'
    # returnDate='2023-09-15'
    logger.info('Dia partida: ' + dia_partida)
    logger.info('Dia retorno: ' + dia_retorno)
    logger.info('Lugar partida: ' + lugar_partida)
    logger.info('Lugar llegada: ' + lugar_partida)

    if datetime.strptime(dia_partida, '%Y-%m-%d') < datetime.now():
        generadorVuelosEnElPasado(dia_partida, dia_retorno, lugar_partida, lugar_llegada)
        logger.info("Fecha de partida anterior a la actual, se devolvera vuelo nulo")

    else:
        response = amadeus.shopping.flight_offers_search.get(
            originLocationCode=lugar_partida,
            destinationLocationCode=lugar_llegada,
            departureDate=dia_partida,
            returnDate=dia_retorno,
            adults=1,
            currencyCode='EUR',
            max=10)

        logger.info("TOTAL NUMBER OF FLIGHTS: " + str(len(response.data)))

        for f in response.data:
            flight_id = str(uuid.uuid4())
            flight_price = float(f['price']['grandTotal'])

            identificador = ECSDI[flight_id]

            transporteDB.add((ECSDI[identificador], ECSDI.identificador, Literal(flight_id, datatype=XSD.string)))
            transporteDB.add((ECSDI[identificador], ECSDI.precio, Literal(flight_price, datatype=XSD.float)))
            transporteDB.add((ECSDI[identificador], ECSDI.viaje_transporte, transporte))
            transporteDB.add((ECSDI[identificador], ECSDI.LugarVueloDePartida, Literal(lugar_partida, datatype=XSD.string)))
            transporteDB.add((ECSDI[identificador], ECSDI.LugarVueloDeLlegada, Literal(lugar_llegada, datatype=XSD.string)))
            transporteDB.add((ECSDI[identificador], ECSDI.DiaVueloDePartida, Literal(dia_partida, datatype=XSD.string)))
            transporteDB.add((ECSDI[identificador], ECSDI.DiaVueloDeRetorno, Literal(dia_retorno, datatype=XSD.string)))

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

    Asumimos que se reciben siempre acciones que se refieren a lo que puede hacer
    el agente (buscar con ciertas restricciones, reservar)
    Las acciones se mandan siempre con un Request
    Prodriamos resolver las busquedas usando una performativa de Query-ref
    """
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
        gr = build_message(Graph(), ACL['not-understood'], sender=AgenteProveedorTransporte.uri,
                           msgcnt=getMessageCount())
    else:
        # Obtenemos la performativa
        perf = msgdic['performative']

        if perf != ACL.request:
            # Si no es un request, respondemos que no hemos entendido el mensaje
            gr = build_message(Graph(), ACL['not-understood'], sender=AgenteProveedorTransporte.uri,
                               msgcnt=getMessageCount())
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
                    gr = build_message(Graph(), ACL['not-understood'], sender=AgenteProveedorTransporte.uri,
                                       msgcnt=getMessageCount())

            else:
                print('No content')
                gr = build_message(Graph(), ACL['not-understood'], sender=AgenteProveedorTransporte.uri,
                                   msgcnt=getMessageCount())
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
    ab1 = Process(target=agentbehavior1, args=(cola1,))
    ab1.start()

    # Ponemos en marcha el servidor
    app.run(host=hostname, port=port)

    # Esperamos a que acaben los behaviors
    ab1.join()
    logger.info('The End')
