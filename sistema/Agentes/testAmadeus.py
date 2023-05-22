import amadeus

from rdflib import XSD, Graph, Namespace, Literal
from rdflib.namespace import FOAF, RDF

from amadeus import Client, ResponseError
from pprint import PrettyPrinter

from AgentUtil.OntoNamespaces import ECSDI

hospedajeDB = Graph()
hospedajeDB.bind('ECSDI', ECSDI)

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

    #print(hospedajeDB.serialize(format='turtle'))

    search_count = 0
    # Testing city search
    city_search = hospedajeDB.triples((None, ECSDI.viaje_ciudad, city))
    if city_search is not None:
        for c in city_search:
            search_count += 1
    print("HOTELS IN " + cityCode + ": " + str(search_count))

except ResponseError as error:
    print(error)








# gmess = Graph()
#     gmess.bind('ECSDI', ECSDI)
#     hospedaje_mess_uri = ECSDI['TomaHospedaje' + str(getMessageCount())]
#     gmess.add((hospedaje_mess_uri, RDF.type, ECSDI.QuieroHospedaje))
#     gmess.add((hospedaje_mess_uri, ECSDI.viaje_ciudad, ECSDI['LON']))
#     send_message(build_message(gmess, ACL['request'], sender=AgentePlanificador.uri, msgcnt=getMessageCount()) , )

