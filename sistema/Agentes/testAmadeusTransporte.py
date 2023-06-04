import amadeus
import uuid
import random


from rdflib import XSD, Graph, Literal
from rdflib.namespace import RDF

from amadeus import Client, ResponseError
from pprint import PrettyPrinter

from AgentUtil.OntoNamespaces import ECSDI

hospedajeDB = Graph()
hospedajeDB.bind('ECSDI', ECSDI)

transporteDB = Graph()
transporteDB.bind('ECSDI', ECSDI)

AMADEUS_KEY = 'EiHVAHxxhgGwlEPZTZ4flG42U1x5QvMI'
AMADEUS_SECRET = 'n32zEDo4N2CAAtLB'

amadeus = Client(
    client_id=AMADEUS_KEY,
    client_secret=AMADEUS_SECRET
)
ppr = PrettyPrinter(indent=4)

# Flights query
try:
    lugar_partida = 'LON'
    lugar_llegada = 'BCN'
    dia_partida = '2023-09-01'
    dia_retorno = '2023-09-15'
    print("Entramos en REMOTE_TRANSPORT_SEARACH----------------------")
    transporteDB = Graph()

    # cityDeparture = 'LON'
    # cityArrival = 'BCN'
    # departureDate='2023-09-01'
    # returnDate='2023-09-15'
    print('Dia partida: ' + dia_partida)
    print('Dia retorno: ' + dia_retorno)
    print('Lugar partida: ' + lugar_partida)
    print('Lugar llegada: ' + lugar_llegada)

    response = amadeus.shopping.flight_offers_search.get(
        originLocationCode=lugar_partida,
        destinationLocationCode=lugar_llegada,
        departureDate=dia_partida,
        returnDate=dia_retorno,
        adults=1,
        currencyCode='EUR',
        max=2)

    print("TOTAL NUMBER OF FLIGHTS: " + str(len(response.data)))

    transporte = ECSDI['avion']

    for f in response.data:
        flight_id = str(uuid.uuid4())
        flight_price = float(f['price']['grandTotal'])

        identificador = ECSDI[flight_id]

        transporteDB.add((ECSDI[identificador], ECSDI.identificador, Literal(flight_id, datatype=XSD.string)))
        transporteDB.add((ECSDI[identificador], ECSDI.precio, Literal(flight_price, datatype=XSD.float)))
        transporteDB.add((ECSDI[identificador], ECSDI.viaje_transporte, transporte))
        transporteDB.add((ECSDI[identificador], ECSDI.LugarDePartida, Literal(lugar_partida, datatype=XSD.string)))
        transporteDB.add((ECSDI[identificador], ECSDI.LugarDeLlegada, Literal(lugar_llegada, datatype=XSD.string)))
        transporteDB.add((ECSDI[identificador], ECSDI.DiaDePartida, Literal(dia_partida, datatype=XSD.string)))
        transporteDB.add((ECSDI[identificador], ECSDI.DiaDeRetorno, Literal(dia_retorno, datatype=XSD.string)))

    print(transporteDB.serialize(format='turtle'))

    print("Entramos en OBTENER_TRANSPORTE_OPTIMO----------------------")

    identificadores = list(transporteDB.triples((None, ECSDI.identificador, None)))
    viaje_random = random.choice(identificadores)[0]
    print(viaje_random)

    # Buscamos info viaje
    info_viaje = list(transporteDB.triples((viaje_random, None, None)))

    viaje_elegido = Graph()
    viaje_elegido.bind('ECSDI', ECSDI)

    # Anadimos info viaje
    for i in info_viaje:
        viaje_elegido.add(i)

    print(viaje_elegido.serialize(format='turtle'))

    print("Acabamos OBTENER_TRANSPORTE_OPTIMO----------------------")

    print("Entramos en FETCH_QUEIRED_DATA---------------------------")

    flights_matching = f"""
         SELECT ?identificador ?precio
    WHERE {{
        ?billete ECSDI:viaje_transporte ?viaje_transporte_param ;
                 ECSDI:identificador ?identificador ;
                 ECSDI:precio ?precio ;
                 ECSDI:DiaDePartida ?dia_partida_param ;
                 ECSDI:DiaDeRetorno ?dia_retorno_param ;
                 ECSDI:LugarDePartida ?lugar_partida_param ;
                 ECSDI:LugarDeLlegada ?lugar_llegada_param .
        FILTER (?viaje_transporte_param = <{transporte}>
                && ?dia_partida_param = "{dia_partida}"
                && ?dia_retorno_param = "{dia_retorno}"
                && ?lugar_partida_param = "{lugar_partida}"
                && ?lugar_llegada_param = "{lugar_llegada}")
    }}
    """
    print(flights_matching)

    resultsQuery = transporteDB.query(
        flights_matching,
        initNs={'ECSDI': ECSDI})

    transporte = ECSDI['avion']
    gr = Graph()
    search_count = 0
    print('Vuelos encontrados: ' + str(len(resultsQuery)))
    for row in resultsQuery:
        search_count += 1
        identificador = row['identificador']
        precio = row['precio']

        print('Identificador:', identificador)
        print('Precio:', precio)
        print('---')
        gr.add((ECSDI[identificador], ECSDI.identificador, Literal(identificador, datatype=XSD.string)))
        gr.add((ECSDI[identificador], ECSDI.viaje_transporte, transporte))
        gr.add((ECSDI[identificador], ECSDI.precio, Literal(precio, datatype=XSD.float)))
        gr.add((ECSDI[identificador], ECSDI.LugarDePartida, Literal(lugar_partida, datatype=XSD.string)))
        gr.add((ECSDI[identificador], ECSDI.LugarDeLlegada, Literal(lugar_llegada, datatype=XSD.string)))
        gr.add((ECSDI[identificador], ECSDI.DiaDePartida, Literal(dia_partida, datatype=XSD.string)))
        gr.add((ECSDI[identificador], ECSDI.DiaDeRetorno, Literal(dia_retorno, datatype=XSD.string)))

    print(gr.serialize(format='turtle'))
    
    print("ACABAMOS LA EJECUCION")

except ResponseError as error:
    print(error)
