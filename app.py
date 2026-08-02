# flight tracker
# app.py

import json
import requests
import psycopg
import time
from datetime import datetime

def load_config():
    with open('config.json', 'r') as f:
        config = json.load(f)
    return config

def get_db(config):
    # Connect to an existing database
    return psycopg.connect(f"host={config['host']} dbname={config['database']} user={config['user']} password={config['password']}")

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
                last_seen
            )
            VALUES (%s, %s, %s, %s, %s, NOW(), NOW())
            ON CONFLICT (hex)
            DO UPDATE SET
                registration = EXCLUDED.registration,
                aircraft_type = EXCLUDED.aircraft_type,
                description = EXCLUDED.description,
                db_flags = EXCLUDED.db_flags,
                last_seen = NOW()
        """,
        (
            row["hex"],
            row["registration"],
            row["aircraft_type"],
            row["description"],
            row["db_flags"],
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
            %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s
        )
        """,
        (
            row["hex"],
            row["callsign"],
            row["lat"],
            row["lon"],
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

def assign_flights(flights):
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

            "lat": flight.get("lat"),
            "lon": flight.get("lon"),

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
        }    

        data.append(row)
    return data

config = load_config()



while True:
    try:
        response_data = fetch_flights(config)
        flights = response_data.get("ac", [])
        data = assign_flights(flights)

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
