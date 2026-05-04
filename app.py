import requests
import streamlit as st

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
        return data.get("result", {})
    except Exception as e:
        st.error(f"API Fehler: {e}")
        return {}

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

with st.spinner("Lade Live-Daten..."):
    data = get_solax_data()

if not data:
    st.error("Keine Daten erhalten")
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

st.markdown(f"""
<div style="display: flex; align-items: left; justify-content: center; width: fit-content; gap: 1rem; ">
    <div style="flex: 0 0 auto; text-align: left;">
        <h5>🏠 Berechneter Verbrauch</h5>
        <p style="font-size: 35px; ">{house_load} W</p>
    </div>
</div>
""", unsafe_allow_html=True)
