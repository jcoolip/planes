# flight tracker
# app.py

import json
import requests
import psycopg

def load_config():
    with open('config.json', 'r') as f:
        config = json.load(f)
    return config

def get_db(config):
    # Connect to an existing database
    return psycopg.connect(f"dbname={config['database']} user={config['user']}")

# def insert_rows(conn):

#         # Open a cursor to perform database operations
#         with conn.cursor() as cur:

#             # Pass data to fill a query placeholders and let Psycopg perform
#             # the correct conversion (no SQL injections!)
#             cur.execute(
#                 "INSERT INTO aircraft (hex, registration, aircraft_type, description, db_flags, first_seen, last_seen) VALUES (%s, %s, %s, %s, %s, %s, %s)",
#                 (100, "abc'def"))

#             # Make the changes to the database persistent
#             conn.commit()

def fetch_flights(config):
    url = config['url'] + config['area']
    response = requests.get(url, timeout=10)
    response.raise_for_status()

    return response.json()

def deg_to_compass(deg):
    try:
        d = float(deg)
    except (TypeError, ValueError):
        return None
    directions = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    idx = int((d / 45.0) + 0.5) % 8
    return directions[idx]

config = load_config()
# conn = get_db(config)
print(f"{config['url']+config['area']}")
f = fetch_flights(config)
total = f.get('total', 0)
flights = f.get('ac', [])
print(f"Aircraft reported: {total}")

data = []

for flight in flights:

    track = flight.get('track')
    altitude = flight.get('alt_baro')
    if altitude == "ground":
        altitude_text = "On ground"
    elif altitude is None:
        altitude_text = "Unknown altitude"
    else:
        altitude_text = f"{altitude:,} ft"

    row = {
        "hex": flight.get('hex'),
        "callsign": (flight.get('flight') or "Unknown callsign").strip(),
        "registration": flight.get('r') or "Unknown registration",
        "aircraft_type": flight.get('t') or "Unknown Type",
        "description": flight.get('desc') or "Unknown description",

        "lat": flight.get('lat'),
        "lon": flight.get('lon'),
        "alt_baro": flight.get('alt_baro'),
        "ground_speed": flight.get('gs'),

        "track_deg": track,
        "track_dir": deg_to_compass(track),

        "baro_rate": flight.get('baro_rate'),
        "emergency": flight.get('emergency'),
        "seen": flight.get('seen'),
        "messages": flight.get('messages'),
        "db_flags": flight.get('dbFlags', 0)
    }

    data.append(row)

for row in data:
    print(row)
