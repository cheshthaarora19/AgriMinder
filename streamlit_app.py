import os
import streamlit as st
import pandas as pd
import sqlite3
import requests
from datetime import datetime, timedelta
from pathlib import Path

# DB file next to this script (robust)
DB_PATH = Path(__file__).parent / "agriminder.db"

# -----------------------
# Database helpers
# -----------------------
def init_db():
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()

    # --- Reminders table ---
    cur.execute("""
    CREATE TABLE IF NOT EXISTS reminders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        desc TEXT,
        remind_at TEXT NOT NULL
    )
    """)

    # --- Schemes table ---
    cur.execute("""
    CREATE TABLE IF NOT EXISTS schemes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        eligible INTEGER DEFAULT 0
    )
    """)

    # ✅ Insert schemes only if table is empty
    cur.execute("SELECT COUNT(*) FROM schemes")
    if cur.fetchone()[0] == 0:
        cur.executemany("INSERT INTO schemes (name, eligible) VALUES (?,?)", [
            ("Pradhan Mantri Fasal Bima Yojana (PMFBY)", 0),
            ("Kisan Credit Card (KCC) Scheme", 0),
            ("PM-KISAN Samman Nidhi Yojana", 0),
            ("Soil Health Card Scheme", 0),
            ("PM-KUSUM Yojana", 0),
            ("Rashtriya Krishi Vikas Yojana (RKVY)", 0),
            ("e-NAM (National Agriculture Market)", 0),
            ("National Mission on Sustainable Agriculture (NMSA)", 0)
        ])

    

    # --- Settings table ---
    cur.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        land_size REAL,
        crops TEXT,
        city TEXT,
        language TEXT
    )
    """)

    # ✅ Seed default settings only if table is empty
    cur.execute("SELECT COUNT(*) FROM settings")
    if cur.fetchone()[0] == 0:
        cur.execute("""
        INSERT INTO settings (name, land_size, crops, city, language)
        VALUES (?, ?, ?, ?, ?)
        """, ("John Doe", 2.0, "Wheat, Rice", "Delhi", "English"))

    conn.commit()
    conn.close()


def add_reminder(title, desc, remind_at):
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO reminders (title, desc, remind_at) VALUES (?,?,?)",
        (title, desc, remind_at)
    )
    conn.commit()
    conn.close()


def get_reminders():
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute("SELECT id, title, desc, remind_at FROM reminders ORDER BY remind_at")
    rows = cur.fetchall()
    conn.close()
    df = pd.DataFrame(rows, columns=["id", "title", "desc", "remind_at"])
    if not df.empty:
        df["remind_at"] = pd.to_datetime(df["remind_at"])
    return df


def get_schemes():
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute("SELECT id, name, eligible FROM schemes")
    rows = cur.fetchall()
    conn.close()
    return rows


def set_scheme_eligibility(scheme_id, eligible):
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute(
        "UPDATE schemes SET eligible=? WHERE id=?",
        (1 if eligible else 0, scheme_id)
    )
    conn.commit()
    conn.close()

def get_sample_market_prices(crop=None, state=None):
    # Hardcoded sample data (no DB needed)
    sample_data = [
        {"Crop": "Wheat", "State": "Delhi",  "Date": "2025-09-21", "Price": 2150},
        {"Crop": "Wheat", "State": "Punjab", "Date": "2025-09-21", "Price": 2200},
        {"Crop": "Wheat", "State": "Delhi",  "Date": "2025-09-20", "Price": 2100},
        {"Crop": "Rice",  "State": "Kerala", "Date": "2025-09-21", "Price": 2800},
        {"Crop": "Rice",  "State": "Bihar",  "Date": "2025-09-22", "Price": 2750},
        {"Crop": "Rice",  "State": "Delhi",  "Date": "2025-09-22", "Price": 2900},
        {"Crop": "Paddy", "State": "Haryana","Date": "2025-09-21", "Price": 2000},
        {"Crop": "Maize", "State": "UP",     "Date": "2025-09-21", "Price": 1800},
        {"Crop": "Sugarcane","State":"Maharashtra","Date":"2025-09-21","Price":3100},
    ]
    df = pd.DataFrame(sample_data)

    # Filter by crop and state
    if crop:
        df = df[df["Crop"].str.lower() == crop.lower()]
    if state:
        df = df[df["State"].str.lower() == state.lower()]

    return df



def get_settings():
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute("SELECT id, name, land_size, crops, city, language FROM settings LIMIT 1")
    row = cur.fetchone()
    conn.close()
    if row:
        return {
            "id": row[0],
            "name": row[1],
            "land_size": row[2],
            "crops": row[3],
            "city": row[4],
            "language": row[5]
        }
    return None


def update_settings(name, land_size, crops, city, language):
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute("""
        UPDATE settings
        SET name=?, land_size=?, crops=?, city=?, language=?
        WHERE id=1
    """, (name, land_size, crops, city, language))
    conn.commit()
    conn.close()



# -----------------------
# Weather API helper
# -----------------------
@st.cache_data(ttl=600)
def get_weather_forecast(city: str, api_key: str):
    """Return a dict: {'data': [ ... ]} on success, or {'error': code, 'message': ...} on failure."""
    city = (city or "").strip()
    if not api_key:
        return {"error": "missing_api_key", "message": "No OpenWeather API key configured."}
    if not city:
        return {"error": "missing_city", "message": "No city provided."}
    try:
        url = "https://api.openweathermap.org/data/2.5/forecast"
        params = {"q": city, "appid": api_key, "units": "metric"}
        res = requests.get(url, params=params, timeout=10)
        if res.status_code == 200:
            data = res.json()
            forecasts = []
            used_dates = set()
            for entry in data.get("list", []):
                dt_txt = entry.get("dt_txt")
                if not dt_txt:
                    continue
                if dt_txt.endswith("12:00:00"):
                    day = dt_txt.split(" ")[0]
                    if day not in used_dates:
                        forecasts.append({
                            "date": day,
                            "temp": entry["main"]["temp"],
                            "weather": entry["weather"][0]["description"],
                            "humidity": entry["main"]["humidity"],
                            "wind": entry["wind"]["speed"]
                        })
                        used_dates.add(day)
                    if len(forecasts) >= 5:
                        break
            if not forecasts:  # fallback
                fallback = data.get("list", [])[::8][:5]
                for entry in fallback:
                    dt = entry.get("dt_txt", "")
                    forecasts.append({
                        "date": dt.split(" ")[0] if dt else "",
                        "temp": entry["main"]["temp"],
                        "weather": entry["weather"][0]["description"],
                        "humidity": entry["main"]["humidity"],
                        "wind": entry["wind"]["speed"]
                    })
            return {"data": forecasts}
        else:
            if res.status_code == 401:
                return {"error": "unauthorized", "message": "Invalid API key (401)."}
            if res.status_code == 404:
                return {"error": "city_not_found", "message": "City not found (404). Try 'Delhi,IN'."}
            if res.status_code == 429:
                return {"error": "rate_limited", "message": "Rate limit reached (429)."}
            return {"error": f"http_{res.status_code}", "message": res.text}
    except requests.exceptions.RequestException as e:
        return {"error": "request_exception", "message": str(e)}

# -----------------------
# App UI & layout
# -----------------------
st.set_page_config(page_title="AgriMinder", layout="wide", page_icon="🌿")
init_db()

# CSS
st.markdown(
    """
    <style>
    .big-title {
        font-size: 42px;
        font-weight: 700;
        color: white;
    }
    .card {
    background: #ffffff;
    padding: 20px;
    border-radius: 16px;
    border: 1px solid #e6e6e6;
    box-shadow: 0 4px 8px rgba(0,0,0,0.05);
    min-height: 260px;   /* ✅ all cards same height */
    display: flex;
    flex-direction: column;
    justify-content: flex-start;
    }
    .weather-line {
        font-size: 14px;
        margin-bottom: 6px;
    }
    .stButton > button {
        background-color: #4CAF50;
        color: white;
        border-radius: 10px;
        padding: 8px 16px;
        cursor: pointer;
        font-weight: 500;
    }
    .stButton > button:hover {
        background-color: #45a049;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# Sidebar
with st.sidebar:
    
    st.markdown("##🌿AgriMinder")
    st.markdown("---")
    page = st.radio("", ["Dashboard","Reminders","Govt. Schemes","Market Watch","Settings"], index=0)
    st.markdown("---")

    # ✅ Load settings from DB
    user_settings = get_settings()
    if user_settings:
        st.markdown(f"**{user_settings['name']}**  \nFarmer")
    else:
        st.markdown("**Farmer**")

    st.markdown("---")



# ---------- Dashboard ----------
if page == "Dashboard":
        # Load farmer name from settings
    user_settings = get_settings()
    farmer_name = user_settings['name'] if user_settings else "Farmer"

    st.markdown(f'<div class="big-title">Welcome back, {farmer_name}!</div>', unsafe_allow_html=True)


    # Create 4 equal columns
    col1, col2, col3, col4 = st.columns(4)

    # --- Upcoming Reminders ---
    with col1:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown("### 🗓️ Upcoming Reminders")
        df = get_reminders()
        if df.empty:
            st.write("No scheduled tasks. Add a reminder in Reminders page.")
        else:
            upcoming = df[df["remind_at"] >= pd.Timestamp.now()].head(2)
            for _, row in upcoming.iterrows():
                st.markdown(f"**{row.title}**  \n{row.desc}  \n{row.remind_at.strftime('%b %d, %Y %I:%M %p')}")
                st.write("")
        st.markdown("</div>", unsafe_allow_html=True)

    # --- Scheme Alerts ---
    with col2:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown("### 🏛️ Scheme Alerts")

        schemes = get_schemes()  # list of tuples (id, name, eligible)

        # DEBUG: uncomment the next line if you want to see exactly what's in the DB
        # st.write("DEBUG - all schemes:", schemes)

        # Find scheme ids for PMFBY and KCC using robust substring matching (case-insensitive)
        important_keys = ["fasal bima", "pmfby", "kisan credit", "kcc"]
        important = []
        for s in schemes:
            name_lower = s[1].lower()
            if any(k in name_lower for k in important_keys):
                important.append(s)

        # Fallback: if we didn't find both, just pick the top 2 schemes from the DB
        if not important:
            important = schemes[:2]

        # Display only the important schemes
        for s in important:
            dot = "🟢" if s[2] else "🟠"
            st.markdown(f"{dot} **{s[1]}**")

        st.write("")  # spacing
        if st.button("Check Eligibility"):
            st.info("Go to Govt. Schemes page to update eligibility.")
        st.markdown("</div>", unsafe_allow_html=True)


    # --- Quick Actions ---
     with col3:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown("### ⚡ Quick Actions")
        if st.button("Add sample reminder"):
            add_reminder(
                "Irrigate Wheat Field",
                "Irrigate the main wheat field",
                (pd.Timestamp.now()+pd.Timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
            )
            st.success("Sample reminder added.")
        st.markdown("</div>", unsafe_allow_html=True)

    # --- Weather Forecast ---
    with col4:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown("### 🌦️ Weather Forecast")

        api_key = st.secrets.get("OPENWEATHER_API_KEY") if hasattr(st, "secrets") else None
        if not api_key:
            api_key = os.environ.get("OPENWEATHER_API_KEY", None)

        default_city = st.session_state.get("sidebar_default_city", "Delhi")
        city = st.text_input("City", value=st.session_state.get("sidebar_weather_city", "Delhi"), key="dashboard_weather_city")

        weather_res = get_weather_forecast(city=city, api_key=api_key)

        if weather_res.get("error"):
            st.error(weather_res.get("message", "Error fetching weather"))
        else:
            data = weather_res.get("data", [])
            if not data:
                st.info("No forecast data available.")
            else:
                for f in data[:2]:  # ✅ only today + tomorrow
                    st.markdown(
                        f"""
                        <div class='weather-line'>
                        📅 <b>{f['date']}</b><br>
                        🌡 {f['temp']}°C &nbsp; | &nbsp; 💧 {f['humidity']}% &nbsp; | &nbsp; 💨 {f['wind']} m/s<br>
                        <i>{f['weather'].capitalize()}</i>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )
        st.markdown("</div>", unsafe_allow_html=True)

# ---------- Reminders ----------
elif page == "Reminders":
    st.header("Reminders")
    with st.form("add_reminder"):
        title = st.text_input("Title")
        desc = st.text_area("Description")
        date = st.date_input("Remind Date", value=(datetime.now()+timedelta(days=1)).date())
        time = st.time_input("Remind Time", value=(datetime.now()+timedelta(days=1)).time())
        remind_at = datetime.combine(date, time)
        submitted = st.form_submit_button("Add Reminder")
        if submitted:
            if not title:
                st.error("Title required.")
            else:
                add_reminder(title, desc, remind_at.strftime("%Y-%m-%d %H:%M:%S"))
                st.success("Reminder added.")

    st.markdown("---")
    df = get_reminders()
    if df.empty:
        st.info("No reminders yet.")
    else:
        for _, row in df.iterrows():
            with st.expander(f"{row.title} — {row.remind_at.strftime('%Y-%m-%d %H:%M')}"):
                st.write(row.desc)
                if st.button(f"Delete-{row.id}", key=f"del-{row.id}"):
                    conn = sqlite3.connect(str(DB_PATH))
                    cur = conn.cursor()
                    cur.execute("DELETE FROM reminders WHERE id=?", (row.id,))
                    conn.commit()
                    conn.close()
                    st.rerun()

# ---------- Govt. Schemes ----------
elif page == "Govt. Schemes":
    st.header("Government Schemes")
    schemes = get_schemes()

    if st.session_state.get("eligibility_updated", False):
        st.success("✅ Eligibility updated in database.")
        st.session_state["eligibility_updated"] = False

    for s in schemes:
        scheme_id = s[0]
        scheme_name = s[1]
        scheme_eligible = bool(s[2])

        with st.expander(f"📌 {scheme_name}"):

            # 🎯 Different criteria per scheme
            if "Fasal Bima" in scheme_name:
                criteria = [
                    {"text": "Owns agricultural land", "default": True},
                    {"text": "Crop insured under PMFBY", "default": False},
                    {"text": "Annual income below ₹2,50,000", "default": False},
                ]
            elif "Kisan Credit Card" in scheme_name:
                criteria = [
                    {"text": "Owns agricultural land", "default": True},
                    {"text": "Annual income below ₹3,00,000", "default": False},
                    {"text": "Has valid Aadhaar card", "default": True},
                ]
            else:
                # fallback for any new schemes
                criteria = [
                    {"text": "Owns agricultural land", "default": True},
                    {"text": "Annual income below threshold", "default": False},
                ]

            st.write("Toggle the criteria below to simulate eligibility:")

            # --- Show checkboxes ---
            met_count = 0
            for i, c in enumerate(criteria):
                cb_key = f"scheme_{scheme_id}_crit_{i}"
                checked = st.checkbox(c["text"], value=c["default"], key=cb_key)
                if checked:
                    met_count += 1

            # --- Progress bar ---
            progress = met_count / len(criteria)
            st.progress(progress)
            st.caption(f"✅ {met_count}/{len(criteria)} criteria met")

            # --- DB eligibility status ---
            st.write("**Current stored eligibility:**", "✅ Eligible" if scheme_eligible else "❌ Not eligible")

            if st.button("Save Eligibility", key=f"save_scheme_{scheme_id}"):
                new_eligible = (met_count == len(criteria))
                set_scheme_eligibility(scheme_id, new_eligible)
                st.session_state["eligibility_updated"] = True
                st.rerun()


# --- Market Watch ---
elif page == "Market Watch":
    st.markdown("## 📈 Market Watch")

    crop = st.selectbox("Select Crop", ["Wheat", "Rice", "Paddy", "Maize", "Sugarcane"])
    state = st.text_input("State (optional)")

    # ✅ Local Sample Data
    sample_data = [
        {"Crop": "Wheat", "State": "Delhi",  "Date": "2025-09-21", "Price": 2150},
        {"Crop": "Wheat", "State": "Punjab", "Date": "2025-09-21", "Price": 2200},
        {"Crop": "Wheat", "State": "Delhi",  "Date": "2025-09-20", "Price": 2100},
        {"Crop": "Rice",  "State": "Kerala", "Date": "2025-09-21", "Price": 2800},
        {"Crop": "Rice",  "State": "Bihar",  "Date": "2025-09-22", "Price": 2750},
        {"Crop": "Rice",  "State": "Delhi",  "Date": "2025-09-22", "Price": 2900},
        {"Crop": "Paddy", "State": "Haryana","Date": "2025-09-21", "Price": 2000},
        {"Crop": "Maize", "State": "UP",     "Date": "2025-09-21", "Price": 1800},
        {"Crop": "Sugarcane","State":"Maharashtra","Date":"2025-09-21","Price":3100},
    ]

    df = pd.DataFrame(sample_data)

    # ✅ Filter by crop and state
    df_filtered = df[df["Crop"].str.lower() == crop.lower()]
    if state:
        df_filtered = df_filtered[df_filtered["State"].str.lower() == state.lower()]

    if df_filtered.empty:
        st.info("No price data available for your selection.")
    else:
        st.subheader(f"Latest Prices for {crop}")
        st.dataframe(df_filtered)
        st.bar_chart(df_filtered.set_index("State")["Price"])


# ---------- Settings ----------
else:
    st.header("⚙️ Settings")

    settings = get_settings()

    with st.form("settings_form"):
        name = st.text_input("Farmer Name", value=settings["name"])
        land_size = st.number_input("Land Size (in acres)", value=settings["land_size"], min_value=0.0)
        crops = st.text_area("Main Crops (comma separated)", value=settings["crops"])
        city = st.text_input("Default City for Weather", value=settings["city"])
        language = st.selectbox("Preferred Language", ["English", "Hindi"], index=0 if settings["language"]=="English" else 1)

        submitted = st.form_submit_button("Save Settings")
        if submitted:
            update_settings(name, land_size, crops, city, language)
            st.success("✅ Settings updated successfully!")
