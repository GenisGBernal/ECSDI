# -*- coding: utf-8 -*-
"""
filename: SimpleInfoAgent

Antes de ejecutar hay que añadir la raiz del proyecto a la variable PYTHONPATH

Agente que se registra como agente de hoteles y espera peticiones

@author: javier
"""

from datetime import datetime as time_converter
import datetime
from multiprocessing import Process, Queue
import logging
import argparse
import random

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
                                    agn.AgenteProveedorActividades,
                                    'http://%s:%d/comm' % (hostaddr, port),
                                    'http://%s:%d/Stop' % (hostaddr, port))

# Directory agent address
AgenteDirectorio = Agent('AgenteDirectorio',
                       agn.Directory,
                       'http://%s:%d/Register' % (dhostname, dport),
                       'http://%s:%d/Stop' % (dhostname, dport))

# Global actividadesDB triplestore
actividadesDB = Graph()
actividadesDB.bind('ECSDI', ECSDI)

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

def string_a_fecha(fecha_en_string):
    formato = "%Y-%m-%d"

    return time_converter.strptime(fecha_en_string, formato).date()

def obtener_diferencia_en_dias(fecha1, fecha2):

    fecha1_obj = string_a_fecha(fecha1)
    fecha2_obj = string_a_fecha(fecha2)

    return abs((fecha2_obj - fecha1_obj).days) + 1


def repartir_actividades(grado_ludica, grado_cultural, grado_festivo, n_actividades):
    total_grado = grado_ludica + grado_cultural + grado_festivo

    n_actividades_ludicas = (grado_ludica / total_grado) * n_actividades
    n_actividades_culturales = (grado_cultural / total_grado) * n_actividades
    n_actividades_festivas = (grado_festivo / total_grado) * n_actividades

    suma_partes = int(n_actividades_ludicas) + int(n_actividades_culturales) + int(n_actividades_festivas)
    diferencia = n_actividades - suma_partes

    if diferencia > 0:
        if n_actividades_ludicas > 0:
            n_actividades_ludicas += diferencia
        elif n_actividades_culturales > 0:
            n_actividades_culturales += diferencia
        else:
            n_actividades_festivas += diferencia

    return int(n_actividades_ludicas), int(n_actividades_culturales), int(n_actividades_festivas)


