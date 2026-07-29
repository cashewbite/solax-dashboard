import requests
import streamlit as st
import pandas as pd
import altair as alt
from today_predict import predict_day
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

status = 200

API_URL = st.secrets["API_URL"]
TOKEN_ID = st.secrets["TOKEN_ID"]
WIFI_SN = st.secrets["WIFI_SN"]

headers = {
    "tokenId": TOKEN_ID,
    "Content-Type": "application/json"
}

payload = {
    "wifiSn": WIFI_SN
}
# -----------------------------
# API REQUEST
# -----------------------------
def get_solax_data():
    try:
        response = requests.post(API_URL, headers=headers, json=payload)
        # print("Status:", response.status_code)
        data = response.json()
        # print(data)
        return data.get("result", {}), response.status_code
    except Exception as e:
        st.error(f"API Fehler: {e}")
        return {},e

# -----------------------------
# STREAMLIT UI
# -----------------------------

st.set_page_config(
    page_title="SolaX",
    page_icon="⚡",
)

st.markdown("""
<style>
    /* Abstand oben und unten reduzieren */
.block-container {
    padding-top: 1rem;
    padding-bottom: 1rem;
}
</style>
""", unsafe_allow_html=True)
st.title("SolaX Live")

if "solax_data" not in st.session_state:
    with st.spinner("Lade Live-Daten..."):
        data, status = get_solax_data()
        st.session_state.solax_data = data
        st.session_state.solax_status = status
else:
    data = st.session_state.solax_data
    status = st.session_state.solax_status

if not data:
    st.error(f"Keine Daten erhalten (Status: {status})")
    st.stop()

# Werte auslesen
soc = data.get("soc", 0)            # Akkustand
feedin = data.get("feedinpower", 0) # import (<0) /export (>0)
batPower = data.get("batPower", 0)  # 0: batterie wird nicht geladen, batterie wird entladen in W (<0)/ beladen (>0)
upload_time = data.get("uploadTime", "")
pv1 = data.get("powerdc1",0)
pv2 = data.get("powerdc2",0)

# PV-Leistung berechnen
pv_total = pv1 + pv2

# Hausverbrauch berechnen
house_load = pv_total - batPower - feedin

soc = round(soc)
house_load = round(house_load)
pv_total = round(pv_total)
feedin = round(feedin)
batPower = round(batPower)

# update
if upload_time:
    uhrzeit = upload_time.split(" ")[1]
    st.write(f"🕒 **{uhrzeit}**")
else:
    st.warning("Keine uploadTime erhalten")

if batPower < 0:
    trend = f"▼ {abs(batPower)} W"
    word = "🔌Entladung"
    color = "red"
elif batPower > 0:
    trend = f"▲ {batPower} W"
    word = "⚡Aufladung"
    color = "green"
else:
    trend = ""
    word = "Kein Auf-/Entladen"
    color = "gray"

if soc >= 40:
    display = f"🔋{soc} %"
else:
    display = f"🪫{soc} %"

st.markdown(f"""
<div style="display:flex; align-items:center; gap:1rem; margin-bottom: 16px; ">
    <div style="font-size:35px; font-weight:bold;">{display}</div>
    <div style="font-size:18px; font-weight:bold; color:{color};">{trend}</div>
    <div style="font-size:18px; color:{color};">{word}</div>
</div>
""", unsafe_allow_html=True)

# Export / Import
if feedin >= 30:
    feedin_title, color, arrow = "🌞 Einspeisung", "green", "▲"
elif feedin <= -30:
    feedin_title, color, arrow = "⚠️ Netzbezug", "red", "▼"
else:
    color = "grey"
    feedin_title = "Einspeisung" if feedin > 0 else "Netzbezug"
    arrow = "▲" if feedin > 0 else ("▼" if feedin < 0 else "")

trend = f"{arrow} {abs(feedin)} W" if arrow else f"{feedin} W"

