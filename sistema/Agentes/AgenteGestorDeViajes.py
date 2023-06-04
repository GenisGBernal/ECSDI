# -*- coding: utf-8 -*-
"""
filename: SimpleInfoAgent

Antes de ejecutar hay que añadir la raiz del proyecto a la variable PYTHONPATH

Agente que se registra como agente de hoteles y espera peticiones

@author: javier
"""

import asyncio
from multiprocessing import Process, Queue
import logging
import argparse
import multiprocessing
import datetime

from flask import Flask, request, render_template
from rdflib import Graph, Namespace, Literal, XSD
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
    port = 9009
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
AgenteGestorDeViajes = Agent('AgenteGestorDeViajes',
                                    agn.AgenteGestorDeViajes,
                                    'http://%s:%d/comm' % (hostaddr, port),
                                    'http://%s:%d/Stop' % (hostaddr, port))

# Directory agent address
AgenteDirectorio = Agent('AgenteDirectorio',
                       agn.Directory,
                       'http://%s:%d/Register' % (dhostname, dport),
                       'http://%s:%d/Stop' % (dhostname, dport))

# Global viajesConfirmadosDB triplestore
viajesConfirmadosDB = Graph()
viajesConfirmadosDB.bind('ECSDI', ECSDI)

# ESTO ES SOLO PARA PODER VER LOS CAMBIOS EN MODO DEV, EN LA VIDA REAL SE ENVIARIA UNA NOTIFICACION AL USUARIO
registroCambiosViaje = []

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

    gr = registerAgent(AgenteGestorDeViajes, AgenteDirectorio, DSO.AgenteGestorDeViajes, getMessageCount())
    return gr


@app.route("/finaliza-viajes-manual", methods=['GET'])
def browser_acualiza_estado_manual():

    if request.method == 'GET':

        n_viajes_finalizados = actualizar_estado_viajes_finalizados()

        return render_template('n_viajes_finalizados.html', n_viajes_finalizados=str(n_viajes_finalizados))


@app.route("/iface", methods=['GET'])
def browser_iface():

    if request.method == 'GET':

        return render_template('ver_cambios_viaje.html', registro_cambios_viaje=registroCambiosViaje)
    

def obtener_actividad_cubierta():

    agenteProveedorActividades = getAgentInfo(DSO.AgenteProveedorActividades, AgenteDirectorio, AgenteGestorDeViajes, getMessageCount())

    gmess = Graph()
    IAA = Namespace('IAActions')
    gmess.bind('foaf', FOAF)
    gmess.bind('iaa', IAA)
    gmess.bind('ECSDI', ECSDI)
    sujeto = agn['PeticiónDeActividadCubierta-' + str(getMessageCount())]
    gmess.add((sujeto, RDF.type, ECSDI.ActividadCubierta))

    msg = build_message(gmess, perf=ACL.request,
                        sender=AgenteGestorDeViajes.uri,
                        receiver=agenteProveedorActividades.uri,
                        msgcnt=getMessageCount(),
                        content=sujeto)
    
    gr = send_message(msg, agenteProveedorActividades.address)

    return clean_graph(gr)


def obtener_usuario_actividades(sujeto_actividades_hoy):
    sujeto_actividades = viajesConfirmadosDB.value(predicate=ECSDI.ActividadesOrdenadas, object=sujeto_actividades_hoy)
    sujeto_viaje = viajesConfirmadosDB.value(predicate=ECSDI.ViajeActividades, object=sujeto_actividades)
    usuario = viajesConfirmadosDB.value(subject=sujeto_viaje, predicate=ECSDI.Usuario).toPython()
    return usuario


