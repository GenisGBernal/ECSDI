# -*- coding: utf-8 -*-
"""
filename: AgenteRecomendadorYSatisfaccion

Antes de ejecutar hay que añadir la raiz del proyecto a la variable PYTHONPATH

Agente que recomienda viajes y recoge valoraciones

@author: daniel
"""
import os
import time
from multiprocessing import Process, Pipe
import logging
import argparse
from flask import Flask, render_template, request
from rdflib.namespace import FOAF, RDF
from datetime import datetime, timedelta

from multiprocessing import Process, Queue
import logging
import argparse
from flask import Flask, request
from rdflib import XSD, Graph, Namespace, Literal
from rdflib.namespace import FOAF, RDF

from AgentUtil.ACL import ACL
from AgentUtil.FlaskServer import shutdown_server
from AgentUtil.ACLMessages import build_message, send_message, getAgentInfo, get_message_properties, clean_graph
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

file_path_satisfaccion = "./.ecsdi/satisfaccionDB.rdf"
file_path_viajes_recomendaciones_ini = "./.ecsdi/recomendaciones/.ini.rdf"
file_path_viajes_recomendaciones = "./.ecsdi/recomendaciones/"


# Global satisfaccionDB y viajesFinalizadosDB triplestore
satisfaccionDB = Graph()
satisfaccionDB.bind('ECSDI', ECSDI)
satisfaccionDB.bind('RDF', RDF)

viajesFinalizadosDB = Graph()
viajesFinalizadosDB.bind('ECSDI', ECSDI)
viajesFinalizadosDB.bind('RDF', RDF)
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


def media(a, b):
    media = (a + b) / 2
    return round(media)


def guardarViajesFinalizados(sujeto, gm):
    for s, p, o in gm:
        if p == ECSDI.ViajeFinalizado:
            viajesFinalizadosDB.add((s, ECSDI.viajeValorado, Literal(False, datatype=XSD.boolean)))
        viajesFinalizadosDB.add((s, p, o))

    viajesFinalizadosDB.serialize(format='turtle')
    return Graph()  # TODO: Devolver algo


def recomendarActividadesUsuario(grado_ludica, grado_cultural, grado_festivo, fecha_ida, fecha_vuelta, usuario):
    logger.info('Fecha ida: ' + fecha_ida)
    logger.info('Fecha vuelta: ' + fecha_vuelta)
    logger.info('Grado ludica: ' + str(grado_ludica))
    logger.info('Grado cultural: ' + str(grado_cultural))
    logger.info('Grado festivo: ' + str(grado_festivo))

    agenteProveedorActividades = getAgentInfo(DSO.AgenteProveedorActividades, AgenteDirectorio,
                                              AgenteRecomendadorYSatisfaccion, getMessageCount())

    gmess = Graph()
    IAA = Namespace('IAActions')
    gmess.bind('foaf', FOAF)
    gmess.bind('iaa', IAA)
    gmess.bind('ECSDI', ECSDI)
    sujeto = agn['PeticiónIntervaloDeActividades-' + str(getMessageCount())]
    gmess.add((sujeto, RDF.type, ECSDI.IntervaloDeActividades))
    gmess.add((sujeto, ECSDI.DiaDePartida, Literal(fecha_ida, datatype=XSD.string)))
    gmess.add((sujeto, ECSDI.DiaDeRetorno, Literal(fecha_vuelta, datatype=XSD.string)))
    gmess.add((sujeto, ECSDI.grado_ludica, Literal(grado_ludica, datatype=XSD.integer)))
    gmess.add((sujeto, ECSDI.grado_cultural, Literal(grado_cultural, datatype=XSD.integer)))
    gmess.add((sujeto, ECSDI.grado_festiva, Literal(grado_festivo, datatype=XSD.integer)))

    msg = build_message(gmess, perf=ACL.request,
                        sender=AgenteRecomendadorYSatisfaccion.uri,
                        receiver=agenteProveedorActividades.uri,
                        msgcnt=getMessageCount(),
                        content=sujeto)

    gr = send_message(msg, agenteProveedorActividades.address)

    g_actividades = clean_graph(gr)

    user_id = usuario.replace(ECSDI, "")
    file_a_guardar = file_path_viajes_recomendaciones + user_id + ".rdf"

    with open(file_a_guardar, "wb") as file:
        g_actividades.serialize(destination=file, format='xml')

    logger.info(g_actividades.serialize(format='turtle'))


