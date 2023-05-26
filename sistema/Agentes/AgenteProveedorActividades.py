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
    port = 9005
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
AgenteProveedorActividades = Agent('AgenteProveedorActivdades',
                                    agn.AgenteProveedorActivdades,
                                    'http://%s:%d/comm' % (hostaddr, port),
                                    'http://%s:%d/Stop' % (hostaddr, port))

# Directory agent address
AgenteDirectorio = Agent('AgenteDirectorio',
                       agn.Directory,
                       'http://%s:%d/Register' % (dhostname, dport),
                       'http://%s:%d/Stop' % (dhostname, dport))

# Global actividadesDB triplestore
actividadesDB = Graph()

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

    gr = registerAgent(AgenteProveedorActividades, AgenteDirectorio, DSO.AgenteProveedorActividades, getMessageCount())
    return gr

def obtener_diferencia_en_dias(fecha1, fecha2):
    formato = "%Y-%m-%d"

    fecha1_obj = datetime.strptime(fecha1, formato).date()
    fecha2_obj = datetime.strptime(fecha2, formato).date()

    return abs((fecha2_obj - fecha1_obj).days) + 1


def repartir_actividades(grado_ludica, grado_cultural, grado_festivo, n_actividades):
    total_grado = grado_ludica + grado_cultural + grado_festivo

    n_actividades_ludicas = (grado_ludica / total_grado) * n_actividades
    n_actividades_culturales = (grado_cultural / total_grado) * n_actividades
    n_actividades_festivas = (grado_festivo / total_grado) * n_actividades

    suma_partes = int(n_actividades_ludicas) + int(n_actividades_culturales) + int(n_actividades_festivas)
    diferencia = n_actividades - suma_partes

    if diferencia > 0:
        n_actividades_ludicas += diferencia

    return int(n_actividades_ludicas), int(n_actividades_culturales), int(n_actividades_festivas)


def obtener_actividad(tipo_actividad):

    id_actividades = actividadesDB.query("""
        SELECT DISTINCT ?sujeto ?
        WHERE {
            ?sujeto ECSDI:tipo_actividad ?tipo .
            FILTER (?tipo = ?var)
        }
    """, 
    initNs = {'ECSDI', ECSDI},
    initBindings={'var': tipo_actividad}
    )

    # TODO: Hacer que elija uno random o por tags
    primer_resultado = id_actividades.fetchone()

    if primer_resultado:
        return primer_resultado['id']
    


    if tipo_actividad == ECSDI.tipo_festiva:
        response = amadeus.reference_data.locations.points_of_interest.get(latitude=41.397896, longitude=2.165111, radius=5, categories="NIGHTLIFE")
        for r in response.data:
            actividadesDB.add((ECSDI['actividad/'+r['id']], RDF.type, ECSDI.actividad))
            actividadesDB.add((ECSDI['actividad/'+r['id']], ECSDI.tipo_actividad, ECSDI.tipo_festiva))
            actividadesDB.add((ECSDI['actividad/'+r['id']], ECSDI.subtipo_actividad, Literal(r['subType'], datatype=XSD.string)))
            actividadesDB.add((ECSDI['actividad/'+r['id']], ECSDI.nombre_actividad, Literal(r['name'], datatype=XSD.string)))
            for tag in r['tags']:
                actividadesDB.add((ECSDI['actividad/'+r['id']], ECSDI.tag_actividad, Literal(tag, datatype=XSD.string)))
            

    # registrar en el grafo
    # devolver nuevo id
    pass


