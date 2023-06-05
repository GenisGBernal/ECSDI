# -*- coding: utf-8 -*-
"""
filename: SimpleInfoAgent

Antes de ejecutar hay que añadir la raiz del proyecto a la variable PYTHONPATH

Agente que se registra como agente de hoteles y espera peticiones

@author: javier
"""

from multiprocessing import Process, Queue
import logging
import argparse

from flask import Flask, request
from rdflib import XSD, Graph, Namespace, Literal
from rdflib.namespace import FOAF, RDF

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
import random

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
    port = 9004
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
AgenteProveedorHospedaje = Agent('AgenteProveedorHospedaje',
                                    agn.AgenteProveedorHospedaje,
                                    'http://%s:%d/comm' % (hostaddr, port),
                                    'http://%s:%d/Stop' % (hostaddr, port))

# Directory agent address
AgenteDirectorio = Agent('AgenteDirectorio',
                       agn.Directory,
                       'http://%s:%d/Register' % (dhostname, dport),
                       'http://%s:%d/Stop' % (dhostname, dport))

# Global hospedajeDB triplestore
hospedajeDB = Graph()

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

    gr = registerAgent(AgenteProveedorHospedaje, AgenteDirectorio, DSO.AgenteProveedorHospedaje, getMessageCount())
    return gr


def remote_hospedaje_search(cityCode):
    global hospedajeDB

    cityCode = str(cityCode)[-3:]
    # Hotels query
    #cityCode = 'LON'
    response = amadeus.reference_data.locations.hotels.by_city.get(cityCode=cityCode)
    # amadeus.shopping.hotel_offers_search.get(cityCode='LON')
    city = ECSDI[cityCode]
    hospedajeDB.add((city, RDF.type, ECSDI.Ciudad))
    print("TOTAL NUMBER OF HOTELS: " + str(len(response.data)))
    for h in response.data:
        hotel_name = h['name']
        hotel_id = ECSDI['hotel/'+h['hotelId']]
        hospedajeDB.add((ECSDI[hotel_id], RDF.type, ECSDI.Hospedaje))
        hospedajeDB.add((ECSDI[hotel_id], ECSDI.identificador, Literal(hotel_name, datatype=XSD.string)))
        hospedajeDB.add((ECSDI[hotel_id], ECSDI.precio, Literal(random.randrange(100,200), datatype=XSD.float)))
        hospedajeDB.add((ECSDI[hotel_id], ECSDI.viaje_ciudad, city))

    


@app.route("/iface", methods=['GET', 'POST'])
def browser_iface():
    """content
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
    global mss_cnt

    logger.info('Peticion de informacion recibida')

    def process_hospedaje_search():
        # Recibimos una peticion de busqueda de hospedaje

        logger.info('Peticion de busqueda de hospedaje: ' + city)

        hotels_in_city = f"""
        SELECT ?hospedaje ?identificador ?precio 
        WHERE {{
            ?hospedaje rdf:type ECSDI:Hospedaje;
                        ECSDI:identificador ?identificador;
                        ECSDI:precio ?precio;
                        ECSDI:viaje_ciudad {'<'+city+'>'}.
        }}
        LIMIT 5   
        """

        

        city_search = hospedajeDB.query(hotels_in_city, initNs={'ECSDI': ECSDI})
        print("CITY SEARCH:", len(city_search))

        # This will be changed to a conditional
        if len(city_search) < 5:
            try:
                remote_hospedaje_search(city)
            except ResponseError as error:
                print(error)
                return build_message(Graph(),
                                    ACL.inform,
                                    sender=AgenteProveedorHospedaje.uri,
                                    msgcnt=mss_cnt)
        
        city_search = hospedajeDB.query(hotels_in_city, initNs={'ECSDI': ECSDI})
        print("2. CITY SEARCH:", city_search)

        if city_search is not None:
            for x in city_search:
                print("X:", x)

        if city_search is not None:
            gr = Graph()
            gr.bind('ECSDI', ECSDI)

            uri_mensaje = ECSDI['TomaHospedaje' + str(getMessageCount())]
            gr.add((uri_mensaje, RDF.type, ECSDI.TomaHospedaje))
            for res in city_search:
                
                hotel_uri, hotel_name, hotel_price = res

                print("HOTEL URI:", hotel_uri)

                

                gr.add((hotel_uri, RDF.type, ECSDI.Hospedaje))
                gr.add((hotel_uri, ECSDI.identificador, Literal(hotel_name, datatype=XSD.string)))
                gr.add((hotel_uri, ECSDI.precio, Literal(hotel_price, datatype=XSD.float)))
                gr.add((hotel_uri, ECSDI.viaje_ciudad, city))


                
                gr.add((uri_mensaje, ECSDI.viaje_hospedaje, hotel_uri))

                logger.info("Hospedaje encontrado: " + hotel_name)
                break
            return build_message(gr,
                                 ACL.inform,
                                 sender=AgenteProveedorHospedaje.uri,
                                 msgcnt=mss_cnt,
                                 content=uri_mensaje,)
        else:
            # Si no encontramos nada retornamos un inform sin contenido
            return build_message(Graph(),
                                ACL.inform,
                                sender=AgenteProveedorHospedaje.uri,
                                msgcnt=mss_cnt)

    # Extraemos el mensaje y creamos un grafo con el
    message = request.args['content']
    gm = Graph()
    gm.parse(data=message, format='xml')

    msgdic = get_message_properties(gm)
    print("I got this message:", gm.serialize(format='turtle'))

    # Comprobamos que sea un mensaje FIPA ACL
    if msgdic is None:
        # Si no es, respondemos que no hemos entendido el mensaje
        gr = build_message(Graph(), ACL['not-understood'], sender=AgenteProveedorHospedaje.uri, msgcnt=getMessageCount())
    else:
        # Obtenemos la performativa
        perf = msgdic['performative']

        if perf != ACL.request:
            # Si no es un request, respondemos que no hemos entendido el mensaje
            gr = build_message(Graph(), ACL['not-understood'], sender=AgenteProveedorHospedaje.uri, msgcnt=getMessageCount())
        else:
            # Extraemos el objeto del contenido que ha de ser una accion de la ontologia de acciones del agente
            # de registro

            # Averiguamos el tipo de la accion
            if 'content' in msgdic:
                content = msgdic['content']
                accion = gm.value(subject=content, predicate=RDF.type)
                city = gm.value(subject=content, predicate=ECSDI.viaje_ciudad)

                if accion == ECSDI.QuieroHospedaje:
                    logger.info('Peticion de Hospedaje')
                    gr = process_hospedaje_search()
                else:
                    # Si no es ninguna de las acciones conocontentcidas, respondemos que no hemos entendido el mensaje
                    gr = build_message(Graph(), ACL['not-understood'], sender=AgenteProveedorHospedaje.uri, msgcnt=getMessageCount())

            else:
                print('No content')
                gr = build_message(Graph(), ACL['not-understood'], sender=AgenteProveedorHospedaje.uri, msgcnt=getMessageCount())
    
    mss_cnt += 1
    logger.info('Respondemos a la peticion')
    print("RESPUESTA: ", gr.serialize(format='turtle'))

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