def cambiar_actividad(sujeto_actividades_hoy, franja):

    global viajesConfirmadosDB
    fecha_hoy = datetime.date.today()

    sujeto_actividad_franja = viajesConfirmadosDB.value(subject=sujeto_actividades_hoy, predicate=franja)
    tipo_actividad_franja = viajesConfirmadosDB.value(subject=sujeto_actividad_franja, predicate=ECSDI.tipo_actividad)
    
    if tipo_actividad_franja != ECSDI.tipo_ludica:

        logger.info("Cambiando actividad franja: " + franja + " - por actividad cubierta")

        usuario = obtener_usuario_actividades(sujeto_actividades_hoy)
        tipo_antigua_actividad = viajesConfirmadosDB.value(subject=sujeto_actividad_franja, predicate=ECSDI.tipo_actividad)
        subtipo_antigua_actividad = viajesConfirmadosDB.value(subject=sujeto_actividad_franja, predicate=ECSDI.subtipo_actividad).toPython()
        nombre_antigua_actividad = viajesConfirmadosDB.value(subject=sujeto_actividad_franja, predicate=ECSDI.nombre_actividad).toPython()

        nueva_actividad = obtener_actividad_cubierta()
        sujeto_nueva_actividad = nueva_actividad.value(predicate=RDF.type, object=ECSDI.actividad)
       
        tipo_nueva_actividad = nueva_actividad.value(subject=sujeto_nueva_actividad, predicate=ECSDI.tipo_actividad)
        subtipo_nueva_actividad = nueva_actividad.value(subject=sujeto_nueva_actividad, predicate=ECSDI.subtipo_actividad).toPython()
        nombre_nueva_actividad = nueva_actividad.value(subject=sujeto_nueva_actividad, predicate=ECSDI.nombre_actividad).toPython()

        viajesConfirmadosDB.remove((sujeto_actividades_hoy, franja, None))
        viajesConfirmadosDB.remove((sujeto_actividad_franja, None, None))

        viajesConfirmadosDB.add((sujeto_actividades_hoy, franja, sujeto_nueva_actividad))
        viajesConfirmadosDB += nueva_actividad

        registro_cambio_actividad = {
            "dia": str(fecha_hoy),
            "usuario": usuario,
            "franja": franja,
            "tipo_antigua_actividad": tipo_antigua_actividad,
            "subtipo_antigua_actividad": subtipo_antigua_actividad,
            "nombre_antigua_actividad": nombre_antigua_actividad,
            "tipo_nueva_actividad": tipo_nueva_actividad,
            "subtipo_nueva_actividad": subtipo_nueva_actividad,
            "nombre_nueva_actividad": nombre_nueva_actividad
        }
        registroCambiosViaje.append(registro_cambio_actividad)



def cambiar_actividades_segun_lluvia(sujeto, gm):

    hay_lluvia_matina = gm.value(subject=sujeto, predicate=ECSDI.hay_lluvia_matina).toPython()
    hay_lluvia_tarde = gm.value(subject=sujeto, predicate=ECSDI.hay_lluvia_tarde).toPython()
    hay_lluvia_noche = gm.value(subject=sujeto, predicate=ECSDI.hay_lluvia_noche).toPython()

    logger.info("Hay lluvia por la mañana: " + str(hay_lluvia_matina))
    logger.info("Hay lluvia por la tarde: " + str(hay_lluvia_tarde))
    logger.info("Hay lluvia por la noche: " + str(hay_lluvia_noche))

    fecha_hoy = datetime.date.today()

    if hay_lluvia_matina or hay_lluvia_tarde or hay_lluvia_noche:

        for sujeto_actividades_hoy,_,_ in viajesConfirmadosDB.triples((None, ECSDI.dia, Literal(fecha_hoy, datatype=XSD.string))):

            if hay_lluvia_matina:
                cambiar_actividad(sujeto_actividades_hoy, ECSDI.actividad_manana)

            if hay_lluvia_tarde:
                cambiar_actividad(sujeto_actividades_hoy, ECSDI.actividad_tarde)

            if hay_lluvia_noche:
                cambiar_actividad(sujeto_actividades_hoy, ECSDI.actividad_noche)

    print(viajesConfirmadosDB.serialize(format='turtle'))

    return build_message(Graph(),
        ACL['inform'],
        sender=AgenteGestorDeViajes.uri,
        msgcnt=getMessageCount())


@app.route("/stop")
def stop():
    """
    Entrypoint que para el agente

    :return:
    """
    tidyup()
    shutdown_server()
    return "Parando Servidor"


