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


def generar_peticion_de_viaje(usuario, lugarDePartida, diaPartida, diaRetorno, grado_ludica, grado_cultural, grado_festivo):

    agentePlanificador = getAgentInfo(DSO.AgentePlanificador, DirectoryAgent, AgenteContratador, getMessageCount())

    gmess = Graph()
    IAA = Namespace('IAActions')
    gmess.bind('foaf', FOAF)
    gmess.bind('iaa', IAA)
    sujeto = agn['PeticiónDeViaje-' + str(getMessageCount())]
    gmess.add((sujeto, RDF.type, ECSDI.PeticionDeViaje))
    gmess.add((sujeto, ECSDI.Usuario, Literal(usuario, datatype=XSD.string)))
    gmess.add((sujeto, ECSDI.LugarDePartida, Literal(lugarDePartida, datatype=XSD.string)))
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


    msgdic = get_message_properties(gr)


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
        diaSalida = request.form['DiaDePartida']
        diaRetorno = request.form['DiaDeRetorno']
        grado_ludica = request.form['grado_ludica']
        grado_cultural = request.form['grado_cultural']
        grado_festivo = request.form['grado_festivo']

        if diaRetorno < diaSalida:
            return render_template('iface.html', error_message='La fecha de retorno no puede ser anterior a la de salida')
        
        if grado_ludica + grado_cultural + grado_festivo == 0:
            return render_template('iface.html', error_message='Se debe escoger un mínimo de algo en algun tipo de actividad')

        generar_peticion_de_viaje(
            usuario=usuario, 
            lugarDePartida=lugarDePartida, 
            diaSalida=diaSalida, 
            diaRetorno=diaRetorno, 
            grado_ludica=grado_ludica, 
            grado_cultural=grado_cultural, 
            grado_festivo=grado_festivo)
        

        
        return render_template('riface.html', user="hoa", mess="df")


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
