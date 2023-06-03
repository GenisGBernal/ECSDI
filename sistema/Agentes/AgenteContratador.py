# -*- coding: utf-8 -*-
"""
filename: SimplePersonalAgent

Antes de ejecutar hay que añadir la raiz del proyecto a la variable PYTHONPATH

Ejemplo de agente que busca en el directorio y llama al agente obtenido


Created on 09/02/2014

@author: javier
"""

from multiprocessing import Process
import logging
import argparse

from flask import Flask, render_template, request
from rdflib import XSD, Graph, Literal, Namespace
from rdflib.namespace import FOAF, RDF

from AgentUtil.ACL import ACL
from AgentUtil.DSO import DSO
from AgentUtil.FlaskServer import shutdown_server
from AgentUtil.ACLMessages import build_message, send_message, getAgentInfo, get_message_properties
from AgentUtil.Agent import Agent
from AgentUtil.Logging import config_logger
from AgentUtil.Util import gethostname
import socket

from AgentUtil.OntoNamespaces import ECSDI


__author__ = 'javier'

# Definimos los parametros de la linea de comandos
parser = argparse.ArgumentParser()
parser.add_argument('--open', help="Define si el servidor est abierto al exterior o no", action='store_true',
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
    port = 9003
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
AgenteContratador = Agent('AgenteContratador',
                       agn.AgenteContratador,
                       'http://%s:%d/comm' % (hostaddr, port),
                       'http://%s:%d/Stop' % (hostaddr, port))

# Directory agent address
DirectoryAgent = Agent('DirectoryAgent',
                       agn.Directory,
                       'http://%s:%d/Register' % (dhostname, dport),
                       'http://%s:%d/Stop' % (dhostname, dport))

# Global dsgraph triplestore
dsgraph = Graph()

def obtener_info_actividad(sujeto, g, franja):
    nombre = g.value(subject=sujeto, predicate=ECSDI.nombre_actividad).toPython()
    tipo_actividad = g.value(subject=sujeto, predicate=ECSDI.tipo_actividad)
    subtipo_actividad = g.value(subject=sujeto, predicate=ECSDI.subtipo_actividad).toPython()

    if tipo_actividad == ECSDI.tipo_ludica:
        tipo_actividad = 'Lúdica'
    elif tipo_actividad == ECSDI.tipo_cultural:
        tipo_actividad = 'Cultural'    
    else:
        tipo_actividad = 'Festiva'

    return {
        'franja': franja,
        'nombre': nombre,
        'tipo_actividad': tipo_actividad,
        'subtipo_actividad': subtipo_actividad
    }

def obtener_actividades(grafo_viaje):

    lista_actividades_completa = []
    for sujeto_dia_actividad_ordenada, _, _ in grafo_viaje.triples((None, RDF.type, ECSDI.actividades_ordenadas)):

        lista_actividades_un_dia = []

        sujeto_actividad_manana = grafo_viaje.value(subject=sujeto_dia_actividad_ordenada, predicate=ECSDI.actividad_manana)
        actividad_mañana = obtener_info_actividad(sujeto_actividad_manana, grafo_viaje, 'mañana')
        lista_actividades_un_dia.append(actividad_mañana)

        sujeto_actividad_tarde = grafo_viaje.value(subject=sujeto_dia_actividad_ordenada, predicate=ECSDI.actividad_tarde)
        actividad_tarde = obtener_info_actividad(sujeto_actividad_tarde, grafo_viaje, 'tarde')
        lista_actividades_un_dia.append(actividad_tarde)

        sujeto_actividad_noche = grafo_viaje.value(subject=sujeto_dia_actividad_ordenada, predicate=ECSDI.actividad_noche)
        actividad_noche = obtener_info_actividad(sujeto_actividad_noche, grafo_viaje, 'noche')
        lista_actividades_un_dia.append(actividad_noche)

        actividad_un_dia = {
            'dia':  grafo_viaje.value(subject=sujeto_dia_actividad_ordenada, predicate=ECSDI.dia).toPython(),
            'actividades': lista_actividades_un_dia
        }
        lista_actividades_completa.append(actividad_un_dia)

    lista_actividades_completa = sorted(lista_actividades_completa, key=lambda x: x['dia'])

    return lista_actividades_completa


def generar_peticion_de_viaje(usuario, lugarDePartida, diaPartida, diaRetorno, grado_ludica, grado_cultural, grado_festivo):

    agentePlanificador = getAgentInfo(DSO.AgentePlanificador, DirectoryAgent, AgenteContratador, getMessageCount())

    lugarDeLlegada = 'BCN'

    gmess = Graph()
    IAA = Namespace('IAActions')
    gmess.bind('foaf', FOAF)
    gmess.bind('iaa', IAA)
    sujeto = agn['PeticiónDeViaje-' + str(getMessageCount())]
    gmess.add((sujeto, RDF.type, ECSDI.PeticionDeViaje))
    gmess.add((sujeto, ECSDI.Usuario, Literal(usuario, datatype=XSD.string)))
    gmess.add((sujeto, ECSDI.LugarDePartida, Literal(lugarDePartida, datatype=XSD.string)))
    gmess.add((sujeto, ECSDI.LugarDeLlegada, Literal(lugarDeLlegada, datatype=XSD.string)))
    gmess.add((sujeto, ECSDI.DiaDePartida, Literal(diaPartida, datatype=XSD.string)))
    gmess.add((sujeto, ECSDI.DiaDeRetorno, Literal(diaRetorno, datatype=XSD.string)))
    gmess.add((sujeto, ECSDI.grado_ludica, Literal(grado_ludica, datatype=XSD.integer)))
    gmess.add((sujeto, ECSDI.grado_cultural, Literal(grado_cultural, datatype=XSD.integer)))
    gmess.add((sujeto, ECSDI.grado_festiva, Literal(grado_festivo, datatype=XSD.integer)))


    msg = build_message(gmess, perf=ACL.request,
                        sender=AgenteContratador.uri,
                        receiver=agentePlanificador.uri,
                        msgcnt=getMessageCount(),
                        content=sujeto)
    
    log.info("Petición de viaje al AgentePlanificador")
    gr = send_message(msg, agentePlanificador.address)
    log.info("Respuesta recibida")
    return gr


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
    

@app.route("/iface", methods=['GET', 'POST'])
def browser_iface():
    """
    Permite la comunicacion con el agente via un navegador
    via un formulario
    """

    if request.method == 'GET':
        return render_template('iface.html')
    else:
        usuario = request.form['Usuario']
        lugarDePartida = request.form['LugarDePartida']
        diaPartida = request.form['DiaDePartida']
        diaRetorno = request.form['DiaDeRetorno']
        grado_ludica = request.form['grado_ludica']
        grado_cultural = request.form['grado_cultural']
        grado_festivo = request.form['grado_festivo']

        if diaRetorno < diaPartida:
            return render_template('iface.html', error_message='La fecha de retorno no puede ser anterior a la de salida')
        
        if grado_ludica + grado_cultural + grado_festivo == 0:
            return render_template('iface.html', error_message='Se debe escoger un mínimo de algo en algun tipo de actividad')

        gr = generar_peticion_de_viaje(
            usuario=usuario, 
            lugarDePartida=lugarDePartida, 
            diaPartida=diaPartida, 
            diaRetorno=diaRetorno, 
            grado_ludica=grado_ludica, 
            grado_cultural=grado_cultural, 
            grado_festivo=grado_festivo)
        
        print(gr.serialize(format='turtle'))
        
        
        actividades = obtener_actividades(gr)

        return render_template('propuesta_viaje.html', actividades=actividades)


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
    """
    return "Hola"


def tidyup():
    """
    Acciones previas a parar el agente

    """
    pass

if __name__ == '__main__':
    # Ponemos en marcha el servidor
    app.run(host=hostname, port=port)

    # Esperamos a que acaben los behaviors
    logger.info('The End')
