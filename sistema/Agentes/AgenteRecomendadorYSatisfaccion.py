# -*- coding: utf-8 -*-
"""
filename: AgenteRecomendadorYSatisfaccion

Antes de ejecutar hay que añadir la raiz del proyecto a la variable PYTHONPATH

Agente que recomienda viajes y recoge valoraciones

@author: daniel
"""
from datetime import datetime as time_converter
from multiprocessing import Process
import logging
import argparse
from flask import Flask, render_template, request
from rdflib.namespace import FOAF, RDF

from multiprocessing import Process, Queue
import logging
import argparse
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

__author__ = 'daniel'

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
    port = 9011
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
AgenteRecomendadorYSatisfaccion = Agent('AgenteRecomendadorYSatisfaccion',
                                        agn.AgenteRecomendadorYSatisfaccion,
                                        'http://%s:%d/comm' % (hostaddr, port),
                                        'http://%s:%d/Stop' % (hostaddr, port))

# Directory agent address
AgenteDirectorio = Agent('AgenteDirectorio',
                         agn.Directory,
                         'http://%s:%d/Register' % (dhostname, dport),
                         'http://%s:%d/Stop' % (dhostname, dport))

# Global satisfaccionDB y viajesFinalizadosDB triplestore
satisfaccionDB = Graph()

viajesFinalizadosDB = Graph()
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

    gr = registerAgent(AgenteRecomendadorYSatisfaccion, AgenteDirectorio, DSO.AgenteRecomendadorYSatisfaccion,
                       getMessageCount())
    return gr


# def generar_peticion_de_viaje(usuario, lugarDePartida, diaPartida, diaRetorno, grado_ludica, grado_cultural,
#                               grado_festivo):
#     agentePlanificador = getAgentInfo(DSO.AgentePlanificador, DirectoryAgent, AgenteContratador, getMessageCount())
#
#     lugarDeLlegada = 'BCN'
#
#     gmess = Graph()
#     IAA = Namespace('IAActions')
#     gmess.bind('foaf', FOAF)
#     gmess.bind('iaa', IAA)
#     sujeto = agn['PeticiónDeViaje-' + str(getMessageCount())]
#     gmess.add((sujeto, RDF.type, ECSDI.PeticionDeViaje))
#     gmess.add((sujeto, ECSDI.Usuario, Literal(usuario, datatype=XSD.string)))
#     gmess.add((sujeto, ECSDI.LugarDePartida, Literal(lugarDePartida, datatype=XSD.string)))
#     gmess.add((sujeto, ECSDI.LugarDeLlegada, Literal(lugarDeLlegada, datatype=XSD.string)))
#     gmess.add((sujeto, ECSDI.DiaDePartida, Literal(diaPartida, datatype=XSD.string)))
#     gmess.add((sujeto, ECSDI.DiaDeRetorno, Literal(diaRetorno, datatype=XSD.string)))
#     gmess.add((sujeto, ECSDI.grado_ludica, Literal(grado_ludica, datatype=XSD.integer)))
#     gmess.add((sujeto, ECSDI.grado_cultural, Literal(grado_cultural, datatype=XSD.integer)))
#     gmess.add((sujeto, ECSDI.grado_festiva, Literal(grado_festivo, datatype=XSD.integer)))
#
#     msg = build_message(gmess, perf=ACL.request,
#                         sender=AgenteContratador.uri,
#                         receiver=agentePlanificador.uri,
#                         msgcnt=getMessageCount(),
#                         content=sujeto)
#
#     log.info("Petición de viaje al AgentePlanificador")
#     gr = send_message(msg, agentePlanificador.address)
#     log.info("Respuesta recibida")
#     return gr

def guardarViajesFinalizados(sujeto, gm):
    for s, p, o in gm:
        if p == ECSDI.ViajeFinalizado:
            viajesFinalizadosDB.add((s, ECSDI.viajeValorado, Literal(False, datatype=XSD.boolean)))
        viajesFinalizadosDB.add((s, p, o))

    viajesFinalizadosDB.serialize(format='turtle')
    return Graph() # TODO: Devolver algo

@app.route("/respuesta-propuesta-viaje", methods=['POST'])
def recibir_respuesta_propuesta_viaje():
    if request.method == 'POST':
        respuesta = request.form['respuesta']
        if respuesta == "si":

            # TODO: Llamada a cobro

            # TODO: Llamada viajes confirmados

            return render_template('viaje_confirmado.html')
        else:
            return render_template('iface.html')


