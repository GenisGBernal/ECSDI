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
from AgentUtil.ACLMessages import build_message, clean_graph, send_message, get_message_properties
from AgentUtil.Agent import Agent
from AgentUtil.Logging import config_logger
from AgentUtil.DSO import DSO
from AgentUtil.Util import gethostname
import socket

from AgentUtil.ACLMessages import registerAgent
from AgentUtil.OntoNamespaces import ECSDI

from amadeus import Client, ResponseError

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

parser.add_argument('--bhost', help="Host del Banco")
parser.add_argument('--bport', type=int, help="Puerto de comunicacion del Banco")

# Logging
logger = config_logger(level=1)

# parsing de los parametros de la linea de comandos
args = parser.parse_args()

# Configuration stuff
if args.port is None:
    port = 9007
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


if args.bport is None:
    bport = 9008
else:
    bport = args.bport

if args.bhost is None:
    bhostname = socket.gethostname()
else:
    bhostname = args.bhost

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
AgenteCobrador = Agent('AgenteCobrador',
                                    agn.AgenteCobrador,
                                    'http://%s:%d/comm' % (hostaddr, port),
                                    'http://%s:%d/Stop' % (hostaddr, port))

# Directory agent address
AgenteDirectorio = Agent('AgenteDirectorio',
                       agn.Directory,
                       'http://%s:%d/Register' % (dhostname, dport),
                       'http://%s:%d/Stop' % (dhostname, dport))


# Datos API Banco
AgenteBanco = Agent('AgenteBanco',
                                    agn.AgenteBanco,
                                    'http://%s:%d/comm' % (bhostname, bport),
                                    'http://%s:%d/Stop' % (bhostname, bport))


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

    gr = registerAgent(AgenteCobrador, AgenteDirectorio, DSO.AgenteCobrador, getMessageCount())
    return gr



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

def se_accepta(viaje_sujeto, viaje_content, price):
    gmess = Graph()
    IAA = Namespace('IAActions')
    gmess.bind('foaf', FOAF)
    gmess.bind('iaa', IAA)
    gmess.bind('ECSDI', ECSDI)

    gmess += viaje_content

    sujeto = agn['TomaCobroAceptado-' + str(getMessageCount())]
    gmess.add((sujeto, RDF.type, ECSDI.TomaCobroAcceptado))
    gmess.add((sujeto, ECSDI.tiene_viaje, viaje_sujeto))
    gmess.add((sujeto, ECSDI.precio_total, Literal(price, datatype=XSD.float)))
    return gmess

def se_rechaza(viaje_sujeto, viaje_content, price):
    gmess = Graph()
    IAA = Namespace('IAActions')
    gmess.bind('foaf', FOAF)
    gmess.bind('iaa', IAA)
    gmess.bind('ECSDI', ECSDI)

    gmess += viaje_content

    sujeto = agn['TomaCobroRechazado-' + str(getMessageCount())]
    gmess.add((sujeto, RDF.type, ECSDI.TomaCobroRechazado))
    gmess.add((sujeto, ECSDI.tiene_viaje, viaje_sujeto))
    gmess.add((sujeto, ECSDI.precio_total, Literal(price, datatype=XSD.float)))
    return gmess


def process_payment(gm, content):
    print("Processing payment")
    tarjeta = gm.value(subject=content, predicate=ECSDI.numero_tarjeta)
    price_to_pay = gm.value(subject=content, predicate=ECSDI.precio_total)
    print("Price to pay: ", price_to_pay)

    # Get the payment info


    le_viaje = None
    juice_trip = clean_graph(gm)
    for a, _, _ in juice_trip.triples((None, RDF.type , ECSDI.PeticionDeViaje)):
        le_viaje = a

    if le_viaje is None: return build_message(Graph(), ACL['not-understood'], sender=AgenteCobrador.uri, msgcnt=getMessageCount())


    message_subject = gm.value(predicate=RDF.type, object=ECSDI.QuieroCobrarViaje)
    if message_subject is not None:
        juice_trip.remove((message_subject, None, None))


    # Logica de se accepta o rechaza

    gmess = Graph()
    IAA = Namespace('IAActions')
    gmess.bind('foaf', FOAF)
    gmess.bind('iaa', IAA)
    gmess.bind('ECSDI', ECSDI)


    # price_to_pay = gm.value(subject=content, predicate=ECSDI.precio_total)
    # tarjeta = gm.value(subject=content, predicate=ECSDI.numero_tarjeta)

    subject_tx = ECSDI['Tx-' + str(getMessageCount())]
    gmess.add((subject_tx, RDF.type, ECSDI.Transaccion))
    gmess.add((subject_tx, ECSDI.numero_tarjeta, Literal(tarjeta, datatype=XSD.string)))
    gmess.add((subject_tx, ECSDI.precio_total, Literal(price_to_pay, datatype=XSD.float)))

    to_send = build_message(gmess, perf=ACL.request, sender=AgenteCobrador.uri, receiver=AgenteBanco.uri,
                            msgcnt=getMessageCount(), content=subject_tx)
    
    print("Sending message to bank:")
    print(gmess.serialize(format='turtle'))
    
    # Enviar mensaje al banco
    resp = send_message(to_send, AgenteBanco.address)
    acceptado = resp.value(predicate=RDF.type, object=ECSDI.Confirmacion)

    if acceptado is None:
        return se_rechaza(le_viaje, juice_trip, price_to_pay)
    else:
        return se_accepta(le_viaje, juice_trip, price_to_pay)



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

    logger.info('Peticion de cobro recibida')

    # Extraemos el mensaje y creamos un grafo con el
    message = request.args['content']
    gm = Graph()
    gm.parse(data=message, format='xml')

    msgdic = get_message_properties(gm)
    print("I got this message:", gm.serialize(format='turtle'))

    # Comprobamos que sea un mensaje FIPA ACL
    if msgdic is None:
        # Si no es, respondemos que no hemos entendido el mensaje
        gr = build_message(Graph(), ACL['not-understood'], sender=AgenteCobrador.uri, msgcnt=getMessageCount())
    else:
        # Obtenemos la performativa
        perf = msgdic['performative']

        if perf != ACL.request:
            # Si no es un request, respondemos que no hemos entendido el mensaje
            gr = build_message(Graph(), ACL['not-understood'], sender=AgenteCobrador.uri, msgcnt=getMessageCount())
        else:
            # Extraemos el objeto del contenido que ha de ser una accion de la ontologia de acciones del agente
            # de registro

            # Averiguamos el tipo de la accion
            if 'content' in msgdic:
                content = msgdic['content']
                accion = gm.value(subject=content, predicate=RDF.type)

                if accion == ECSDI.QuieroCobrarViaje:
                    logger.info('Peticion de Cobro recibida')

                    gr = process_payment(gm, content)
                    
                else:
                    # Si no es ninguna de las acciones conocontentcidas, respondemos que no hemos entendido el mensaje
                    gr = build_message(Graph(), ACL['not-understood'], sender=AgenteCobrador.uri, msgcnt=getMessageCount())

            else:
                print('No content')
                gr = build_message(Graph(), ACL['not-understood'], sender=AgenteCobrador.uri, msgcnt=getMessageCount())
    
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