def enviar_recomendaciones():
    satisfaccionDB = Graph()
    satisfaccionDB.parse(file_path_satisfaccion, format='xml')

    logger.info('ESTADO BASE DE DATOS SATISFACCION')
    logger.info(satisfaccionDB.serialize(format='turtle'))

    query = f"""
        SELECT ?usuario ?gusto_ludica ?gusto_cultural ?gusto_festivo
        WHERE {{
            ?usuario ECSDI:gusto_actividades_ludicas ?gusto_ludica ;
                     ECSDI:gusto_actividades_culturales ?gusto_cultural ;
                     ECSDI:gusto_actividades_festivas ?gusto_festivo .
        }}
        """

    logger.info(query)

    resultsQuery = satisfaccionDB.query(
        query,
        initNs={'ECSDI': ECSDI, 'RDF': RDF})

    logger.info('Se van a hacer ' + str(len(resultsQuery)) + ' recomendaciones')

    for result in resultsQuery:
        grado_ludica = result['gusto_ludica']
        grado_cultural = result['gusto_cultural']
        grado_festivo = result['gusto_festivo']
        usuario = result['usuario']

        fecha_ida = (datetime.today() + timedelta(days=30)).strftime('%Y-%m-%d')
        fecha_vuelta = (datetime.today() + timedelta(days=37)).strftime('%Y-%m-%d')
        recomendarActividadesUsuario(grado_ludica, grado_cultural, grado_festivo, fecha_ida, fecha_vuelta, usuario)
        logger.info('Recomendacion enviada a ' + result['usuario'])


def obtener_viaje_no_valorado_usuario(usuario):
    global viajesFinalizadosDB

    query = f"""
        SELECT ?viaje ?diaDePartida ?diaDeRetorno ?lugarDePartida ?lugarDeLlegada ?precio_total ?grado_ludica ?grado_cultural ?grado_festivo
        WHERE {{
            ?viaje RDF:type ECSDI:ViajeFinalizado ;
                            ECSDI:viajeValorado ?viajeValorado_param ;
                            ECSDI:Usuario ?usuario_param ;
                            ECSDI:DiaDePartida ?diaDePartida ;
                            ECSDI:DiaDeRetorno ?diaDeRetorno ;
                            ECSDI:LugarDePartida ?lugarDePartida ;
                            ECSDI:LugarDeLlegada ?lugarDeLlegada ;
                            ECSDI:precio_total ?precio_total ;
                            ECSDI:grado_ludica ?grado_ludica ;
                            ECSDI:grado_cultural ?grado_cultural ;
                            ECSDI:grado_festivo ?grado_festivo .
            FILTER (?viajeValorado_param = false && ?usuario_param = "{usuario}")
        }}
        LIMIT 1
        """

    logger.info(query)

    resultsQuery = viajesFinalizadosDB.query(
        query,
        initNs={'ECSDI': ECSDI, 'RDF': RDF})

    if len(resultsQuery) == 0:
        return None

    viaje_a_valorar = {}
    logger.info('Viajes por valorar encontrados: ' + str(len(resultsQuery)))
    # for con solo 1 elemento
    for row in resultsQuery:
        id_viaje = row['viaje']
        viaje_a_valorar = {'viaje_id': id_viaje, 'Lugar de partida': row['lugarDePartida'],
                           'Lugar de llegada': row['lugarDeLlegada'], 'Dia de partida': row['diaDePartida'],
                           'Dia de retorno': row['diaDeRetorno'], 'Precio': row['precio_total'],
                           'Grado ludica': row['grado_ludica'], 'Grado cultural': row['grado_cultural'],
                           'Grado festivo': row['grado_festivo']}

        viajesFinalizadosDB.remove((id_viaje, ECSDI.viajeValorado, Literal(False, datatype=XSD.boolean)))
        viajesFinalizadosDB.add((id_viaje, ECSDI.viajeValorado, Literal(True, datatype=XSD.boolean)))

    logger.info(viajesFinalizadosDB.serialize(format='turtle'))

    return viaje_a_valorar


