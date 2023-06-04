from multiprocessing import Process, Queue
import logging
import argparse

from flask import Flask, request
from rdflib import Graph, Namespace, Literal
from rdflib.namespace import FOAF, RDF

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


def print_message(mssg):
    print("Process triggered!" + mssg)


def agentbehavior1(cola):
    interval = 10  # Trigger the process every 10 seconds
    try:
        while True:
            print_message("AGENT BEHAVIOR 1")
            time.sleep(interval)
    except KeyboardInterrupt:
        print("Agent behavior 1 interrupted by KeyboardInterrupt")


def agentbehavior2():
    interval = 5  # Trigger the process every 5 seconds
    try:
        while True:
            print_message("AGENT BEHAVIOR 2")
            time.sleep(interval)
    except KeyboardInterrupt:
        print("Agent behavior 2 interrupted by KeyboardInterrupt")


try:
    # Ponemos en marcha los behaviors
    ab1 = Process(target=agentbehavior1, args=(cola1,))
    ab1.start()

    ab2 = Process(target=agentbehavior2)
    ab2.start()

    print('The End')

except Exception as e:
    print("An exception occurred:", str(e))
