import time
import pandas as pd
from suncalc import get_position
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import requests
import io
import joblib
import streamlit as st
from cryptography.fernet import Fernet
import numpy as np

LAT = st.secrets["LAT"]
LON = st.secrets["LON"]

FERNET_KEY = st.secrets["FERNET_KEY"]
cipher = Fernet(FERNET_KEY.encode())

NOW = datetime.now(ZoneInfo("Europe/Berlin"))
heute = NOW.replace(hour=0, minute=0, second=0, microsecond=0)

FEATURE_ASSET_URL = "https://github.com/cashewbite/solax-dashboard/releases/download/data-model/feature_columns.joblib.enc"
MODEL_ASSET_URL = "https://github.com/cashewbite/solax-dashboard/releases/download/data-model/pv_model.joblib.enc"

def forcast_data(forecast_day):
    url = f"https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}&hourly=shortwave_radiation_instant,direct_radiation_instant,diffuse_radiation_instant,cloud_cover,temperature_2m,wind_speed_10m,relative_humidity_2m,visibility&timezone=Europe%2FBerlin&forecast_days={forecast_day}"
    try:
        data = requests.get(url).json()

        shortwave_radiation = data["hourly"]["shortwave_radiation_instant"][-24:]
        direct_radiation = data["hourly"]["direct_radiation_instant"][-24:]
        diffuse_radiation = data["hourly"]["diffuse_radiation_instant"][-24:]

        cloudcover = data["hourly"]["cloud_cover"][-24:]
        temperatur = data["hourly"]["temperature_2m"][-24:]
        windspeed = data["hourly"]["wind_speed_10m"][-24:]

        humidity = data["hourly"]["relative_humidity_2m"][-24:]
        visibility = data["hourly"]["visibility"][-24:]
    except Exception as e:
        print("API-Exception:")
        print(e)
        print("data:")
        print(data)
        return None

    altitude = [] # Höhe überm Horizont (0: Horizont, >0: über Horizont, <0: unter Horizont)
    azimuth = [] # Sonne ist in der Richtung (-1.57: Osten, 0: Sueden, 1.57: Westen, 3.14: Norden)
    time = []
    start = heute + timedelta(days=forecast_day-1)
    for i in range(24):
        t = start + timedelta(hours=i)
        pos = get_position(t, LAT, LON)
        altitude.append(round(pos["altitude"],2))
        azimuth.append(round(pos["azimuth"],2))
        time.append(t)

    df = pd.DataFrame({
        "time": time,
        "altitude": altitude,
        "azimuth": azimuth,

        "shortwave_radiation": shortwave_radiation,
        "direct_radiation": direct_radiation,
        "diffuse_radiation": diffuse_radiation,

        "cloudcover": cloudcover,
        "temperatur": temperatur,
        "windspeed": windspeed,

        "humidity": humidity,
        "visibility": visibility
    })
    df["time"] = pd.to_datetime(df["time"])
    df["hour"] = df["time"].dt.hour + df["time"].dt.minute/60
    df["hour_sin"] = np.sin(2 * np.pi * df["hour"] / 24)
    df["hour_cos"] = np.cos(2 * np.pi * df["hour"] / 24)
    df["time"] = df["time"].dt.tz_localize(None).dt.floor("min")

    df.pop("hour")

    print("Wettervorhersage erhalten für")
    print(start.date())
    return df


def predict_day(forecast_day=1):
    df = forcast_data(forecast_day)
    if df is None:
        return None
    times = df["time"]

    def load_encrypted(url):
        response = requests.get(url)
        response.raise_for_status()
        encrypted = response.content
        decrypted = cipher.decrypt(encrypted)
        buffer = io.BytesIO(decrypted)
        return joblib.load(buffer)

    model = load_encrypted(MODEL_ASSET_URL)
    feature_cols = load_encrypted(FEATURE_ASSET_URL)

    df = df[feature_cols]
    preds = model.predict(df)

    result = pd.DataFrame({
        "time": times,
        "pv1": preds[:, 0],
        "pv2": preds[:, 1],
    })
    result["pv1"] = result["pv1"].round().astype(int)
    result["pv2"] = result["pv2"].round().astype(int)

    # Nachtstunden auf 0 setzen
    hours = result["time"].dt.hour
    result.loc[(hours >= 23) | (hours <= 4), ["pv1", "pv2"]] = 0

    print("PV Vorhersage berechnet")
    return result

if __name__ == '__main__':
    start = time.time()
    print(predict_day())
    end = time.time()
    print(f"Laufzeit: {end - start:.2f} Sekunden")