def obtener_viajes_no_valorados_usuario(usuario):
    global viajesFinalizadosDB

    query = f"""
        SELECT ?viaje ?lugarDePartida ?lugarDeLlegada ?diaDePartida ?diaDeRetorno ?precio ?grado_ludica ?grado_cultural ?grado_festivo
        WHERE {{
            ?viaje RDF:type ECSDI:ViajeFinalizado ;
                            ECSDI:viajeValorado ?viajeValorado_param ;
                            ECSDI:Usuario ?usuario_param ;
                            ECSDI:LugarDePartida ?lugarDePartida ;
                            ECSDI:LugarDeLlegada ?lugarDeLlegada ;
                            ECSDI:DiaDePartida ?diaDePartida ;
                            ECSDI:DiaDeRetorno ?diaDeRetorno ;
                            ECSDI:precio_total ?precio ;
                            ECSDI:grado_ludica ?grado_ludica ;
                            ECSDI:grado_cultural ?grado_cultural ;
                            ECSDI:grado_festivo ?grado_festivo .
            FILTER (?usuario_param = {Literal(usuario, datatype=XSD.string)} &&
                    ?viajeValorado_param = {Literal(False, datatype=XSD.boolean)})
        }}
        """

    logger.info(query)

    resultsQuery = viajesFinalizadosDB.query(
        query,
        initNs={'ECSDI': ECSDI, 'RDF': RDF})

    viajes_a_valorar = []
    search_count = 0
    logger.info('Viajes por valorar encontrados: ' + str(len(resultsQuery)))
    for row in resultsQuery:
        datos_viaje = {'viaje': row['viaje'], 'lugarDePartida': row['lugarDePartida'],
                       'lugarDeLlegada': row['lugarDeLlegada'], 'diaDePartida': row['diaDePartida'],
                       'diaDeRetorno': row['diaDeRetorno'], 'precio': row['precio'],
                       'grado_ludica': row['grado_ludica'], 'grado_cultural': row['grado_cultural'],
                       'grado_festivo': row['grado_festivo']}
        viajes_a_valorar.append(datos_viaje)

        viajesFinalizadosDB.remove((ECSDI[row['viaje']], ECSDI.viajeValorado, Literal(False, datatype=XSD.boolean)))
        viajesFinalizadosDB.add((ECSDI[row['viaje']], ECSDI.viajeValorado, Literal(True, datatype=XSD.boolean)))

        search_count += 1

    logger.info(viajesFinalizadosDB.parse(format='turtle'))

    return viajes_a_valorar

@app.route("/encuesta_finalizada", methods=['GET'])
def browser_iface_encuesta_satisfaccion_finalizada():
    return render_template('encuesta_satisfaccion_finalizada.html')

