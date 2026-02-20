import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
import pytz
from streamlit_folium import st_folium
import folium


st.set_page_config(layout="wide", page_title="Interactive Weather (12h)")


def weathercode_to_text(code: int) -> str:
    mapping = {
        0: "Clear",
        1: "Mainly clear",
        2: "Partly cloudy",
        3: "Overcast",
        45: "Fog",
        48: "Depositing rime fog",
        51: "Drizzle: Light",
        53: "Drizzle: Moderate",
        55: "Drizzle: Dense",
        61: "Rain: Slight",
        63: "Rain: Moderate",
        65: "Rain: Heavy",
        71: "Snow: Slight",
        73: "Snow: Moderate",
        75: "Snow: Heavy",
        80: "Rain showers: Slight",
        81: "Rain showers: Moderate",
        82: "Rain showers: Violent",
    }
    return mapping.get(code, "Unknown")


@st.cache_data(ttl=600)
def get_weather(lat: float, lon: float, refresh_count: int = 0):
    # Query Open-Meteo for hourly data and current weather
    url = (
        "https://api.open-meteo.com/v1/forecast?"
        f"latitude={lat}&longitude={lon}"
        "&hourly=temperature_2m,precipitation_probability,relativehumidity_2m,windspeed_10m,weathercode"
        "&current_weather=true"
        "&timezone=Asia%2FSeoul"
    )
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    data = r.json()

    hourly = data.get("hourly", {})
    times = pd.to_datetime(hourly.get("time", []))
    # Localize times to KST
    if not times.tzinfo:
        times = times.tz_localize(pytz.timezone("Asia/Seoul"))

    df = pd.DataFrame(
        {
            "time": times,
            "temperature": hourly.get("temperature_2m", []),
            "precip_prob": hourly.get("precipitation_probability", []),
            "humidity": hourly.get("relativehumidity_2m", []),
            "windspeed": hourly.get("windspeed_10m", []),
            "weathercode": hourly.get("weathercode", []),
        }
    )

    now_kst = datetime.now(pytz.timezone("Asia/Seoul"))
    df_next = df[df["time"] >= now_kst].head(12)
    # If API times don't include the current hour, fallback to first 12 entries
    if df_next.empty:
        df_next = df.head(12)

    current = data.get("current_weather", {})

    return {"df": df_next.reset_index(drop=True), "current": current}


def to_fahrenheit(c):
    return c * 9 / 5 + 32


def main():
    st.title("Interactive 12-Hour Weather Viewer")
    st.write("Click on the map to choose a location (defaults to Seoul).")

    # Sidebar controls
    with st.sidebar:
        st.header("Settings")
        unit = st.radio("Temperature unit", ("Celsius", "Fahrenheit"))
        refresh = st.button("Refresh Data")
        st.write("Data source: Open-Meteo (no API key required)")

    if "coords" not in st.session_state:
        st.session_state.coords = {"lat": 37.5665, "lon": 126.9780}  # Seoul default
    if "refresh_count" not in st.session_state:
        st.session_state.refresh_count = 0

    if refresh:
        st.session_state.refresh_count += 1

    # Map area
    col1, col2 = st.columns([2, 3])
    with col1:
        m = folium.Map(location=[st.session_state.coords["lat"], st.session_state.coords["lon"]], zoom_start=10)
        folium.TileLayer("OpenStreetMap").add_to(m)
        folium.LatLngPopup().add_to(m)
        # Display map and capture clicks
        map_data = st_folium(m, height=500)
        last = map_data.get("last_clicked") if map_data else None
        if last:
            st.session_state.coords = {"lat": last["lat"], "lon": last["lng"]}

    # Fetch weather (cached)
    coords = st.session_state.coords
    try:
        payload = get_weather(coords["lat"], coords["lon"], st.session_state.refresh_count)
    except Exception as e:
        st.error(f"Failed to fetch weather: {e}")
        return

    df = payload["df"]
    current = payload.get("current", {})

    # Convert temps if needed
    display_temp = df["temperature"].copy()
    current_temp = current.get("temperature")
    if unit == "Fahrenheit":
        display_temp = display_temp.apply(to_fahrenheit)
        if current_temp is not None:
            current_temp = to_fahrenheit(current_temp)

    # Top metrics
    with col2:
        st.subheader("Current Summary")
        cols = st.columns(3)
        weather_code = df.loc[0, "weathercode"] if not df.empty else None
        weather_text = weathercode_to_text(int(weather_code)) if weather_code is not None else "N/A"
        cols[0].metric("Temperature", f"{current_temp:.1f}° {'F' if unit=='Fahrenheit' else 'C'}" if current_temp is not None else "N/A")
        cols[1].metric("Condition", weather_text)
        cols[2].metric("Precip Prob (next hour)", f"{df.loc[0,'precip_prob']}%" if not df.empty else "N/A")
    
    # Graph area
    st.markdown("---")
    st.subheader("Next 12 Hours — Temperature and Precipitation Probability")
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=df["time"],
            y=display_temp,
            name="Temperature",
            mode="lines+markers",
            yaxis="y1",
        )
    )
    fig.add_trace(
        go.Bar(
            x=df["time"],
            y=df["precip_prob"],
            name="Precipitation %",
            yaxis="y2",
            opacity=0.6,
        )
    )
    fig.update_layout(
        xaxis=dict(type="category", title="Time (KST)"),
        yaxis=dict(title=f"Temperature (°{'F' if unit=='Fahrenheit' else 'C'})"),
        yaxis2=dict(title="Precipitation Probability (%)", overlaying="y", side="right", range=[0, 100]),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(t=30, b=20),
    )
    st.plotly_chart(fig, use_container_width=True)

    # Detailed table
    st.subheader("Hourly Details")
    display_df = df.copy()
    display_df["time"] = display_df["time"].dt.strftime("%Y-%m-%d %H:%M")
    if unit == "Fahrenheit":
        display_df["temperature"] = display_df["temperature"].apply(lambda c: f"{to_fahrenheit(c):.1f}")
    else:
        display_df["temperature"] = display_df["temperature"].apply(lambda c: f"{c:.1f}")
    display_df["precip_prob"] = display_df["precip_prob"].apply(lambda p: f"{p}%")
    st.dataframe(display_df.rename(columns={"temperature": "temp", "precip_prob": "precip%"}))


if __name__ == "__main__":
    main()
