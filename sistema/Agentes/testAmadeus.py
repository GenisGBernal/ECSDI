import amadeus
import uuid

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

# Hotels query
try:
    cityCode = 'LON'
    response = amadeus.reference_data.locations.hotels.by_city.get(cityCode=cityCode)
    # amadeus.shopping.hotel_offers_search.get(cityCode='LON')
    city = ECSDI[cityCode]
    hospedajeDB.add((city, RDF.type, ECSDI.Ciudad))
    print("TOTAL NUMBER OF HOTELS: " + str(len(response.data)))
    for h in response.data:
        hotel_name = h['name']
        hotel_id = h['hotelId']
        hospedajeDB.add((ECSDI[hotel_id], RDF.type, ECSDI.Hospedaje))
        hospedajeDB.add((ECSDI[hotel_id], ECSDI.identificador, Literal(hotel_name, datatype=XSD.string)))
        hospedajeDB.add((ECSDI[hotel_id], ECSDI.precio, Literal(100, datatype=XSD.float)))
        hospedajeDB.add((ECSDI[hotel_id], ECSDI.viaje_ciudad, city))

    print(hospedajeDB.serialize(format='turtle'))

    search_count = 0

    hotels_in_london = f"""
    SELECT ?identificador ?precio
    WHERE {{
        ?hospedaje rdf:type ECSDI:Hospedaje;
                    ECSDI:identificador ?identificador;
                    ECSDI:precio ?precio;
                    ECSDI:viaje_ciudad {'<' + city + '>'}.
    }}
    """
    print(hotels_in_london)

    # for s,p in hospedajeDB.query(hotels_in_london, initNs={'ECSDI': ECSDI}):
    #     search_count += 1
    #     print(s,p)
    # Testing city search
    # for a,b,c in hospedajeDB.triples((None, ECSDI.viaje_ciudad, city)):
    #     print(a,"Is an hotel in",c)
    # print("HOTELS IN " + cityCode + ": " + str(search_count))

except ResponseError as error:
    print(error)

# Flights query
try:
    lugar_partida = 'LON'
    lugar_llegada = 'BCN'
    dia_partida = '2023-09-01'
    dia_retorno = '2023-09-15'
    lugar_partida_ont = Literal(lugar_partida, datatype=XSD.string)
    lugar_llegada_ont = Literal(lugar_llegada, datatype=XSD.string)
    dia_partida_ont = Literal(dia_partida, datatype=XSD.string)
    dia_retorno_ont = Literal(dia_retorno, datatype=XSD.string)
    print("Entramos en REMOTE_TRANSPORT_SEARACH----------------------")
    transporteDB = Graph()

    # cityDeparture = 'LON'
    # cityArrival = 'BCN'
    # departureDate='2023-09-01'
    # returnDate='2023-09-15'
    print('Dia partida: ' + dia_partida)
    print('Dia partida ont: ' + dia_partida_ont)
    print('Dia retorno: ' + dia_retorno)
    print('Dia retorno ont: ' + dia_retorno_ont)
    print('Lugar partida: ' + lugar_partida)
    print('Lugar partida ont: ' + lugar_partida_ont)
    print('Lugar llegada: ' + lugar_llegada)
    print('Lugar llegada_ont: ' + lugar_llegada_ont)

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

    print("Entramos en FETCH_QUEIRED_DATA---------------------------")

    flights_matching = f"""
         SELECT ?identificador ?precio
    WHERE {{
        ?billete ECSDI:viaje_transporte ?viaje_transporte_param ;
                 ECSDI:identificador ?identificador ;
                 ECSDI:precio ?precio ;
                 ECSDI:DiaDePartida ?dia_partida_param .
        FILTER (?viaje_transporte_param = <{transporte}> && ?dia_partida_param = "{dia_partida}")
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