@app.route("/encuesta_satisfaccion", methods=['GET', 'POST'])
def browser_iface_encuesta_satisfaccion():
    """
    Permite la comunicacion con el agente via un navegador
    via un formulario
    """

    if request.method == 'GET':
        return render_template('pedir_usuario.html')
    else:
        usuario = request.form['Usuario']

        # if grado_ludica + grado_cultural + grado_festivo == 0:
        #     return render_template('iface.html',
        #                            error_message='Se debe escoger un mínimo de algo en algun tipo de actividad')

        viajes_no_valorados_usuario = obtener_viajes_no_valorados_usuario(usuario=usuario)

        return render_template('encuesta_satisfaccion.html', viajes_no_valorados_usuario=viajes_no_valorados_usuario)


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
        gr = build_message(Graph(), ACL['not-understood'], sender=AgenteRecomendadorYSatisfaccion.uri,
                           msgcnt=getMessageCount())
    else:
        # Obtenemos la performativa
        perf = msgdic['performative']

        if perf != ACL.request:
            # Si no es un request, respondemos que no hemos entendido el mensaje
            gr = build_message(Graph(), ACL['not-understood'], sender=AgenteRecomendadorYSatisfaccion.uri,
                               msgcnt=getMessageCount())
        else:
            # Extraemos el objeto del contenido que ha de ser una accion de la ontologia de acciones del agente
            # de registro

            # Averiguamos el tipo de la accion
            if 'content' in msgdic:
                sujeto = msgdic['content']
                accion = gm.value(subject=sujeto, predicate=RDF.type)

                if accion == ECSDI.TomaViajeFinalizado:
                    logger.info('Peticion de viajes finalizados recibida')
                    gr = guardarViajesFinalizados(sujeto, gm)
                else:
                    # Si no es ninguna de las acciones conocontentcidas, respondemos que no hemos entendido el mensaje
                    gr = build_message(Graph(), ACL['not-understood'], sender=AgenteRecomendadorYSatisfaccion.uri,
                                       msgcnt=getMessageCount())

            else:
                print('No content')
                gr = build_message(Graph(), ACL['not-understood'], sender=AgenteRecomendadorYSatisfaccion.uri,
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


def inicializarViajesFinalizadosDataTesing():
    global viajesFinalizadosDB

    viajesFinalizadosDB.add((ECSDI['viaje1'], RDF.type, ECSDI['ViajeFinalizado']))
    viajesFinalizadosDB.add((ECSDI['viaje1'], ECSDI.viajeValorado, Literal(False, datatype=XSD.boolean)))
    viajesFinalizadosDB.add((ECSDI['viaje1'], ECSDI.Usuario, Literal('daniel', datatype=XSD.string)))
    viajesFinalizadosDB.add((ECSDI['viaje1'], ECSDI.DiaDePartida, Literal('2019-05-01', datatype=XSD.date)))
    viajesFinalizadosDB.add((ECSDI['viaje1'], ECSDI.DiaDeLlegada, Literal('2019-05-05', datatype=XSD.date)))
    viajesFinalizadosDB.add((ECSDI['viaje1'], ECSDI.precio_total, Literal(100, datatype=XSD.float)))
    viajesFinalizadosDB.add((ECSDI['viaje1'], ECSDI.LugarDeSalida, Literal('BCN', datatype=XSD.string)))
    viajesFinalizadosDB.add((ECSDI['viaje1'], ECSDI.LugarDeLlegada, Literal('MAD', datatype=XSD.string)))
    viajesFinalizadosDB.add((ECSDI['viaje1'], ECSDI.grado_ludica, Literal(0, datatype=XSD.integer)))
    viajesFinalizadosDB.add((ECSDI['viaje1'], ECSDI.grado_cultural, Literal(1, datatype=XSD.integer)))
    viajesFinalizadosDB.add((ECSDI['viaje1'], ECSDI.grado_festivo, Literal(2, datatype=XSD.integer)))

    viajesFinalizadosDB.add((ECSDI['viaje2'], RDF.type, ECSDI['ViajeFinalizado']))
    viajesFinalizadosDB.add((ECSDI['viaje2'], ECSDI.viajeValorado, Literal(True, datatype=XSD.boolean)))
    viajesFinalizadosDB.add((ECSDI['viaje2'], ECSDI.Usuario, Literal('daniel', datatype=XSD.string)))
    viajesFinalizadosDB.add((ECSDI['viaje2'], ECSDI.DiaDePartida, Literal('2019-05-01', datatype=XSD.date)))
    viajesFinalizadosDB.add((ECSDI['viaje2'], ECSDI.DiaDeLlegada, Literal('2019-05-05', datatype=XSD.date)))
    viajesFinalizadosDB.add((ECSDI['viaje2'], ECSDI.precio_total, Literal(100, datatype=XSD.float)))
    viajesFinalizadosDB.add((ECSDI['viaje2'], ECSDI.LugarDeSalida, Literal('NYC', datatype=XSD.string)))
    viajesFinalizadosDB.add((ECSDI['viaje2'], ECSDI.LugarDeLlegada, Literal('MAD', datatype=XSD.string)))
    viajesFinalizadosDB.add((ECSDI['viaje2'], ECSDI.grado_ludica, Literal(0, datatype=XSD.integer)))
    viajesFinalizadosDB.add((ECSDI['viaje2'], ECSDI.grado_cultural, Literal(1, datatype=XSD.integer)))
    viajesFinalizadosDB.add((ECSDI['viaje2'], ECSDI.grado_festivo, Literal(2, datatype=XSD.integer)))

    logger.info(viajesFinalizadosDB.serialize(format='turtle'))

if __name__ == '__main__':
    inicializarViajesFinalizadosDataTesing() # TODO data para testing
    # Ponemos en marcha los behaviors
    ab1 = Process(target=agentbehavior1, args=(cola1,))
    ab1.start()

    # Ponemos en marcha el servidor
    app.run(host=hostname, port=port)

    # Esperamos a que acaben los behaviors
    ab1.join()
    logger.info('The End')
