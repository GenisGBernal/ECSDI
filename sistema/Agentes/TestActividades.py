
import datetime
import turtle
from rdflib import XSD, Graph, Namespace, Literal
from rdflib.namespace import FOAF, RDF

from amadeus import Client, ResponseError
import requests

from AgentUtil.OntoNamespaces import ECSDI


WEATHER_API_KEY = "a05dcb0b544eb16418da6f65fce9e345"

WEATHER_END_POINT = 'https://api.open-meteo.com/v1/forecast'
print(WEATHER_END_POINT)

fecha_hoy = datetime.date.today()

fecha_futura = fecha_hoy + datetime.timedelta(days=0)

print("Obteniendo previsión dia para hoy dia:" + str(fecha_hoy))

# r = requests.get(WEATHER_END_POINT, params={
#     'latitude': 41.397896,
#     'longitude': 2.165111,
#     'start_date': str(fecha_hoy),
#     'end_date': str(fecha_hoy),
#     'hourly':'weathercode'
# })

# def hay_lluvia(codigo):
#     return codigo > 40

# tiempo_por_horas = r.json()['hourly']['weathercode']

# hay_lluvia_matina = hay_lluvia(tiempo_por_horas[10])
# hay_lluvia_tarde = hay_lluvia(tiempo_por_horas[18])
# hay_lluvia_noche = hay_lluvia(tiempo_por_horas[22])

# print(hay_lluvia_matina)
# print(hay_lluvia_tarde)
# print(hay_lluvia_noche)
