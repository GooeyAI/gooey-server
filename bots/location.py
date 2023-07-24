import googlemaps

import pygsheets
import pandas as pd

#authorization
gc = pygsheets.authorize(service_file="/Users/eliweise/ddgai/serviceAccountKey.json")

# Create empty dataframe
df = pd.DataFrame()

gmaps = googlemaps.Client(key='AIzaSyC7j8WI-P_BZQogR809B2QbaH_aP1KsVeM')

location: str = "busia"

geocode_result = gmaps.geocode(location)

# Create a column
df["location"] = [location]
df["JSON"] = [geocode_result]
df["formatted address"] = [geocode_result[0]["formatted_address"]]
df["latitude and longitude"] = [geocode_result[0]["geometry"]["location"]]

#open the google spreadsheet (where 'PY to Gsheet Test' is the name of my sheet)
sh = gc.open("saved locations")

#select the first sheet 
wks = sh[0]

#update the first sheet with df, starting at cell A1. 
wks.set_dataframe(df,(1,1))