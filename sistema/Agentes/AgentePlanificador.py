# -*- coding: utf-8 -*-
"""
filename: SimpleInfoAgent

Antes de ejecutar hay que añadir la raiz del proyecto a la variable PYTHONPATH

Agente que se registra como agente de hoteles y espera peticiones

@author: javier
"""

from multiprocessing import Pipe, Process, Queue
import logging
import argparse

from flask import Flask, request
from rdflib import XSD, Graph, Namespace, Literal
from rdflib.namespace import FOAF, RDF

from AgentUtil.ACL import ACL
from AgentUtil.FlaskServer import shutdown_server
from AgentUtil.ACLMessages import build_message, send_message, get_message_properties, getAgentInfo, clean_graph
from AgentUtil.Agent import Agent
from AgentUtil.Logging import config_logger
from AgentUtil.DSO import DSO
from AgentUtil.Util import gethostname
import socket

from AgentUtil.ACLMessages import registerAgent
from AgentUtil.OntoNamespaces import ECSDI


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
    # TODO: PONER PUERTO QUE SEA UNICO 
    port = 9002
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
AgentePlanificador = Agent('AgentePlanificador',
                                    agn.AgentePlanificador,
                                    'http://%s:%d/comm' % (hostaddr, port),
                                    'http://%s:%d/Stop' % (hostaddr, port))

# Directory agent address
AgenteDirectorio = Agent('AgenteDirectorio',
                       agn.Directory,
                       'http://%s:%d/Register' % (dhostname, dport),
                       'http://%s:%d/Stop' % (dhostname, dport))

# Global dsgraph triplestore
dsgraph = Graph()

def register_message():
    """
    Envia un mensaje de registro al servicio de registro
    usando una performativa Request y una accion Register del
    servicio de directorio

    :param gmess:
    :return:
    """

    logger.info('Nos registramos')

    gr = registerAgent(AgentePlanificador, AgenteDirectorio, DSO.AgentePlanificador, getMessageCount())
    return gr


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

def obtener_hospedaje(p_salida, primerDia, últimoDia, cityCode):
    gmess = Graph()
    gmess.bind('ECSDI', ECSDI)
    hospedaje_mess_uri = ECSDI['QuieroHospedaje' + str(getMessageCount())]
    gmess.add((hospedaje_mess_uri, RDF.type, ECSDI.QuieroHospedaje))
    gmess.add((hospedaje_mess_uri, ECSDI.viaje_ciudad, ECSDI[cityCode]))

    # TODO: Llamar para obtener viajes, transporte y hospedaje en paralelo
    agenteProveedorHospedaje = getAgentInfo(DSO.AgenteProveedorHospedaje, AgenteDirectorio, AgentePlanificador, getMessageCount())

    response_hosp = send_message(build_message(gmess, ACL['request'], sender=AgentePlanificador.uri, content= hospedaje_mess_uri, msgcnt=getMessageCount()) , agenteProveedorHospedaje.address)

    response = clean_graph(response_hosp)
    p_salida.send(response.serialize(format='xml'))
    p_salida.close()

    return


    msgdic_hospedaje = get_message_properties(response_hosp)

    if msgdic_hospedaje is not None and msgdic_hospedaje['performative'] == ACL.inform and 'content' in msgdic_hospedaje:
        content_hosp = msgdic_hospedaje['content']
        hotels = response_hosp.triples((content_hosp, ECSDI.viaje_hospedaje, None))
        for _,_,hotel in hotels:
            h_name = response_hosp.value(subject=hotel, predicate=ECSDI.identificador)
            h_price = response_hosp.value(subject=hotel, predicate=ECSDI.precio)
            print("RESULTADO HOSPEDAJE:", h_name, h_price)

    pass

def obtener_transporte(lugarDePartida, primerDia, últimoDia):
    pass

def obtener_actividades(p_salida, fecha_llegada, fecha_salida, grado_ludica, grado_cultural, grado_festivo):

    global g_actividades
    
    agenteProveedorActividades = getAgentInfo(DSO.AgenteProveedorActividades, AgenteDirectorio, AgentePlanificador, getMessageCount())
    
    gmess = Graph()
    IAA = Namespace('IAActions')
    gmess.bind('foaf', FOAF)
    gmess.bind('iaa', IAA)
    sujeto = agn['PeticiónIntervaloDeActividades-' + str(getMessageCount())]
    gmess.add((sujeto, RDF.type, ECSDI.IntervaloDeActividades))
    gmess.add((sujeto, ECSDI.DiaDePartida, Literal(fecha_llegada, datatype=XSD.string)))
    gmess.add((sujeto, ECSDI.DiaDeRetorno, Literal(fecha_salida, datatype=XSD.string)))
    gmess.add((sujeto, ECSDI.grado_ludica, Literal(grado_ludica, datatype=XSD.integer)))
    gmess.add((sujeto, ECSDI.grado_cultural, Literal(grado_cultural, datatype=XSD.integer)))
    gmess.add((sujeto, ECSDI.grado_festiva, Literal(grado_festivo, datatype=XSD.integer)))

    msg = build_message(gmess, perf=ACL.request,
                        sender=AgentePlanificador.uri,
                        receiver=agenteProveedorActividades.uri,
                        msgcnt=getMessageCount(),
                        content=sujeto)

    gr = send_message(msg, agenteProveedorActividades.address)
    g_actividades = clean_graph(gr)

    p_salida.send(gr.serialize(format='xml'))
    p_salida.close()
    