def obtener_actividad(tipo_actividad, lugar_llegada="BCN"):
    latitude = None
    longitude = None
    if lugar_llegada == 'LON':
        latitude = 51.516089
        longitude = -0.123917
    else:
        latitude = 41.397896
        longitude = 2.165111

    global actividadesDB

    sujetos_actividades = list(actividadesDB.query("""
        SELECT DISTINCT ?sujeto
        WHERE {
            ?sujeto ECSDI:tipo_actividad ?tipo ;
            ECSDI:latitude ?latitude ;
            ECSDI:longitude ?longitude .
            FILTER (?tipo = ?var1
                && ?latitude = ?var2
                && ?longitude = ?var3)
        }
    """, 
    initNs = {'ECSDI': ECSDI},
    initBindings={
        'var1': tipo_actividad,
        'var2': Literal(latitude, datatype=XSD.float),
        'var3': Literal(longitude, datatype=XSD.float),
        }
    ))

    sujeto = None

    if len(sujetos_actividades) > 0:
        logger.info('Busqueda en cache de actividad tipo: ' + tipo_actividad)
        sujeto = random.choice(sujetos_actividades)[0]

    else:
        logger.info('Busqueda en amadeus de actividad tipo: ' + tipo_actividad)
        if tipo_actividad == ECSDI.tipo_festiva:
            response = amadeus.reference_data.locations.points_of_interest.get(latitude=latitude, longitude=longitude, radius=7, categories="NIGHTLIFE", page=70)
            sujeto = ECSDI['actividad/festiva/'+random.choice(response.data)['id']]
            for r in response.data:
                actividadesDB.add((ECSDI['actividad/festiva/'+r['id']], RDF.type, ECSDI.actividad))
                actividadesDB.add((ECSDI['actividad/festiva/'+r['id']], ECSDI.tipo_actividad, ECSDI.tipo_festiva))
                actividadesDB.add((ECSDI['actividad/festiva/'+r['id']], ECSDI.subtipo_actividad, Literal(r['subType'], datatype=XSD.string)))
                actividadesDB.add((ECSDI['actividad/festiva/'+r['id']], ECSDI.nombre_actividad, Literal(r['name'], datatype=XSD.string)))
                actividadesDB.add((ECSDI['actividad/festiva/'+r['id']], ECSDI.latitude, Literal(latitude, datatype=XSD.float)))
                actividadesDB.add((ECSDI['actividad/festiva/'+r['id']], ECSDI.longitude, Literal(longitude, datatype=XSD.float)))
                for tag in r['tags']:
                    actividadesDB.add((ECSDI['actividad/festiva/'+r['id']], ECSDI.tag_actividad, Literal(tag, datatype=XSD.string)))

        elif tipo_actividad == ECSDI.tipo_ludica:
            response = amadeus.reference_data.locations.points_of_interest.get(latitude=latitude, longitude=longitude, radius=7, categories="SHOPPING", page=70)
            sujeto = ECSDI['actividad/ludica/'+random.choice(response.data)['id']]
            for r in response.data:
                actividadesDB.add((ECSDI['actividad/ludica/'+r['id']], RDF.type, ECSDI.actividad))
                actividadesDB.add((ECSDI['actividad/ludica/'+r['id']], ECSDI.tipo_actividad, ECSDI.tipo_ludica))
                actividadesDB.add((ECSDI['actividad/ludica/'+r['id']], ECSDI.subtipo_actividad, Literal(r['subType'], datatype=XSD.string)))
                actividadesDB.add((ECSDI['actividad/ludica/'+r['id']], ECSDI.nombre_actividad, Literal(r['name'], datatype=XSD.string)))
                actividadesDB.add((ECSDI['actividad/ludica/'+r['id']], ECSDI.latitude, Literal(latitude, datatype=XSD.float)))
                actividadesDB.add((ECSDI['actividad/ludica/'+r['id']], ECSDI.longitude, Literal(longitude, datatype=XSD.float)))
                for tag in r['tags']:
                    actividadesDB.add((ECSDI['actividad/ludica/'+r['id']], ECSDI.tag_actividad, Literal(tag, datatype=XSD.string)))

        elif tipo_actividad == ECSDI.tipo_cultural:
            response = amadeus.reference_data.locations.points_of_interest.get(latitude=latitude, longitude=longitude, radius=7, categories="SIGHTS", page=70)
            sujeto = ECSDI['actividad/cultural/'+random.choice(response.data)['id']]
            for r in response.data:
                actividadesDB.add((ECSDI['actividad/cultural/'+r['id']], RDF.type, ECSDI.actividad))
                actividadesDB.add((ECSDI['actividad/cultural/'+r['id']], ECSDI.tipo_actividad, ECSDI.tipo_cultural))
                actividadesDB.add((ECSDI['actividad/cultural/'+r['id']], ECSDI.subtipo_actividad, Literal(r['subType'], datatype=XSD.string)))
                actividadesDB.add((ECSDI['actividad/cultural/'+r['id']], ECSDI.nombre_actividad, Literal(r['name'], datatype=XSD.string)))
                actividadesDB.add((ECSDI['actividad/cultural/'+r['id']], ECSDI.latitude, Literal(latitude, datatype=XSD.float)))
                actividadesDB.add((ECSDI['actividad/cultural/'+r['id']], ECSDI.longitude, Literal(longitude, datatype=XSD.float)))
                for tag in r['tags']:
                    actividadesDB.add((ECSDI['actividad/cultural/'+r['id']], ECSDI.tag_actividad, Literal(tag, datatype=XSD.string)))
        
    gr = Graph()
    IAA = Namespace('IAActions')
    gr.bind('foaf', FOAF)
    gr.bind('iaa', IAA)
    gr.bind('ECSDI', ECSDI)
    gr.add((sujeto, RDF.type, ECSDI.actividad))    
    gr.add((sujeto, ECSDI.tipo_actividad, actividadesDB.value(subject=sujeto, predicate=ECSDI.tipo_actividad)))
    gr.add((sujeto, ECSDI.subtipo_actividad, actividadesDB.value(subject=sujeto, predicate=ECSDI.subtipo_actividad)))
    gr.add((sujeto, ECSDI.nombre_actividad, actividadesDB.value(subject=sujeto, predicate=ECSDI.nombre_actividad)))
    for _, _, tag in actividadesDB.triples((sujeto, ECSDI.tag_actividad, None)):
        gr.add((sujeto, ECSDI.tag_actividad, tag))

    return gr