@app.route("/encuesta_finalizada", methods=['GET', 'POST'])
def browser_iface_encuesta_satisfaccion_finalizada():
    global satisfaccionDB

    if request.method == 'GET':
        return render_template('encuesta_satisfaccion_finalizada.html')
    else:
        print('Grado ludica viaje: ' + request.form['grado_ludica_viaje'])
        print('Grado cultural viaje: ' + request.form['grado_cultural_viaje'])
        print('Grado festivo viaje: ' + request.form['grado_festivo_viaje'])
        print('Usuario: ' + request.form['usuario'])

        print('Grado ludica opinion: ' + request.form['grado_ludica_opinion'])
        print('Grado cultural opinion: ' + request.form['grado_cultural_opinion'])
        print('Grado festivo opinion: ' + request.form['grado_festivo_opinion'])

        grado_ludica_viaje = request.form['grado_ludica_viaje']
        grado_cultural_viaje = request.form['grado_cultural_viaje']
        grado_festivo_viaje = request.form['grado_festivo_viaje']

        grado_ludica_opinion = request.form['grado_ludica_opinion']
        grado_cultural_opinion = request.form['grado_cultural_opinion']
        grado_festivo_opinion = request.form['grado_festivo_opinion']

        viaje_id = request.form['viaje_id']
        usuario = request.form['usuario']

        query = f"""
            SELECT ?gusto_ludica ?gusto_cultural ?gusto_festivo
            WHERE {{
                ?usuario ECSDI:gusto_actividades_ludicas ?gusto_ludica ;
                                ECSDI:gusto_actividades_culturales ?gusto_cultural ;
                                ECSDI:gusto_actividades_festivas ?gusto_festivo .
                FILTER (?usuario = ECSDI:{usuario})
            }}
            LIMIT 1
            """

        print(query)

        resultsQuery = satisfaccionDB.query(
            query,
            initNs={'ECSDI': ECSDI, 'RDF': RDF})

        nuevo_gusto_actividades_culturales = max(0, min(3, int(grado_cultural_opinion) + int(grado_cultural_viaje)))
        nuevo_gusto_actividades_festivas = max(0, min(3, int(grado_festivo_opinion) + int(grado_festivo_viaje)))
        nuevo_gusto_actividades_ludicas = max(0, min(3, int(grado_ludica_opinion) + int(grado_ludica_viaje)))

        print('Nuevo gusto ludica: ' + str(nuevo_gusto_actividades_ludicas))
        print('Nuevo gusto cultural: ' + str(nuevo_gusto_actividades_culturales))
        print('Nuevo gusto festivo: ' + str(nuevo_gusto_actividades_festivas))

        logger.info("En la BD habia " + str(len(resultsQuery)) + " resultados")

        if len(resultsQuery) == 0:
            satisfaccionDB.add((ECSDI[usuario], RDF.type, ECSDI.Usuario))
        else:
            for row in resultsQuery:
                registro_gusto_actividades_ludicas = row['gusto_ludica']
                registro_gusto_actividades_culturales = row['gusto_cultural']
                registro_gusto_actividades_festivas = row['gusto_festivo']

                print('Registro gusto ludica: ' + str(registro_gusto_actividades_ludicas))
                print('Registro gusto cultural: ' + str(registro_gusto_actividades_culturales))
                print('Registro gusto festivo: ' + str(registro_gusto_actividades_festivas))

                nuevo_gusto_actividades_ludicas = max(0, min(3, media(nuevo_gusto_actividades_ludicas,
                                                                      int(registro_gusto_actividades_ludicas))))
                nuevo_gusto_actividades_culturales = max(0, min(3, media(nuevo_gusto_actividades_culturales,
                                                                         int(registro_gusto_actividades_culturales))))
                nuevo_gusto_actividades_festivas = max(0, min(3, media(nuevo_gusto_actividades_festivas,
                                                                       int(registro_gusto_actividades_festivas))))

                satisfaccionDB.remove((ECSDI[usuario], ECSDI.gusto_actividades_ludicas, None))
                satisfaccionDB.remove((ECSDI[usuario], ECSDI.gusto_actividades_culturales, None))
                satisfaccionDB.remove((ECSDI[usuario], ECSDI.gusto_actividades_festivas, None))

        print('Gusto ludica a insertar: ' + str(nuevo_gusto_actividades_ludicas))
        print('Gusto cultural a insertar: ' + str(nuevo_gusto_actividades_culturales))
        print('Gusto festivo a insertar: ' + str(nuevo_gusto_actividades_festivas))

        satisfaccionDB.add((ECSDI[usuario], ECSDI.gusto_actividades_ludicas,
                            Literal(nuevo_gusto_actividades_ludicas, datatype=XSD.integer)))
        satisfaccionDB.add((ECSDI[usuario], ECSDI.gusto_actividades_culturales,
                            Literal(nuevo_gusto_actividades_culturales, datatype=XSD.integer)))
        satisfaccionDB.add((ECSDI[usuario], ECSDI.gusto_actividades_festivas,
                            Literal(nuevo_gusto_actividades_festivas, datatype=XSD.integer)))

        with open(file_path_satisfaccion, "wb") as file:
            satisfaccionDB.serialize(destination=file, format='xml')
        logger.info(satisfaccionDB.serialize(format='turtle'))

        return render_template('encuesta_satisfaccion_finalizada.html', usuario=usuario)