def planificar_viaje(sujeto, gm):

    fecha_llegada = gm.value(subject=sujeto, predicate=ECSDI.DiaDePartida).toPython()
    fecha_salida = gm.value(subject=sujeto, predicate=ECSDI.DiaDeRetorno).toPython()
    grado_ludica = gm.value(subject=sujeto, predicate=ECSDI.grado_ludica).toPython()
    grado_cultural = gm.value(subject=sujeto, predicate=ECSDI.grado_cultural).toPython()
    grado_festivo = gm.value(subject=sujeto, predicate=ECSDI.grado_festiva).toPython()

    logger.info("Fecha llegada: " + fecha_llegada)
    logger.info("Fecha salida: " + fecha_salida)
    logger.info("Grado festivo: " + str(grado_festivo))
    logger.info("Grado cultural: " + str(grado_cultural))
    logger.info("Grado ludica: " + str(grado_ludica))

    

    p_actividades_salida, p_actividades_entrada = Pipe()
    p1 = Process(target=obtener_actividades, args=(p_actividades_entrada, fecha_llegada,fecha_salida,grado_ludica,grado_cultural,grado_festivo))
    p1.start()

    # p2 =
    # p2.start() def obtener_hospedaje(p_salida, primerDia, últimoDia, cityCode):
    cityCode = "LON"
    p_hospedaje_salida, p_hospedaje_entrada = Pipe()
    p2 = Process(target=obtener_hospedaje, args=(p_hospedaje_entrada, fecha_llegada, fecha_salida, cityCode))
    p2.start()

    
    # p3 = 
    # p3.start()

    g_actividades = Graph()
    g_actividades.parse(data=p_actividades_salida.recv(), format='xml')

    g_hospedaje = Graph()
    g_hospedaje.parse(data=p_hospedaje_salida.recv(), format='xml')

    p1.join()
    p2.join()
    # p3.join()


    gmess = Graph()
    IAA = Namespace('IAActions')
    gmess.bind('foaf', FOAF)
    gmess.bind('iaa', IAA)
    sujeto = agn['planificador/PlanificacionDeViaje-' + str(getMessageCount())]
    gmess.add((sujeto, RDF.type, ECSDI.ViajePendienteDeConfirmacion))

    gmess += g_actividades
    gmess += g_hospedaje

    return build_message(gmess, ACL['inform'], sender=AgentePlanificador.uri, msgcnt=getMessageCount(), content=sujeto)


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
        gr = build_message(Graph(), ACL['not-understood'], sender=AgentePlanificador.uri, msgcnt=getMessageCount())
    else:
        # Obtenemos la performativa
        perf = msgdic['performative']

        if perf != ACL.request:
            # Si no es un request, respondemos que no hemos entendido el mensaje
            gr = build_message(Graph(), ACL['not-understood'], sender=AgentePlanificador.uri, msgcnt=getMessageCount())
        else:
            # Extraemos el objeto del contenido que ha de ser una accion de la ontologia de acciones del agente
            # de registro

            # Averiguamos el tipo de la accion
            if 'content' in msgdic:
                sujeto = msgdic['content']
                accion = gm.value(subject=sujeto, predicate=RDF.type)

                if accion == ECSDI.PeticionDeViaje:
                    logger.info('Peticion de viaje')
                    gr = planificar_viaje(sujeto, gm)

    logger.info('Respondemos a la peticion')

    return gr.serialize(format='xml')


def tidyup():
    """
    Acciones previas a parar el agente

    """

def agentbehavior1():
    """
    Un comportamiento del agente

    :return:
    """
    # Registramos el agente
    gr = register_message()


if __name__ == '__main__':
    # Ponemos en marcha los behaviors
    ab1 = Process(target=agentbehavior1, args=())
    ab1.start()

    # Ponemos en marcha el servidor
    app.run(host=hostname, port=port)

    # Esperamos a que acaben los behaviors
    ab1.join()
    logger.info('The End')
