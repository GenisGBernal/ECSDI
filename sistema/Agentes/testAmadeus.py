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
                    ECSDI:viaje_ciudad {'<'+city+'>'}.
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
    cityDeparture = 'LON'
    cityArrival = 'BCN'
    departureDate='2023-09-01'
    returnDate='2023-09-15'
    transport = 'avion'
    currency='EUR'

    response = amadeus.shopping.flight_offers_search.get(
        originLocationCode=cityDeparture,
        destinationLocationCode=cityArrival,
        departureDate=departureDate,
        returnDate=returnDate,
        adults=1,
        currencyCode=currency,
        max=20)

    print("TOTAL NUMBER OF FLIGHTS: " + str(len(response.data)))

    transporte = ECSDI[transport]
    ciudadSalida = ECSDI[cityDeparture]
    ciudadLlegada = ECSDI[cityArrival]
    fechaSalida = ECSDI[departureDate]
    fechaLlegada = ECSDI[returnDate]

    transporteDB.add((fechaSalida, RDF.type, ECSDI.Fecha))
    transporteDB.add((fechaLlegada, RDF.type, ECSDI.Fecha))
    transporteDB.add((ciudadSalida, RDF.type, ECSDI.Ciudad))
    transporteDB.add((ciudadLlegada, RDF.type, ECSDI.Ciudad))
    transporteDB.add((transporte, RDF.type, ECSDI.Transporte))

    for f in response.data:
        flight_id = str(uuid.uuid4())
        flight_price= float(f['price']['grandTotal'])

        identificador = ECSDI[flight_id]

        transporteDB.add((ECSDI[identificador], ECSDI.identifcador, Literal(flight_id, datatype=XSD.string)))
        transporteDB.add((ECSDI[identificador], RDF.type, ECSDI.BilleteIdaVuelta))
        transporteDB.add((ECSDI[identificador], ECSDI.precio, Literal(flight_price, datatype=XSD.float)))
        transporteDB.add((ECSDI[identificador], ECSDI.viaje_transporte, transporte))
        transporteDB.add((ECSDI[identificador], ECSDI.ciudadSalida, ciudadSalida))
        transporteDB.add((ECSDI[identificador], ECSDI.ciudadLlegada, ciudadLlegada))
        transporteDB.add((ECSDI[identificador], ECSDI.fechaSalida, fechaSalida))
        transporteDB.add((ECSDI[identificador], ECSDI.fechaLlegada, fechaLlegada))

    print(transporteDB.serialize(format='turtle'))

    search_count = 0

    flights_from_london = f"""
    SELECT ?billete ?identificador ?precio
    WHERE {{
        ?billete rdf:type ECSDI:BilleteIdaVuelta;
                ECSDI:identifcador ?identificador;
                ECSDI:precio ?precio;
    }}
    """
    print(flights_from_london)

    # Execute the query
    results = transporteDB.query(flights_from_london, initNs={'ECSDI': ECSDI, 'rdf': RDF})

    # Process the results
    for row in results:
        billete = row['billete']
        identificador = row['identificador']
        precio = row['precio']

        # Do something with the billete, identificador, and precio values
        print('Billete:', billete)
        print('Identificador:', identificador)
        print('Precio:', precio)
        print('---')

except ResponseError as error:
    print(error)





# gmess = Graph()
#     gmess.bind('ECSDI', ECSDI)
#     hospedaje_mess_uri = ECSDI['TomaHospedaje' + str(getMessageCount())]
#     gmess.add((hospedaje_mess_uri, RDF.type, ECSDI.QuieroHospedaje))
#     gmess.add((hospedaje_mess_uri, ECSDI.viaje_ciudad, ECSDI['LON']))
#     send_message(build_message(gmess, ACL['request'], sender=AgentePlanificador.uri, msgcnt=getMessageCount()) , )
