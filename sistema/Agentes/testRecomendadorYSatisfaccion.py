from multiprocessing import Process, Queue
import logging
import argparse

from flask import Flask, request
from rdflib import Graph, Namespace, Literal
from rdflib.namespace import FOAF, RDF, XSD
from datetime import datetime

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

from pprint import PrettyPrinter

from AgentUtil.OntoNamespaces import ECSDI

ppr = PrettyPrinter(indent=4)

import time
from multiprocessing import Process

# Cola de comunicacion entre procesos
cola1 = Queue()

viajesFinalizados = Graph()
viajesFinalizados.bind('ECSDI', ECSDI)
satisfaccionDB = Graph()
satisfaccionDB.bind('ECSDI', ECSDI)


def inicializamosBD():
    global viajesFinalizados

    viajesFinalizados.add((ECSDI['viaje1'], RDF.type, ECSDI.ViajeFinalizado))
    viajesFinalizados.add((ECSDI['viaje1'], ECSDI.identificador, Literal('viaje1', datatype=XSD.string)))
    viajesFinalizados.add((ECSDI['viaje1'], ECSDI.Usuario, Literal('usuario1', datatype=XSD.string)))
    viajesFinalizados.add((ECSDI['viaje1'], ECSDI.DiaDePartida, Literal('2023-09-01', datatype=XSD.string)))
    viajesFinalizados.add((ECSDI['viaje1'], ECSDI.DiaDeRetorno, Literal('2023-09-15', datatype=XSD.string)))
    viajesFinalizados.add((ECSDI['viaje1'], ECSDI.LugarDePartida, Literal('BCN', datatype=XSD.string)))
    viajesFinalizados.add((ECSDI['viaje1'], ECSDI.LugarDeLlegada, Literal('LON', datatype=XSD.string)))
    viajesFinalizados.add((ECSDI['viaje1'], ECSDI.tipo, Literal('avion', datatype=XSD.string)))

    viajesFinalizados.add((ECSDI['viaje1'], ECSDI.valorado, Literal(False, datatype=XSD.boolean)))

    viajesFinalizados.add((ECSDI['viaje2'], RDF.type, ECSDI.ViajeFinalizado))
    viajesFinalizados.add((ECSDI['viaje2'], ECSDI.identificador, Literal('viaje2', datatype=XSD.string)))
    viajesFinalizados.add((ECSDI['viaje2'], ECSDI.Usuario, Literal('usuario1', datatype=XSD.string)))
    viajesFinalizados.add((ECSDI['viaje2'], ECSDI.DiaDePartida, Literal('2023-10-01', datatype=XSD.string)))
    viajesFinalizados.add((ECSDI['viaje2'], ECSDI.DiaDeRetorno, Literal('2023-10-15', datatype=XSD.string)))
    viajesFinalizados.add((ECSDI['viaje2'], ECSDI.LugarDePartida, Literal('MAD', datatype=XSD.string)))
    viajesFinalizados.add((ECSDI['viaje2'], ECSDI.LugarDeLlegada, Literal('NYC', datatype=XSD.string)))
    viajesFinalizados.add((ECSDI['viaje2'], ECSDI.tipo, Literal('avion', datatype=XSD.string)))

    viajesFinalizados.add((ECSDI['viaje2'], ECSDI.valorado, Literal(True, datatype=XSD.boolean)))

    pass

def getInfoViajesNoValorados():
    viajesNoValorados = []

    for s, p, o in viajesFinalizados.triples((None, ECSDI.valorado, Literal(False, datatype=XSD.boolean))):
        viajesNoValorados.append(s)

    viajesAValorar = Graph()
    for viaje in viajesNoValorados:
        for s, p, o in viajesFinalizados.triples((viaje, None, None)):
            viajesAValorar.add((s, p, o))

    print(viajesAValorar.serialize(format='turtle'))
    pass


def agentbehavior1(cola):
    getInfoViajesNoValorados()
    pass


def agentbehavior2():
    interval = 60  # Trigger the process every 10 seconds
    try:
        while True:
            print("Ha pasado un minuto" + datetime.now().strftime("%d/%m/%Y %H:%M:%S"))
            time.sleep(interval)
    except KeyboardInterrupt:
        print("Agent behavior 1 interrupted by KeyboardInterrupt")


try:
    # Ponemos en marcha los behaviors
    inicializamosBD()

    ab1 = Process(target=agentbehavior1, args=(cola1,))
    ab1.start()

    ab2 = Process(target=agentbehavior2)
    ab2.start()

    print('The End')

except Exception as e:
    print("An exception occurred:", str(e))
