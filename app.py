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

def upsert_active_aircraft(cur, row):
    cur.execute(
        """
        INSERT INTO active_aircraft (
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
            entered_at,
            last_seen_at,
            closest_distance_miles,
            closest_at,
            closest_altitude_ft,
            minimum_altitude_ft,
            maximum_altitude_ft,
            maximum_ground_speed,
            observation_count,
            entry_latitude,
            entry_longitude,
            entry_altitude_ft,
            entry_distance_miles
        )
        VALUES (
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s,
            NOW(), NOW(),
            %s, NOW(), %s,
            %s, %s, %s,
            1, %s, %s, %s, %s
        )
        ON CONFLICT (aircraft_hex)
        DO UPDATE SET
            callsign = COALESCE(EXCLUDED.callsign, active_aircraft.callsign),
            latitude = EXCLUDED.latitude,
            longitude = EXCLUDED.longitude,
            distance_miles = EXCLUDED.distance_miles,
            altitude_ft = EXCLUDED.altitude_ft,
            on_ground = EXCLUDED.on_ground,
            ground_speed = EXCLUDED.ground_speed,
            track_degrees = EXCLUDED.track_degrees,
            track_direction = EXCLUDED.track_direction,
            baro_rate = EXCLUDED.baro_rate,
            emergency = EXCLUDED.emergency,
            last_seen_at = NOW(),

            closest_distance_miles = CASE
                WHEN active_aircraft.closest_distance_miles IS NULL
                    THEN EXCLUDED.distance_miles
                WHEN EXCLUDED.distance_miles IS NULL
                    THEN active_aircraft.closest_distance_miles
                ELSE LEAST(
                    active_aircraft.closest_distance_miles,
                    EXCLUDED.distance_miles
                )
            END,

            closest_at = CASE
                WHEN EXCLUDED.distance_miles IS NOT NULL
                 AND (
                    active_aircraft.closest_distance_miles IS NULL
                    OR EXCLUDED.distance_miles
                       < active_aircraft.closest_distance_miles
                 )
                    THEN NOW()
                ELSE active_aircraft.closest_at
            END,

            closest_altitude_ft = CASE
                WHEN EXCLUDED.distance_miles IS NOT NULL
                 AND (
                    active_aircraft.closest_distance_miles IS NULL
                    OR EXCLUDED.distance_miles
                       < active_aircraft.closest_distance_miles
                 )
                    THEN EXCLUDED.altitude_ft
                ELSE active_aircraft.closest_altitude_ft
            END,

            minimum_altitude_ft = CASE
                WHEN active_aircraft.minimum_altitude_ft IS NULL
                    THEN EXCLUDED.altitude_ft
                WHEN EXCLUDED.altitude_ft IS NULL
                    THEN active_aircraft.minimum_altitude_ft
                ELSE LEAST(
                    active_aircraft.minimum_altitude_ft,
                    EXCLUDED.altitude_ft
                )
            END,

            maximum_altitude_ft = CASE
                WHEN active_aircraft.maximum_altitude_ft IS NULL
                    THEN EXCLUDED.altitude_ft
                WHEN EXCLUDED.altitude_ft IS NULL
                    THEN active_aircraft.maximum_altitude_ft
                ELSE GREATEST(
                    active_aircraft.maximum_altitude_ft,
                    EXCLUDED.altitude_ft
                )
            END,

            maximum_ground_speed = CASE
                WHEN active_aircraft.maximum_ground_speed IS NULL
                    THEN EXCLUDED.ground_speed
                WHEN EXCLUDED.ground_speed IS NULL
                    THEN active_aircraft.maximum_ground_speed
                ELSE GREATEST(
                    active_aircraft.maximum_ground_speed,
                    EXCLUDED.ground_speed
                )
            END,

            observation_count =
                active_aircraft.observation_count + 1
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

            row["distance_miles"],
            row["altitude_ft"],
            row["altitude_ft"],
            row["altitude_ft"],
            row["ground_speed"],
            row["lat"],
            row["lon"],
            row["altitude_ft"],
            row["distance_miles"],
        ),
    )

def finalize_stale_flyovers(cur, timeout_minutes=2):
    cur.execute(
        """
        WITH stale AS (
            DELETE FROM active_aircraft
            WHERE last_seen_at < NOW() - (%s * INTERVAL '1 minute')
            RETURNING *
        )
        INSERT INTO flyovers (
            aircraft_hex,
            callsign,
            entered_at,
            exited_at,

            entry_latitude,
            entry_longitude,
            entry_altitude_ft,
            entry_distance_miles,

            exit_latitude,
            exit_longitude,
            exit_altitude_ft,
            exit_distance_miles,

            closest_distance_miles,
            closest_at,
            closest_altitude_ft,

            minimum_altitude_ft,
            maximum_altitude_ft,
            maximum_ground_speed,

            observation_count
        )
        SELECT
            aircraft_hex,
            callsign,
            entered_at,
            last_seen_at,

            entry_latitude
            entry_longitude
            entry_altitude_ft
            entry_distance_miles

            latitude,
            longitude,
            altitude_ft,
            distance_miles,

            closest_distance_miles,
            closest_at,
            closest_altitude_ft,

            minimum_altitude_ft,
            maximum_altitude_ft,
            maximum_ground_speed,

            observation_count
        FROM stale
        """,
        (timeout_minutes,),
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
                    upsert_active_aircraft(cur, row)
                    insert_observation(cur, row)
                    stored += 1
                
                finalize_stale_flyovers(cur, timeout_minutes=2)
        timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
        print(f"{timestamp} Stored {stored} aircraft observations")

    except requests.RequestException as exc:
        print(f"API error: {exc}")

    except psycopg.Error as exc:
        print(f"Database error: {exc}")

    except Exception as exc:
        print(f"Unexpected error: {exc}")

    time.sleep(config.get("poll_interval", 20))
