# -*- coding: utf-8 -*-
"""
filename: SimplePersonalAgent

Antes de ejecutar hay que añadir la raiz del proyecto a la variable PYTHONPATH

Ejemplo de agente que busca en el directorio y llama al agente obtenido


Created on 09/02/2014

@author: javier
"""

import datetime
from datetime import datetime as time_converter
from multiprocessing import Process
import logging
import argparse

from flask import Flask, render_template, request
from rdflib import XSD, Graph, Literal, Namespace
from rdflib.namespace import FOAF, RDF

from AgentUtil.ACL import ACL
from AgentUtil.DSO import DSO
from AgentUtil.FlaskServer import shutdown_server
from AgentUtil.ACLMessages import build_message, send_message, getAgentInfo, get_message_properties, clean_graph
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
viaje_pendiente_confirmacion = Graph()

propuesta_viaje = None

def string_a_fecha(fecha_en_string):
    formato = "%Y-%m-%d"

    return time_converter.strptime(fecha_en_string, formato).date()


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

def obtener_info_transporte(grafo_viaje):
    transporte = ECSDI['avion']

    info_relevante_vuelo = []

    query = f"""
        SELECT ?identificador ?precio ?dia_partida ?dia_retorno ?lugar_partida ?lugar_llegada
        WHERE {{
            ?billete ECSDI:viaje_transporte ?viaje_transporte_param ;
                     ECSDI:identificador ?identificador ;
                     ECSDI:precio ?precio ;
                     ECSDI:DiaVueloDePartida ?dia_partida ;
                     ECSDI:DiaVueloDeRetorno ?dia_retorno ;
                     ECSDI:LugarVueloDePartida ?lugar_partida ;
                     ECSDI:LugarVueloDeLlegada ?lugar_llegada .
                FILTER (?viaje_transporte_param = <{transporte}>)
            }}
            LIMIT 1
            """
    logger.info(query)

    resultsQuery = grafo_viaje.query(
        query,
        initNs={'ECSDI': ECSDI})

    info_general = {'nombre': 'Informacion general', 'info': []}
    info_viaje_ida = {'nombre': 'Informacion viaje ida', 'info': []}
    info_viaje_vuelta = {'nombre': 'Informacion viaje vuelta', 'info': []}

    for result in resultsQuery:
        info_general['info'] = ['Identificador : ' + str(result.identificador.toPython()),
                        'Precio total: ' + str(result.precio.toPython()) + '€']

        info_viaje_ida['info'] = ['Fecha vuelo : ' + str(result.dia_partida.toPython()),
                          'Ciudad salida : ' + str(result.lugar_partida.toPython()),
                          'Ciudad llegada: ' + str(result.lugar_llegada.toPython())]

        info_viaje_vuelta['info'] = ['Fecha vuelo : ' + str(result.dia_retorno.toPython()),
                             'Ciudad salida : ' + str(result.lugar_llegada.toPython()),
                             'Ciudad llegada: ' + str(result.lugar_partida.toPython())]

    info_vuelo = [info_general, info_viaje_ida, info_viaje_vuelta]

    return info_vuelo

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

    lista_actividades_completa = sorted(lista_actividades_completa, key=lambda x: string_a_fecha(x['dia']))

    return lista_actividades_completa


def obten_precio_total(grafo_viaje):

    sujeto = grafo_viaje.value(predicate=RDF.type, object=ECSDI.ViajePendienteDeConfirmacion)
    precio_total = grafo_viaje.value(subject=sujeto, predicate=ECSDI.precio_total).toPython()

    return precio_total

def obtener_hotel(grafo_viaje):
    hotel = grafo_viaje.value(predicate=RDF.type, object=ECSDI.Hospedaje)
    nombre_hotel = grafo_viaje.value(subject=hotel, predicate=ECSDI.identificador).toPython()
    precio_hotel = grafo_viaje.value(subject=hotel, predicate=ECSDI.precio).toPython()
    return {
        'nombre': nombre_hotel,
        'precio': precio_hotel
    }


def generar_peticion_de_viaje(usuario, lugarDePartida, destinacion, diaPartida, diaRetorno, grado_ludica, grado_cultural, grado_festivo):

    agentePlanificador = getAgentInfo(DSO.AgentePlanificador, DirectoryAgent, AgenteContratador, getMessageCount())

    gmess = Graph()
    IAA = Namespace('IAActions')
    gmess.bind('foaf', FOAF)
    gmess.bind('iaa', IAA)
    gmess.bind('ECSDI', ECSDI)
    sujeto = agn['PeticiónDeViaje-' + str(getMessageCount())]
    gmess.add((sujeto, RDF.type, ECSDI.PeticionDeViaje))
    gmess.add((sujeto, ECSDI.Usuario, Literal(usuario, datatype=XSD.string)))
    gmess.add((sujeto, ECSDI.LugarDePartida, Literal(lugarDePartida, datatype=XSD.string)))
    gmess.add((sujeto, ECSDI.LugarDeLlegada, Literal(destinacion, datatype=XSD.string)))
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
    gr = clean_graph(gr)
    log.info("Respuesta recibida")
    return gr

