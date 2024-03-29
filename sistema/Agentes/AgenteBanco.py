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

from flask import Flask, render_template, request
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

# Logging
logger = config_logger(level=1)

# parsing de los parametros de la linea de comandos
args = parser.parse_args()

# Configuration stuff
if args.port is None:
    port = 9008
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
AgenteBanco = Agent('AgenteBanco',
                                    agn.AgenteBanco,
                                    'http://%s:%d/comm' % (hostaddr, port),
                                    'http://%s:%d/Stop' % (hostaddr, port))

# Directory agent address
AgenteDirectorio = Agent('AgenteDirectorio',
                       agn.Directory,
                       'http://%s:%d/Register' % (dhostname, dport),
                       'http://%s:%d/Stop' % (dhostname, dport))

# Global hospedajeDB triplestore
cuentas_corrientes = Graph()

def init_cuentas_corrientes():
    # Se inician cuentas corrientes con solo nombre de usuario y numero de tarjeta de credito
    nombres = ['Pepe', 'Juan', 'Maria', 'Luis', 'Ana', 'Paco', 'Lola', 'Rosa', 'Pablo', 'Sara']
    tarjetas = ['123456789', '987654321', '123123123', '456456456', '789789789', '321321321', '654654654', '987987987', '159159159', '753753753']
    for i,n in enumerate(nombres):
        cuenta = ECSDI['CuentaCorriente/' + n]
        cuentas_corrientes.add((cuenta, RDF.type, ECSDI.CuentaCorriente))
        cuentas_corrientes.add((cuenta, ECSDI.nombre, Literal(n, datatype=XSD.string)))
        cuentas_corrientes.add((cuenta, ECSDI.numero_tarjeta, Literal(tarjetas[i], datatype=XSD.string)))
        cuentas_corrientes.add((cuenta, ECSDI.saldo, Literal(10000, datatype=XSD.float)))

init_cuentas_corrientes()


def obten_cuentas_corrientes():
    ccs = []
    for s,p,o in cuentas_corrientes.triples((None, RDF.type, ECSDI.CuentaCorriente)):
        cuenta = {}
        cuenta['nombre'] = cuentas_corrientes.value(subject=s, predicate=ECSDI.nombre).toPython()
        cuenta['numero_tarjeta'] = cuentas_corrientes.value(subject=s, predicate=ECSDI.numero_tarjeta).toPython()
        cuenta['saldo'] = cuentas_corrientes.value(subject=s, predicate=ECSDI.saldo).toPython()
        ccs.append(cuenta)
    return ccs
       
        

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

    gr = registerAgent(AgenteBanco, AgenteDirectorio, DSO.AgenteBanco, getMessageCount())
    return gr



@app.route("/iface", methods=['GET', 'POST'])
def browser_iface():
    """content
    Permite la comunicacion con el agente via un navegador
    via un formulario
    """
    return render_template('cuentas_bancarias.html', cuentas=obten_cuentas_corrientes())


@app.route("/stop")
def stop():
    """
    Entrypoint que para el agente

    :return:
    """
    tidyup()
    shutdown_server()
    return "Parando Servidor"


def process_payment(gm, content):
    print("Processing payment")
    price_to_pay = gm.value(subject=content, predicate=ECSDI.precio_total).toPython()
    tarjeta = gm.value(subject=content, predicate=ECSDI.numero_tarjeta)
    print("Price to pay: ", price_to_pay)

    gr = Graph()
    IAA = Namespace('IAActions')
    gr.bind('ECSDI', ECSDI)
    gr.bind('foaf', FOAF)
    gr.bind('ia', IAA)


    # Get the payment info

    # Check if the payment is accepted
    global cuentas_corrientes
    cc_subject = cuentas_corrientes.value(predicate=ECSDI.numero_tarjeta, object=Literal(tarjeta, datatype=XSD.string))

    saldo_actual = cuentas_corrientes.value(subject=cc_subject, predicate=ECSDI.saldo).toPython()
    print("Saldo actual: ", saldo_actual)

    if saldo_actual < price_to_pay:
        rechazo = ECSDI['Rechazo-' + str(getMessageCount())]
        gr.add((rechazo, RDF.type, ECSDI.Rechazo))
        gr.add((rechazo, ECSDI.transaccion, content))
        gr.add((rechazo, ECSDI.motivo, Literal("Saldo insuficiente", datatype=XSD.string)))
        return build_message(gr,
                                 ACL.inform,
                                 sender=AgenteBanco.uri,
                                 msgcnt=mss_cnt,
                                 content=rechazo)
    
    # Update the balance
    cuentas_corrientes.set((cc_subject, ECSDI.saldo, Literal(saldo_actual - price_to_pay, datatype=XSD.float)))

    # Send the confirmation
    confirmacion = ECSDI['Confirmacion-' + str(getMessageCount())]
    gr.add((confirmacion, RDF.type, ECSDI.Confirmacion))
    gr.add((confirmacion, ECSDI.transaccion, content))
    return build_message(gr,
                                ACL.inform,
                                sender=AgenteBanco.uri,
                                msgcnt=mss_cnt,
                                content=confirmacion)



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
        gr = build_message(Graph(), ACL['not-understood'], sender=AgenteBanco.uri, msgcnt=getMessageCount())
    else:
        # Obtenemos la performativa
        perf = msgdic['performative']

        if perf != ACL.request:
            # Si no es un request, respondemos que no hemos entendido el mensaje
            gr = build_message(Graph(), ACL['not-understood'], sender=AgenteBanco.uri, msgcnt=getMessageCount())
        else:
            # Extraemos el objeto del contenido que ha de ser una accion de la ontologia de acciones del agente
            # de registro

            # Averiguamos el tipo de la accion
            if 'content' in msgdic:
                content = msgdic['content']
                accion = gm.value(subject=content, predicate=RDF.type)

                if accion == ECSDI.Transaccion:
                    logger.info('Transaccion Recibida')

                    gr = process_payment(gm, content)
                    
                else:
                    # Si no es ninguna de las acciones conocontentcidas, respondemos que no hemos entendido el mensaje
                    gr = build_message(Graph(), ACL['not-understood'], sender=AgenteBanco.uri, msgcnt=getMessageCount())

            else:
                print('No content')
                gr = build_message(Graph(), ACL['not-understood'], sender=AgenteBanco.uri, msgcnt=getMessageCount())
    
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
    #gr = register_message()

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