def obtener_actividades_un_dia(sujeto_viaje, dia, lugar_llegada, tipo_actividad_manana, tipo_actividad_tarde, tipo_actividad_noche):

    gr = Graph()
    IAA = Namespace('IAActions')
    gr.bind('foaf', FOAF)
    gr.bind('iaa', IAA)
    gr.bind('ECSDI', ECSDI)
    sujeto = ECSDI['ActividadesParaUnDia-' + str(getMessageCount())]
    gr.add((sujeto_viaje, ECSDI.ActividadesOrdenadas, sujeto))
    gr.add((sujeto, RDF.type, ECSDI.actividades_ordenadas))
    gr.add((sujeto, ECSDI.dia, Literal(dia, datatype=XSD.string)))

    gr_actividad_de_manana = obtener_actividad(tipo_actividad=tipo_actividad_manana, lugar_llegada=lugar_llegada)
    sujeto_actividad_de_manana = gr_actividad_de_manana.value(predicate=RDF.type, object=ECSDI.actividad)
    gr.add((sujeto, ECSDI.actividad_manana, sujeto_actividad_de_manana))

    gr_actividad_de_tarde = obtener_actividad(tipo_actividad=tipo_actividad_tarde, lugar_llegada=lugar_llegada)
    sujeto_actividad_de_tarde = gr_actividad_de_tarde.value(predicate=RDF.type, object=ECSDI.actividad)
    gr.add((sujeto, ECSDI.actividad_tarde, sujeto_actividad_de_tarde))

    gr_actividad_de_noche = obtener_actividad(tipo_actividad=tipo_actividad_noche, lugar_llegada=lugar_llegada)
    sujeto_actividad_de_noche = gr_actividad_de_noche.value(predicate=RDF.type, object=ECSDI.actividad)
    gr.add((sujeto, ECSDI.actividad_noche, sujeto_actividad_de_noche))

    return gr + gr_actividad_de_manana + gr_actividad_de_tarde + gr_actividad_de_noche


def obtener_intervalo_actividades(sujeto, gm):

    fecha_llegada = gm.value(subject=sujeto, predicate=ECSDI.DiaDePartida).toPython()
    fecha_salida = gm.value(subject=sujeto, predicate=ECSDI.DiaDeRetorno).toPython()
    grado_ludica = gm.value(subject=sujeto, predicate=ECSDI.grado_ludica).toPython()
    grado_cultural = gm.value(subject=sujeto, predicate=ECSDI.grado_cultural).toPython()
    grado_festivo = gm.value(subject=sujeto, predicate=ECSDI.grado_festiva).toPython()
    lugar_llegada = gm.value(subject=sujeto, predicate=ECSDI.LugarDeLlegada).toPython()

    logger.info("Fecha llegada: " + fecha_llegada)
    logger.info("Fecha salida: " + fecha_salida)
    logger.info("Grado festivo: " + str(grado_festivo))
    logger.info("Grado cultural: " + str(grado_cultural))
    logger.info("Grado ludica: " + str(grado_ludica))

    duracion_vacaciones = obtener_diferencia_en_dias(fecha_llegada, fecha_salida)

    n_actividades = duracion_vacaciones * 3;

    n_actividades_ludicas, n_actividades_culturales, n_actividades_festivas = repartir_actividades(grado_ludica, grado_cultural, grado_festivo, n_actividades)

    logger.info("Duración vacaciones: " + str(duracion_vacaciones))
    logger.info("N festivo: " + str(n_actividades_festivas))
    logger.info("N cultural: " + str(n_actividades_culturales))
    logger.info("N ludicas: " + str(n_actividades_ludicas))

    tipo_actividades = []
    tipo_actividades.extend([ECSDI.tipo_ludica] * n_actividades_ludicas)
    tipo_actividades.extend([ECSDI.tipo_cultural] * n_actividades_culturales)
    tipo_actividades.extend([ECSDI.tipo_festiva] * n_actividades_festivas)
    random.shuffle(tipo_actividades)

    gr = Graph()
    IAA = Namespace('IAActions')
    gr.bind('foaf', FOAF)
    gr.bind('iaa', IAA)
    gr.bind('ECSDI', ECSDI)
    sujeto = ECSDI['IntervaloDeActividades-' + str(getMessageCount())]
    gr.add((sujeto, RDF.type, ECSDI.viaje_actividades))

    for i in range(duracion_vacaciones):
        gr += obtener_actividades_un_dia(
            sujeto_viaje = sujeto,
            dia = string_a_fecha(fecha_llegada) + datetime.timedelta(days=i),
            lugar_llegada = lugar_llegada,
            tipo_actividad_manana= tipo_actividades[i*3],
            tipo_actividad_tarde= tipo_actividades[i*3+1], 
            tipo_actividad_noche= tipo_actividades[i*3+2])
        
    print(gr.serialize(format='turtle'))

    return build_message(gr, ACL['inform'], sender=AgenteProveedorActividades.uri, msgcnt=getMessageCount(), content=sujeto)


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
                
                elif accion == ECSDI.ActividadCubierta:
                    logger.info('Peticion de actividad cubierta')
                    lugar_llegada = gm.value(subject=sujeto, predicate=ECSDI.LugarDeLlegada).toPython()
                    print("Codigo lugar:" + lugar_llegada)
                    gr = obtener_actividad(ECSDI.tipo_ludica, lugar_llegada)
                    gr = build_message(gr, ACL['inform'], 
                                       sender=AgenteProveedorActividades.uri, 
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