def registra_viaje_confirmado(sujeto_viaje, gm):

    global viajesConfirmadosDB

    logger.info("Registrando viaje confirmado")

    gm_cleaned = clean_graph(gm)
    viajesConfirmadosDB += gm_cleaned

    return build_message(Graph(),
        ACL['inform'],
        sender=AgenteGestorDeViajes.uri,
        msgcnt=getMessageCount())
    

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

    # Comprobamos que sea un mensaje FIPA ACL
    if msgdic is None:
        # Si no es, respondemos que no hemos entendido el mensaje
        gr = build_message(Graph(), ACL['not-understood'], sender=AgenteGestorDeViajes.uri, msgcnt=getMessageCount())
    else:
        # Obtenemos la performativa
        perf = msgdic['performative']

        if perf != ACL.request:
            # Si no es un request, respondemos que no hemos entendido el mensaje
            gr = build_message(Graph(), ACL['not-understood'], sender=AgenteGestorDeViajes.uri, msgcnt=getMessageCount())
        else:
            # Extraemos el objeto del contenido que ha de ser una accion de la ontologia de acciones del agente
            # de registro

            # Averiguamos el tipo de la accion
            if 'content' in msgdic:
                sujeto = msgdic['content']
                accion = gm.value(subject=sujeto, predicate=RDF.type)

                if accion == ECSDI.ViajePendienteDeConfirmacion:
                    logger.info('Peticion de registrar viaje confirmado')
                    gr = registra_viaje_confirmado(sujeto, gm)
                
                elif accion == ECSDI.prevision:
                    logger.info('Recibida prediccion meterologica')
                    gr = cambiar_actividades_segun_lluvia(sujeto, gm)       
                    

    logger.info('Respondemos a la peticion')

    return gr.serialize(format='xml')


def tidyup():
    """
    Acciones previas a parar el agente

    """
    global cola1
    cola1.put(0)


def actualizar_estado_viajes_finalizados():

    global viajesConfirmadosDB

    logger.info("Actualizando estado de viajes finalizados")

    fecha_hoy = datetime.date.today()

    sujetos_viajes_finalizados = list(viajesConfirmadosDB.query("""
            SELECT DISTINCT ?sujeto
            WHERE {
                ?sujeto ECSDI:DiaDeRetorno ?tipo .
                FILTER (?tipo < ?var)
            }
        """, 
        initNs = {'ECSDI': ECSDI},
        initBindings={'var': Literal(fecha_hoy, datatype=XSD.string)}
    ))

    if len(sujetos_viajes_finalizados) > 0:
        # TODO: HACER CUANDO AGENTE LISTO
        # agenteRecomendadorYSatisfaccion = getAgentInfo(DSO.AgenteRecomendadorYSatisfaccion, AgenteDirectorio, AgenteGestorDeViajes, getMessageCount())

        gmess = Graph()
        IAA = Namespace('IAActions')
        gmess.bind('foaf', FOAF)
        gmess.bind('iaa', IAA)
        gmess.bind('ECSDI', ECSDI)

        for sujeto_viaje_finalizado in sujetos_viajes_finalizados:

            for sujeto, predicado, objeto in viajesConfirmadosDB.triples((sujeto_viaje_finalizado, None, None)):
                if (predicado == RDF.type):
                    gmess.add((sujeto, RDF.type, ECSDI.ViajeFinalizado))
                else:
                    gmess.add((sujeto, predicado, objeto))
            
            viajesConfirmadosDB.remove((sujeto_viaje_finalizado, None, None))

        # msg = build_message(gmess, perf=ACL.request,
        #             sender=AgenteGestorDeViajes.uri,
        #             receiver=agenteRecomendadorYSatisfaccion.uri,
        #             msgcnt=getMessageCount(),
        #             content=sujeto)
        # gr = send_message(msg, agenteRecomendadorYSatisfaccion.address)

    logger.info("Viajes actualizados: " + str(len(sujetos_viajes_finalizados)))

    return len(sujetos_viajes_finalizados)


async def temporizador():
    while True:
        actualizar_estado_viajes_finalizados()
        await asyncio.sleep(60*60*24)


def agentbehavior1(cola):
    """
    Un comportamiento del agente

    :return:
    """

    # Registramos el agente
    gr = register_message()


def agentbehavior2():
    """
    Un comportamiento del agente

    :return:
    """

    loop = asyncio.get_event_loop()
    loop.run_until_complete(temporizador())


if __name__ == '__main__':


    # Ponemos en marcha los behaviors
    ab1 = Process(target=agentbehavior1, args=(cola1,))
    ab1.start()

    ab2 = multiprocessing.Process(target=agentbehavior2)
    ab2.start()

    # Ponemos en marcha el servidor
    app.run(host=hostname, port=port)

    # Esperamos a que acaben los behaviors
    ab1.join()
    ab2.join()
    logger.info('The End')