st.markdown(f"""
<div style="display: flex; align-items: left; justify-content: center; width: fit-content; gap: 1rem; ">
    <div style="flex: 0 0 auto; text-align: left;">
        <h5>⚡Solar</h5>
        <p style="font-size: 35px; ">{pv_total} W</p>
    </div>
    <div style="flex: 0 0 auto; text-align: left;">
        <h5 style="color:{"grey" if color == "grey" else "inherit"};" >{feedin_title}</h5>
        <div style="display:flex; align-items:center; gap:1rem; margin-bottom: 16px; ">
            <div style="font-size:35px; color:{color};">{trend}</div>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

color = "grey" if house_load < 0 else "inherit"

st.markdown(f"""
<div style="display: flex; align-items: left; justify-content: center; width: fit-content; gap: 1rem; ">
    <div style="flex: 0 0 auto; text-align: left;">
        <h5 style="color:{color};">{"" if color == "grey" else "🏠 "}Berechneter Verbrauch</h5>
        <p style="font-size: 35px; color:{color}; ">{house_load} W</p>
    </div>
</div>
""", unsafe_allow_html=True)

NOW = datetime.now(ZoneInfo("Europe/Berlin"))
heute = NOW.replace(hour=0, minute=0, second=0, microsecond=0)

def get_data_chart(forecast_day, pv_total):
    df = predict_day(forecast_day)

    if df is None:
        return None
    if df.empty:
        return None

    df["pv_sum"] = df["pv1"] + df["pv2"]

    tmin = df["time"].min()
    tmax = df["time"].max()

    now = NOW.replace(second=0, microsecond=0) + timedelta(days=forecast_day-1)
    now = now.replace(tzinfo=None)
    
    if pd.isna(tmin) or pd.isna(tmax):
        return alt.Chart(df).mark_area().encode(
            x="time:T",
            y="pv_sum:Q"
        )

    # 2. pv_total prüfen
    if pv_total is None:
        pv_total = 0

    # # 3. now prüfen
    if not (tmin <= now <= tmax):
        draw_now = False
    else:
        draw_now = True    

    pv_sum = (
        alt.Chart(df) # "#D48D09"
        .mark_area(color="#BD7D08", interpolate="monotone") #mark_line mark_bar mark_area mark_trail
        .encode( #"#fd0"
            x=alt.X("time:T", axis=alt.Axis(format="%H:%M"), title=None),
            y=alt.Y("pv_sum:Q", title=None),
            tooltip=[alt.Tooltip("time:T", title="time", format="%H:%M"),
                     "pv1", "pv2", "pv_sum"]
        )
        .properties(height=270)
    )
    pv1 = (
        alt.Chart(df)
        .mark_area(color="orange", interpolate="monotone")
        .encode(
            x=alt.X("time:T", axis=alt.Axis(format="%H:%M"), title=None),
            y=alt.Y("pv1:Q", title=None),
            tooltip=[alt.Tooltip("time:T", title="time", format="%H:%M"),
                "pv1", "pv2", "pv_sum"]
        )
        .properties(height=270)
    )
    rule_8k = (
        alt.Chart(pd.DataFrame({"pv_sum": [8000]}))
        .mark_rule(color="red", strokeWidth=2)
        .encode(y="pv_sum:Q")
    )
    label_8k = (
        alt.Chart(pd.DataFrame({"pv_sum": [8000], "x": [tmin]}))
        .mark_text(
            text="🚗 8 k",
            align="left", baseline="bottom",
            dx=5, dy=-5,
            color="red", fontSize=16
        )
        .encode(x="x:T", y="pv_sum:Q")
    )
    if draw_now:
        rule_now = (
            alt.Chart(pd.DataFrame({"time": [now]}))
            .mark_rule(color="green", strokeWidth=2)
            .encode(x="time:T")
        )
        now_point = (
            alt.Chart(pd.DataFrame({"time": [now],"pv_sum": pv_total}))
            .mark_point(filled=True, color="green", shape="diamond",size=200,strokeWidth=2,fillOpacity=1) #arc point
            .encode(x="time:T", y="pv_sum:Q")
        )
        label_now = (
            alt.Chart(pd.DataFrame({"time": [now],"pv_sum": pv_total}))
            .mark_text(
                text=f"{pv_total} W",
                align="left", 
                dx=13, 
                color="green", fontSize=16
            )
            .encode(x="time:T", y="pv_sum:Q")
        )
    else:
        rule_now = now_point = label_now = alt.Chart(pd.DataFrame({"time": []})).mark_point()    

    chart = ( pv_sum + pv1 
             + 
             rule_8k + 
             label_8k + 
             rule_now + now_point + label_now
             ).properties(
        width="container")

    return chart


weekdays = {
    0: "Montag",
    1: "Dienstag",
    2: "Mittwoch",
    3: "Donnerstag",
    4: "Freitag",
    5: "Samstag",
    6: "Sonntag"
}

def day_name(timedelta_days):
    day = heute + timedelta(days=timedelta_days)
    return weekdays[day.weekday()]

options = {
    "Heute": 1,
    "Morgen": 2,
    day_name(2): 3,
    day_name(3): 4
}

if "forecast_day" not in st.session_state:
    st.session_state.forecast_day = 1

def mode_changed():
    # Wert kommt aus segmented_control
    if st.session_state["mode"] is not None:
        st.session_state.forecast_day = options[st.session_state["mode"]]

st.segmented_control(
    label="Vorhersage",
    options=options.keys(),
    default="Heute",
    key="mode",
    on_change=mode_changed
)

@st.cache_data(ttl=3600)  # Cache für 1 Stunde
def cached_chart(forecast_day, pv_total):
    return get_data_chart(forecast_day, pv_total)

with st.spinner("Vorhersage ..."):
    forecast_day = st.session_state.forecast_day
    chart = cached_chart(forecast_day, pv_total)

    if chart is None:
        st.error("Keine Daten")
    else:
        st.altair_chart(chart)