@app.route("/iface", methods=['GET', 'POST'])
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

        viaje_no_valorado_usuario = obtener_viaje_no_valorado_usuario(usuario=usuario)
        if viaje_no_valorado_usuario is None:
            return render_template('no_hay mas_encuestas.html')

        return render_template('encuesta_satisfaccion.html', viaje_no_valorado_usuario=viaje_no_valorado_usuario,
                               usuario=usuario)


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


def inicializarViajesFinalizadosDataTesing():
    global viajesFinalizadosDB

    viajesFinalizadosDB.add((ECSDI['viaje1'], RDF.type, ECSDI['ViajeFinalizado']))
    viajesFinalizadosDB.add((ECSDI['viaje1'], ECSDI.viajeValorado, Literal(False, datatype=XSD.boolean)))
    viajesFinalizadosDB.add((ECSDI['viaje1'], ECSDI.Usuario, Literal('daniel', datatype=XSD.string)))
    viajesFinalizadosDB.add((ECSDI['viaje1'], ECSDI.DiaDePartida, Literal('2019-05-01', datatype=XSD.date)))
    viajesFinalizadosDB.add((ECSDI['viaje1'], ECSDI.DiaDeRetorno, Literal('2019-05-05', datatype=XSD.date)))
    viajesFinalizadosDB.add((ECSDI['viaje1'], ECSDI.precio_total, Literal(100, datatype=XSD.float)))
    viajesFinalizadosDB.add((ECSDI['viaje1'], ECSDI.LugarDePartida, Literal('BCN', datatype=XSD.string)))
    viajesFinalizadosDB.add((ECSDI['viaje1'], ECSDI.LugarDeLlegada, Literal('MAD', datatype=XSD.string)))
    viajesFinalizadosDB.add((ECSDI['viaje1'], ECSDI.grado_ludica, Literal(0, datatype=XSD.integer)))
    viajesFinalizadosDB.add((ECSDI['viaje1'], ECSDI.grado_cultural, Literal(1, datatype=XSD.integer)))
    viajesFinalizadosDB.add((ECSDI['viaje1'], ECSDI.grado_festivo, Literal(2, datatype=XSD.integer)))

    viajesFinalizadosDB.add((ECSDI['viaje2'], RDF.type, ECSDI['ViajeFinalizado']))
    viajesFinalizadosDB.add((ECSDI['viaje2'], ECSDI.viajeValorado, Literal(False, datatype=XSD.boolean)))
    viajesFinalizadosDB.add((ECSDI['viaje2'], ECSDI.Usuario, Literal('daniel', datatype=XSD.string)))
    viajesFinalizadosDB.add((ECSDI['viaje2'], ECSDI.DiaDePartida, Literal('2019-05-01', datatype=XSD.date)))
    viajesFinalizadosDB.add((ECSDI['viaje2'], ECSDI.DiaDeRetorno, Literal('2019-05-05', datatype=XSD.date)))
    viajesFinalizadosDB.add((ECSDI['viaje2'], ECSDI.precio_total, Literal(100, datatype=XSD.float)))
    viajesFinalizadosDB.add((ECSDI['viaje2'], ECSDI.LugarDePartida, Literal('NYC', datatype=XSD.string)))
    viajesFinalizadosDB.add((ECSDI['viaje2'], ECSDI.LugarDeLlegada, Literal('MAD', datatype=XSD.string)))
    viajesFinalizadosDB.add((ECSDI['viaje2'], ECSDI.grado_ludica, Literal(0, datatype=XSD.integer)))
    viajesFinalizadosDB.add((ECSDI['viaje2'], ECSDI.grado_cultural, Literal(1, datatype=XSD.integer)))
    viajesFinalizadosDB.add((ECSDI['viaje2'], ECSDI.grado_festivo, Literal(2, datatype=XSD.integer)))

    viajesFinalizadosDB.add((ECSDI['viaje3'], RDF.type, ECSDI['ViajeFinalizado']))
    viajesFinalizadosDB.add((ECSDI['viaje3'], ECSDI.viajeValorado, Literal(False, datatype=XSD.boolean)))
    viajesFinalizadosDB.add((ECSDI['viaje3'], ECSDI.Usuario, Literal('genis', datatype=XSD.string)))
    viajesFinalizadosDB.add((ECSDI['viaje3'], ECSDI.DiaDePartida, Literal('2019-05-01', datatype=XSD.date)))
    viajesFinalizadosDB.add((ECSDI['viaje3'], ECSDI.DiaDeRetorno, Literal('2019-05-05', datatype=XSD.date)))
    viajesFinalizadosDB.add((ECSDI['viaje3'], ECSDI.precio_total, Literal(100, datatype=XSD.float)))
    viajesFinalizadosDB.add((ECSDI['viaje3'], ECSDI.LugarDePartida, Literal('BCN', datatype=XSD.string)))
    viajesFinalizadosDB.add((ECSDI['viaje3'], ECSDI.LugarDeLlegada, Literal('MAD', datatype=XSD.string)))
    viajesFinalizadosDB.add((ECSDI['viaje3'], ECSDI.grado_ludica, Literal(0, datatype=XSD.integer)))
    viajesFinalizadosDB.add((ECSDI['viaje3'], ECSDI.grado_cultural, Literal(1, datatype=XSD.integer)))
    viajesFinalizadosDB.add((ECSDI['viaje3'], ECSDI.grado_festivo, Literal(2, datatype=XSD.integer)))

    logger.info(viajesFinalizadosDB.serialize(format='xml'))
    viajesFinalizadosDB.serialize(destination=file_path_satisfaccion, format='xml')


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


def agentbehavior2():
    interval = 30  # Trigger the process every 10 seconds
    try:
        while True:
            enviar_recomendaciones()
            time.sleep(interval)
    except KeyboardInterrupt:
        print("Agent behavior 1 interrupted by KeyboardInterrupt")


if __name__ == '__main__':
    os.makedirs(os.path.dirname(file_path_satisfaccion), exist_ok=True)
    os.makedirs(os.path.dirname(file_path_viajes_recomendaciones), exist_ok=True)
    inicializarViajesFinalizadosDataTesing()  # TODO data para testing
    # Ponemos en marcha los behaviors
    ab1 = Process(target=agentbehavior1, args=(cola1,))
    ab1.start()

    ab2 = Process(target=agentbehavior2)
    ab2.start()

    # Ponemos en marcha el servidor
    app.run(host=hostname, port=port)

    # Esperamos a que acaben los behaviors
    ab1.join()
    ab2.join()
    logger.info('The End')
