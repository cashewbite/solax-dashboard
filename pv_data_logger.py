from suncalc import get_position
from datetime import datetime, timezone
import ntplib
from zoneinfo import ZoneInfo
import requests
import pandas as pd
import os
import sys
from cryptography.fernet import Fernet
import io
import threading

# ------------------------------------------------------------
# GLOBAL TIMEOUT (50 Sekunden)
# ------------------------------------------------------------
TIMEOUT_SECONDS = 50

def timeout_handler():
    print("Zeitlimit überschritten – Skript wird beendet.")
    sys.exit(3)   # Exit-Code 3 = Timeout

# Starte globalen Timeout
timer = threading.Timer(TIMEOUT_SECONDS, timeout_handler)
timer.start()

# ------------------------------------------------------------
# NTP TIME
# ------------------------------------------------------------
def get_internet_time():
    try:
        c = ntplib.NTPClient()
        response = c.request("pool.ntp.org", version=3)
        utc_time = datetime.fromtimestamp(response.tx_time, timezone.utc)
        return utc_time.astimezone(ZoneInfo("Europe/Berlin"))
    except Exception as e:
        print("NTP Fehler:", e)
        sys.exit(2)

NOW = get_internet_time().replace(second=0, microsecond=0)
print("Internet Time erhalten")

# ------------------------------------------------------------
# ENVIRONMENT VARIABLES
# ------------------------------------------------------------
API_URL = os.getenv("API_URL")
TOKEN_ID = os.getenv("TOKEN_ID")
WIFI_SN = os.getenv("WIFI_SN")
LAT = float(os.getenv("LAT"))
LON = float(os.getenv("LON"))
FERNET_KEY = os.getenv("FERNET_KEY")

cipher = Fernet(FERNET_KEY.encode())

# ------------------------------------------------------------
# ENCRYPTED CSV HANDLING
# ------------------------------------------------------------
def load_encrypted_csv(path_enc):
    try:
        with open(path_enc, "rb") as f:
            encrypted = f.read()
        decrypted = cipher.decrypt(encrypted)
        return pd.read_csv(io.BytesIO(decrypted))
    except Exception as e:
        print("CSV Ladefehler:", e)
        sys.exit(6)

def dump_encrypted_csv(df, path_enc):
    try:
        buffer = io.BytesIO()
        df.to_csv(buffer, index=False)
        encrypted = cipher.encrypt(buffer.getvalue())
        with open(path_enc, "wb") as f:
            f.write(encrypted)
    except Exception as e:
        print("CSV Speicherfehler:", e)
        sys.exit(6)

# ------------------------------------------------------------
# SOLAX API (ohne individuellen Timeout)
# ------------------------------------------------------------
headers = {
    "tokenId": TOKEN_ID,
    "Content-Type": "application/json"
}
payload = {"wifiSn": WIFI_SN}
# API REQUEST
def get_solax_data():
    try:
        response = requests.post(API_URL, headers=headers, json=payload)
        print("SolaX API-Status:", response.status_code)
        data = response.json()
        return data.get("result", {})
    except Exception as e:
        with open("log.txt", "a", encoding="utf-8") as f:
            f.write(str(e) + "\n")
        print("SolaX Fehler:", e)
        sys.exit(2)

data = get_solax_data()
print("SolaX Daten erhalten")
pv1 = data.get("powerdc1",0)
pv2 = data.get("powerdc2",0)

# ------------------------------------------------------------
# OPEN-METEO
# ------------------------------------------------------------
url = f"https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}&current=shortwave_radiation_instant,direct_radiation_instant,diffuse_radiation_instant,cloud_cover,temperature_2m,wind_speed_10m,relative_humidity_2m,visibility&timezone=Europe%2FBerlin"

try:
    data = requests.get(url).json()
except Exception as e:
    print("Open-Meteo Fehler:", e)
    sys.exit(2)

shortwave_radiation = data["current"]["shortwave_radiation_instant"]
direct_radiation = data["current"]["direct_radiation_instant"]
diffuse_radiation = data["current"]["diffuse_radiation_instant"]

cloudcover = data["current"]["cloud_cover"]
temperatur = data["current"]["temperature_2m"]
windspeed = data["current"]["wind_speed_10m"]

humidity = data["current"]["relative_humidity_2m"]
visibility = data["current"]["visibility"]

print("Open-Meteo Werte erhalten")

# ------------------------------------------------------------
# SUNCALC
# ------------------------------------------------------------
pos = get_position(NOW, LAT, LON)
altitude = pos["altitude"]
azimuth = pos["azimuth"]
print("SunCalc: altitude, azimuth erhalten")

# ------------------------------------------------------------
# DATAFRAME
# ------------------------------------------------------------
df = pd.DataFrame({
    "time": [NOW],
    "pv1": [round(pv1)],
    "pv2": [round(pv2)],
    "altitude": [round(altitude,2)],
    "azimuth": [round(azimuth,2)],

    "shortwave_radiation": [round(shortwave_radiation)],
    "direct_radiation": [round(direct_radiation)],
    "diffuse_radiation": [round(diffuse_radiation)],

    "cloudcover": [cloudcover],
    "temperatur": [round(temperatur)],
    "windspeed": [round(windspeed)],

    "humidity": [round(humidity)],
    "visibility": [round(visibility)/10]
})
int_cols = ["pv1","pv2", "shortwave_radiation","cloudcover",
            "direct_radiation","diffuse_radiation",
             "temperatur", "windspeed", "humidity", "visibility"]
df[int_cols] = df[int_cols].astype("Int64")

df["time"] = df["time"].dt.tz_localize(None).dt.floor("min")

# ------------------------------------------------------------
# FILE PATHS
# ------------------------------------------------------------
year = NOW.year
month = NOW.month

path = "data"
folder = os.path.join(path, f"{year}")
filename = f"{year}{month:02d}.csv"
filepath = os.path.join(folder, filename)

os.makedirs(folder, exist_ok=True)

# ------------------------------------------------------------
# MERGE & SAVE
# ------------------------------------------------------------
enc_path = filepath + ".enc"

if os.path.exists(enc_path):
    df_old = load_encrypted_csv(enc_path)
    df_old[int_cols] = df_old[int_cols].astype("Int64")
    df_all = pd.concat([df_old, df], ignore_index=True)
else:
    df_all = df

dump_encrypted_csv(df_all, enc_path)
# ------------------------------------------------------------
# STOP GLOBAL TIMER
# ------------------------------------------------------------
timer.cancel()

print("CSV gespeichert")
