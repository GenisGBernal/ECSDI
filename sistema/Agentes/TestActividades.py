
import turtle
from rdflib import XSD, Graph, Namespace, Literal
from rdflib.namespace import FOAF, RDF

from amadeus import Client, ResponseError

from AgentUtil.OntoNamespaces import ECSDI

AMADEUS_KEY = '8zfjCOSbBMc4MgaOkibZ4ydWXxR4mljG'
AMADEUS_SECRET = 'yGTFfTOPGHNzIIZe'

amadeus = Client(
    client_id=AMADEUS_KEY,
    client_secret=AMADEUS_SECRET
)

actividadesDB = Graph()


response = amadeus.reference_data.locations.points_of_interest.get(latitude=41.397896, longitude=2.165111, radius=5, categories="NIGHTLIFE")
for r in response.data:
    actividadesDB.add((ECSDI['actividad/'+r['id']], RDF.type, ECSDI.actividad))
    actividadesDB.add((ECSDI['actividad/'+r['id']], ECSDI.tipo_actividad, ECSDI.tipo_festiva))
    actividadesDB.add((ECSDI['actividad/'+r['id']], ECSDI.subtipo_actividad, Literal(r['subType'], datatype=XSD.string)))
    actividadesDB.add((ECSDI['actividad/'+r['id']], ECSDI.nombre_actividad, Literal(r['name'], datatype=XSD.string)))
    for tag in r['tags']:
        actividadesDB.add((ECSDI['actividad/'+r['id']], ECSDI.tag_actividad, Literal(tag, datatype=XSD.string)))
    
print(actividadesDB.serialize(format='turtle'))