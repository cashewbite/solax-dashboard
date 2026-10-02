from datetime import datetime, timezone
import io
from cryptography.fernet import Fernet
from github import Github
import ntplib
import pandas as pd
import requests
import streamlit as st
from suncalc import get_position
from zoneinfo import ZoneInfo

def log_pv_data():
    # ------------------------------------------------------------
    # CONFIG & SECRETS 
    # ------------------------------------------------------------
    API_URL = st.secrets["API_URL"]
    TOKEN_ID = st.secrets["TOKEN_ID"]
    WIFI_SN = st.secrets["WIFI_SN"]
    LAT = float(st.secrets["LAT"])
    LON = float(st.secrets["LON"])
    FERNET_KEY = st.secrets["FERNET_KEY"]
    GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]

    cipher = Fernet(FERNET_KEY.encode())

    try:
        # 1. NTP TIME
        c = ntplib.NTPClient()
        response = c.request("pool.ntp.org", version=3)
        utc_time = datetime.fromtimestamp(response.tx_time, timezone.utc)
        NOW = utc_time.astimezone(ZoneInfo("Europe/Berlin")).replace(
            second=0, microsecond=0
        )
        print("Internet Time erhalten")

        # 2. SolaX API
        headers = {"tokenId": TOKEN_ID, "Content-Type": "application/json"}
        payload = {"wifiSn": WIFI_SN}
        response = requests.post(API_URL, headers=headers, json=payload)
        print("SolaX API-Status:", response.status_code)
        data = response.json().get("result", {})
        pv1 = data.get("powerdc1", 0)
        pv2 = data.get("powerdc2", 0)

        # 3. Open-Meteo
        url = f"https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}&current=shortwave_radiation_instant,direct_radiation_instant,diffuse_radiation_instant,cloud_cover,temperature_2m,wind_speed_10m,relative_humidity_2m,visibility&timezone=Europe%2FBerlin"
        meteo_data = requests.get(url, timeout=10).json()["current"]

        # 4. SunCalc
        pos = get_position(NOW, LAT, LON)

        # 5. DataFrame erstellen
        df = pd.DataFrame({
            "time": [NOW],
            "pv1": [round(pv1)],
            "pv2": [round(pv2)],
            "altitude": [round(pos["altitude"], 2)],
            "azimuth": [round(pos["azimuth"], 2)],
            "shortwave_radiation": [round(meteo_data["shortwave_radiation_instant"])],
            "direct_radiation": [round(meteo_data["direct_radiation_instant"])],
            "diffuse_radiation": [round(meteo_data["diffuse_radiation_instant"])],
            "cloudcover": [meteo_data["cloud_cover"]],
            "temperatur": [round(meteo_data["temperature_2m"])],
            "windspeed": [round(meteo_data["wind_speed_10m"])],
            "humidity": [round(meteo_data["relative_humidity_2m"])],
            "visibility": [round(meteo_data["visibility"] / 10)],
        })
        int_cols = [
            "pv1",
            "pv2",
            "shortwave_radiation",
            "cloudcover",
            "direct_radiation",
            "diffuse_radiation",
            "temperatur",
            "windspeed",
            "humidity",
            "visibility",
        ]
        df[int_cols] = df[int_cols].astype("Int64")
        df["time"] = df["time"].dt.tz_localize(None).dt.floor("min")

        # Pfad-Logik
        year = NOW.year
        month = NOW.month
        folder = f"data/{year}"
        filename = f"{year}{month:02d}.csv.enc"
        filepath_repo = f"{folder}/{filename}"

        # ------------------------------------------------------------
        # GITHUB SYNCHRONISATION (Datei laden, mergen, hochladen)
        # ------------------------------------------------------------
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(
            "cashewbite/solax-dashboard"
        )

        df_all = df
        file_sha = None

        try:
            # Versuche bestehende Datei aus GitHub zu laden
            file_content = repo.get_contents(filepath_repo)
            file_sha = file_content.sha
            decrypted = cipher.decrypt(file_content.decoded_content)
            df_old = pd.read_csv(io.BytesIO(decrypted))
            df_old[int_cols] = df_old[int_cols].astype("Int64")
            df_all = pd.concat([df_old, df], ignore_index=True)
        except Exception:
            # Datei existiert noch nicht -> wird neu erstellt
            pass

        # Neuer DataFrame verschlüsseln
        buffer = io.BytesIO()
        df_all.to_csv(buffer, index=False)
        encrypted_data = cipher.encrypt(buffer.getvalue())

        # Commit zu GitHub senden
        commit_message = f"Update data via Streamlit {NOW}"
        if file_sha:
          repo.update_file(
              filepath_repo,
              commit_message,
              encrypted_data,
              file_sha,
              branch="main",
          )
        else:
          repo.create_file(
              filepath_repo, commit_message, encrypted_data, branch="main"
          )

        print("Erfolgreich ausgeführt und Änderungen auf GitHub gepusht!")
        return True

    except Exception as e:
      return

if __name__ == '__main__':
    log_pv_data()