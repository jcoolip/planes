# flight tracker
# app.py

import json
import requests
import psycopg
import time
from datetime import datetime
from math import atan2, cos, radians, sin, sqrt

def load_config():
    with open('config.json', 'r') as f:
        config = json.load(f)
    return config

def get_db(config):
    # Connect to an existing database
    return psycopg.connect(f"host={config['host']} dbname={config['database']} user={config['user']} password={config['password']}")


def distance_miles(lat1, lon1, lat2, lon2):
    earth_radius_miles = 3958.8

    lat1 = radians(lat1)
    lon1 = radians(lon1)
    lat2 = radians(lat2)
    lon2 = radians(lon2)

    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1

    a = (
        sin(delta_lat / 2) ** 2
        + cos(lat1) * cos(lat2) * sin(delta_lon / 2) ** 2
    )

    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    return earth_radius_miles * c

def upsert_aircraft(cur, row):
    cur.execute(
        """
        INSERT INTO aircraft (
            hex,
            registration,
            aircraft_type,
            description,
            db_flags,
            first_seen,
            last_seen,
            owner_operator,
            category
        )
        VALUES (%s, %s, %s, %s, %s, NOW(), NOW(), %s, %s)
        ON CONFLICT (hex)
        DO UPDATE SET
            registration = COALESCE(
                EXCLUDED.registration,
                aircraft.registration
            ),
            aircraft_type = COALESCE(
                EXCLUDED.aircraft_type,
                aircraft.aircraft_type
            ),
            description = COALESCE(
                EXCLUDED.description,
                aircraft.description
            ),
            db_flags = EXCLUDED.db_flags,
            last_seen = NOW(),
            owner_operator = COALESCE(
                EXCLUDED.owner_operator,
                aircraft.owner_operator
            ),
            category = COALESCE(
                EXCLUDED.category,
                aircraft.category
            )
        """,
        (
            row["hex"],
            row["registration"],
            row["aircraft_type"],
            row["description"],
            row["db_flags"],
            row["owner_operator"],
            row["category"],
        ),
    )

def insert_observation(cur, row):
    cur.execute(
        """
        INSERT INTO aircraft_observations (
            aircraft_hex,
            callsign,
            latitude,
            longitude,
            distance_miles,
            altitude_ft,
            on_ground,
            ground_speed,
            track_degrees,
            track_direction,
            baro_rate,
            emergency,
            seen_seconds
        )
        VALUES (
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s
        )
        """,
        (
            row["hex"],
            row["callsign"],
            row["lat"],
            row["lon"],
            row["distance_miles"],
            row["altitude_ft"],
            row["on_ground"],
            row["ground_speed"],
            row["track_deg"],
            row["track_dir"],
            row["baro_rate"],
            row["emergency"],
            row["seen"],
        ),
    )

def fetch_flights(config):
    url = (
        f"{config['url']}"
        f"{config['lat']}/"
        f"{config['lon']}/"
        f"{config['area']}"
    )

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

def assign_flights(flights, config):
    data = []

    for flight in flights:

        track = flight.get('track')

        altitude = flight.get("alt_baro")
        if altitude == "ground":
            altitude_ft = None
            on_ground = True
        elif altitude is None:
            altitude_ft = None
            on_ground = False
        else:
            altitude_ft = int(altitude)
            on_ground = False

        aircraft_lat = flight.get("lat")
        aircraft_lon = flight.get("lon")

        if aircraft_lat is not None and aircraft_lon is not None:
            distance = distance_miles(
                float(config["lat"]),
                float(config["lon"]),
                aircraft_lat,
                aircraft_lon,
            )
        else:
            distance = None

        row = {
            "hex": flight.get("hex"),
            "callsign": (
                flight["flight"].strip()
                if flight.get("flight")
                else None
            ),
            "registration": flight.get("r"),
            "aircraft_type": flight.get("t"),
            "description": flight.get("desc"),

            "lat": aircraft_lat,
            "lon": aircraft_lon,
            "distance_miles": round(distance, 2) if distance is not None else None,

            "altitude_ft": altitude_ft,
            "on_ground": on_ground,

            "ground_speed": flight.get("gs"),

            "track_deg": track,
            "track_dir": deg_to_compass(track),

            "baro_rate": flight.get("baro_rate"),
            "emergency": flight.get("emergency"),
            "seen": flight.get("seen"),
            "messages": flight.get("messages"),
            "db_flags": flight.get("dbFlags", 0),

            "owner_operator": flight.get("ownOp"),
            "category": flight.get("category")

        }    

        data.append(row)
    return data

config = load_config()



while True:
    try:
        response_data = fetch_flights(config)
        flights = response_data.get("ac", [])
        data = assign_flights(flights, config)

        stored = 0

        with get_db(config) as conn:
            with conn.cursor() as cur:
                for row in data:
                    if row["hex"] is None:
                        continue

                    upsert_aircraft(cur, row)
                    insert_observation(cur, row)
                    stored += 1
        timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
        print(f"{timestamp} Stored {stored} aircraft observations")

    except requests.RequestException as exc:
        print(f"API error: {exc}")

    except psycopg.Error as exc:
        print(f"Database error: {exc}")

    except Exception as exc:
        print(f"Unexpected error: {exc}")

    time.sleep(config.get("poll_interval", 20))