def obtener_actividades_un_dia(dia, tipo_actividad_manana, tipo_actividad_tarde, tipo_actividad_noche):

    gr = Graph()
    IAA = Namespace('IAActions')
    gr.bind('foaf', FOAF)
    gr.bind('iaa', IAA)
    sujeto = ECSDI['ActividadesUnDia-' + str(getMessageCount())]
    gr.add((sujeto, RDF.type, ECSDI.actividades_ordenadas))
    gr.add((sujeto, ECSDI.dia, dia))

    gr_actividad_de_manana = obtener_actividad(tipo_actividad=tipo_actividad_manana)
    sujeto_actividad_de_manana = gr_actividad_de_manana.value(predicate=RDF.type, object=ECSDI.actividad)
    gr.add((sujeto_actividad_de_manana, RDF.type, ECSDI.actividad_manana))

    gr_actividad_de_tarde = obtener_actividad(tipo_actividad=tipo_actividad_tarde)
    sujeto_actividad_de_tarde = gr_actividad_de_tarde.value(predicate=RDF.type, object=ECSDI.actividad)
    gr.add((sujeto_actividad_de_tarde, RDF.type, ECSDI.actividad_tarde))

    gr_actividad_de_noche = obtener_actividad(tipo_actividad=tipo_actividad_noche)
    sujeto_actividad_de_noche = gr_actividad_de_noche.value(predicate=RDF.type, object=ECSDI.actividad)
    gr.add((sujeto_actividad_de_noche, RDF.type, ECSDI.actividad_noche))

    return gr + gr_actividad_de_manana + gr_actividad_de_tarde + gr_actividad_de_manana


def obtener_intervalo_actividades(sujeto, gm):

    fecha_llegada = gm.value(subject=sujeto, predicate=ECSDI.DiaDePartida)
    fecha_salida = gm.value(subject=sujeto, predicate=ECSDI.DiaDeRetorno)
    grado_ludica = gm.value(subject=sujeto, predicate=ECSDI.grado_ludica)
    grado_cultural = gm.value(subject=sujeto, predicate=ECSDI.grado_cultural)
    grado_festivo = gm.value(subject=sujeto, predicate=ECSDI.grado_festiva)

    duracion_vacaciones = obtener_diferencia_en_dias(fecha_llegada, fecha_salida)

    n_actividades = duracion_vacaciones * 3;

    n_actividades_ludicas, n_actividades_culturales, n_actividades_festivas = repartir_actividades(grado_ludica, grado_cultural, grado_festivo, n_actividades)

    tipo_actividades = []
    tipo_actividades.extend([ECSDI.tipo_ludica] * n_actividades_ludicas)
    tipo_actividades.extend([ECSDI.tipo_cultural] * n_actividades_culturales)
    tipo_actividades.extend([ECSDI.tipo_festiva] * n_actividades_festivas)

    for i in range(duracion_vacaciones):
        obtener_actividades_un_dia(
            dia = i+1,
            tipo_actividad_manana= tipo_actividades[i*3],
            tipo_actividad_tarde= tipo_actividades[i*3+1], 
            tipo_actividad_noche= tipo_actividades[i*3+2])
    

    return build_message(Graph(), ACL['inform'], sender=AgenteProveedorActividades.uri, msgcnt=getMessageCount())


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
        gr = build_message(Graph(), ACL['not-understood'], sender=AgenteProveedorActividades.uri, msgcnt=getMessageCount())
    else:
        # Obtenemos la performativa
        perf = msgdic['performative']

        if perf != ACL.request:
            # Si no es un request, respondemos que no hemos entendido el mensaje
            gr = build_message(Graph(), ACL['not-understood'], sender=AgenteProveedorActividades.uri, msgcnt=getMessageCount())
        else:
            # Extraemos el objeto del contenido que ha de ser una accion de la ontologia de acciones del agente
            # de registro

            # Averiguamos el tipo de la accion
            if 'content' in msgdic:
                sujeto = msgdic['content']
                accion = gm.value(subject=sujeto, predicate=RDF.type)

                if accion == ECSDI.IntervaloDeActividades:
                    logger.info('Peticion de intervalo de actividades')
                    gr = obtener_intervalo_actividades(sujeto, gm)

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

    ab1 = Process(target=obtener_intervalo_actividades, args=("jaja","puto"))
    ab1.start()

    # Ponemos en marcha el servidor
    app.run(host=hostname, port=port)

    # Esperamos a que acaben los behaviors
    ab1.join()
    logger.info('The End')