def peticion_de_cobro(tarjeta_id):
    agenteCobrador = getAgentInfo(DSO.AgenteCobrador, DirectoryAgent, AgenteContratador, getMessageCount())

    sujeto = agn['QuieroCobrarViaje-' + str(getMessageCount())]

    global viaje_pendiente_confirmacion


    if not viaje_pendiente_confirmacion:
        print("No hay viaje pendiente de confirmación")
        return False
    

    print("VIAJE GUARDADO:")
    print(viaje_pendiente_confirmacion.serialize(format='turtle'))

    gmess = Graph() + viaje_pendiente_confirmacion
    IAA = Namespace('IAActions')
    gmess.bind('foaf', FOAF)
    gmess.bind('iaa', IAA)
    gmess.bind('ECSDI', ECSDI)
    gmess.add((sujeto, RDF.type, ECSDI.QuieroCobrarViaje))

    le_viaje = gmess.value(predicate=RDF.type, object=ECSDI.ViajePendienteDeConfirmacion)

    if le_viaje is None:
        return False

    gmess.add((sujeto, ECSDI.tiene_viaje, le_viaje))
    gmess.add((sujeto, ECSDI.numero_tarjeta, Literal(tarjeta_id, datatype=XSD.string)))
    gmess.add((sujeto, ECSDI.precio_total, Literal(obten_precio_total(viaje_pendiente_confirmacion), datatype=XSD.float)))

    msg = build_message(gmess, perf=ACL.request,
                        sender=AgenteContratador.uri,
                        receiver=agenteCobrador.uri,
                        msgcnt=getMessageCount(),
                        content=sujeto)
    
    logger.info("Petición de cobro al AgenteCobrador")
    gr = send_message(msg, agenteCobrador.address)
    
    print(gr.serialize(format='turtle'))

    gr = clean_graph(gr)
    response_subject = gr.value(predicate=RDF.type, object=ECSDI.TomaCobroAcceptado)
    if response_subject is not None:
        return True
    else:
        return False



@app.route("/respuesta-propuesta-viaje", methods=['POST'])
def recibir_respuesta_propuesta_viaje():
    if request.method == 'POST':
        respuesta = request.form['respuesta']
        if respuesta == "si":
            tarjeta_id = request.form['tarjeta']
            success = peticion_de_cobro(tarjeta_id)
            
            if success: 
                agenteGestorDeViajes = getAgentInfo(DSO.AgenteGestorDeViajes, DirectoryAgent, AgenteContratador, getMessageCount())

                sujeto = propuesta_viaje.value(predicate=RDF.type, object=ECSDI.ViajePendienteDeConfirmacion)
                msg = build_message(propuesta_viaje, perf=ACL.request,
                            sender=AgenteContratador.uri,
                            receiver=agenteGestorDeViajes.uri,
                            msgcnt=getMessageCount(),
                            content=sujeto)
                gr = send_message(msg, agenteGestorDeViajes.address)
                return render_template('viaje_confirmado.html')
            else: 
                global viaje_pendiente_confirmacion
                actividades = obtener_actividades(viaje_pendiente_confirmacion)
                hotel = obtener_hotel(viaje_pendiente_confirmacion)
                return render_template('propuesta_viaje.html', actividades=actividades, hospedaje=hotel, precio_total = obten_precio_total(viaje_pendiente_confirmacion), error_message='No se ha podido realizar el cobro')
        else:
            return render_template('iface.html')
    

def emulate_planificador():
    with open('example_planificador_response.ttl', 'r') as f:
            print(f)
            gr = Graph().parse(f, format='turtle')
        
            print(gr.serialize(format='turtle'))
        
            global viaje_pendiente_confirmacion
            viaje_pendiente_confirmacion = Graph()
            viaje_pendiente_confirmacion.bind('ECSDI', ECSDI)
            viaje_pendiente_confirmacion += gr
        
            actividades = obtener_actividades(gr)
            hotel = obtener_hotel(gr)

            return render_template('propuesta_viaje.html', actividades=actividades, hospedaje=hotel, precio_total = obten_precio_total(gr))


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
        destinacion = request.form['destinacion']
        diaPartida = request.form['DiaDePartida']
        diaRetorno = request.form['DiaDeRetorno']
        grado_ludica = request.form['grado_ludica']
        grado_cultural = request.form['grado_cultural']
        grado_festivo = request.form['grado_festivo']

        if len(lugarDePartida) != 3 or not lugarDePartida.isupper():
            return render_template('iface.html', error_message='El lugar de salida debe ser el código IATA de un aeropuerto, como: LHR, TXL, CDG, FCO, YYZ, SYD, PEK, GRU, EZE...')

        if diaRetorno < diaPartida:
            return render_template('iface.html', error_message='La fecha de retorno no puede ser anterior a la de salida')

        if grado_ludica + grado_cultural + grado_festivo == 0:
            return render_template('iface.html', error_message='Se debe escoger un mínimo de algo en algun tipo de actividad')
        


        gr = generar_peticion_de_viaje(
            usuario=usuario,
            lugarDePartida=lugarDePartida,
            destinacion=destinacion,
            diaPartida=diaPartida,
            diaRetorno=diaRetorno,
            grado_ludica=grado_ludica,
            grado_cultural=grado_cultural,
            grado_festivo=grado_festivo)

        print(gr.serialize(format='turtle'))

        transporte = obtener_info_transporte(gr)
        actividades = obtener_actividades(gr)
        
        global propuesta_viaje
        propuesta_viaje = clean_graph(gr)

        global viaje_pendiente_confirmacion
        viaje_pendiente_confirmacion = clean_graph(gr)

        hotel = obtener_hotel(gr)

        return render_template('propuesta_viaje.html', actividades=actividades, transporte=transporte, hospedaje=hotel, precio_total = obten_precio_total(viaje_pendiente_confirmacion))

        


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
