from flask import Flask, render_template, request, redirect, url_for, session
import requests
from datetime import datetime, timedelta, timezone

app = Flask(__name__)
app.secret_key = "change-this-secret-key"

API_KEY = "056bc2805c791e9a8ac92d45aeb77836"
BASE_URL = "https://api.openweathermap.org/data/2.5/weather"
FORECAST_URL = "https://api.openweathermap.org/data/2.5/forecast"
AIR_QUALITY_URL = "https://api.openweathermap.org/data/2.5/air_pollution"
SEVEN_DAY_URL = "https://api.open-meteo.com/v1/forecast"


def format_time(timestamp, offset_seconds, fmt):
    tz = timezone(timedelta(seconds=offset_seconds))
    return datetime.fromtimestamp(timestamp, tz).strftime(fmt)


def aqi_meta(index):
    mapping = {
        1: ("Good", "Air quality is satisfactory for most people."),
        2: ("Fair", "Sensitive people may feel minor discomfort."),
        3: ("Moderate", "Sensitive groups should reduce prolonged exposure."),
        4: ("Poor", "Health effects possible for everyone with longer exposure."),
        5: ("Very Poor", "Serious health effects possible. Limit outdoor time.")
    }
    return mapping.get(index, ("Unknown", "AQI data unavailable."))


def build_tips(weather, air):
    tips = []

    if weather["temp"] >= 35:
        tips.append("High heat: avoid direct sun in afternoon.")
    elif weather["temp"] <= 8:
        tips.append("Cold weather: keep yourself warm outdoors.")

    if weather["humidity"] >= 75:
        tips.append("Humidity is high: stay hydrated.")

    if weather["wind"] >= 25:
        tips.append("Winds are strong: secure loose outdoor items.")

    if weather["visibility"] <= 3:
        tips.append("Low visibility: drive carefully.")

    if air and air["index"] >= 4:
        tips.append("Air quality is poor: mask is recommended outside.")

    if weather["clouds"] >= 70:
        tips.append("Cloud cover is dense: sunlight may stay limited.")

    if "rain" in weather["description"].lower() or "drizzle" in weather["description"].lower():
        tips.append("Rain likely: keep an umbrella with you.")

    tips.append(f"Cloud cover: {weather['clouds']}%")
    tips.append(f"Pressure: {weather['pressure']} hPa")

    # Keep UI balanced with exactly 6 cards.
    unique = []
    for tip in tips:
        if tip not in unique:
            unique.append(tip)
    return unique[:6]


def weather_code_label(code):
    mapping = {
        0: "Clear Sky",
        1: "Mostly Clear",
        2: "Partly Cloudy",
        3: "Cloudy",
        45: "Fog",
        48: "Depositing Rime Fog",
        51: "Light Drizzle",
        53: "Drizzle",
        55: "Dense Drizzle",
        61: "Slight Rain",
        63: "Rain",
        65: "Heavy Rain",
        71: "Slight Snow",
        73: "Snow",
        75: "Heavy Snow",
        80: "Rain Showers",
        81: "Rain Showers",
        82: "Heavy Showers",
        95: "Thunderstorm",
        96: "Thunderstorm Hail",
        99: "Thunderstorm Hail"
    }
    return mapping.get(code, "Weather Update")


def fetch_seven_day_forecast(lat, lon):
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": "weathercode,temperature_2m_max,temperature_2m_min,precipitation_probability_max,windspeed_10m_max",
        "timezone": "auto",
        "forecast_days": 7
    }

    try:
        response = requests.get(SEVEN_DAY_URL, params=params, timeout=10)
    except requests.RequestException:
        response = None

    if not response or response.status_code != 200:
        return []

    daily = response.json().get("daily", {})
    dates = daily.get("time", [])
    highs = daily.get("temperature_2m_max", [])
    lows = daily.get("temperature_2m_min", [])
    rain_chance = daily.get("precipitation_probability_max", [])
    wind_speeds = daily.get("windspeed_10m_max", daily.get("wind_speed_10m_max", []))
    weather_codes = daily.get("weathercode", daily.get("weather_code", []))

    seven_day = []
    for idx, day_str in enumerate(dates[:7]):
        try:
            parsed = datetime.strptime(day_str, "%Y-%m-%d")
        except ValueError:
            continue

        high = round(highs[idx]) if idx < len(highs) and highs[idx] is not None else "--"
        low = round(lows[idx]) if idx < len(lows) and lows[idx] is not None else "--"
        rain = round(rain_chance[idx]) if idx < len(rain_chance) and rain_chance[idx] is not None else 0
        wind = round(wind_speeds[idx]) if idx < len(wind_speeds) and wind_speeds[idx] is not None else 0
        code = weather_codes[idx] if idx < len(weather_codes) and weather_codes[idx] is not None else -1

        seven_day.append({
            "date": day_str,
            "day": parsed.strftime("%a"),
            "display": parsed.strftime("%d %b"),
            "weather": weather_code_label(code),
            "high": high,
            "low": low,
            "rain": rain,
            "wind": wind
        })

    return seven_day

@app.route("/", methods=["GET", "POST"])
def index():
    if "user" not in session:
        return redirect(url_for("login"))

    weather = None
    forecast = []
    air = None
    tips = []
    seven_day = []
    error = None

    if request.method == "POST":
        city = request.form.get("city")

        if city:
            params = {
                "q": city,
                "appid": API_KEY,
                "units": "metric"
            }

            try:
                response = requests.get(BASE_URL, params=params, timeout=10)
            except requests.RequestException:
                response = None

            if response and response.status_code == 200:
                data = response.json()
                timezone_offset = data.get("timezone", 0)
                lat = data.get("coord", {}).get("lat")
                lon = data.get("coord", {}).get("lon")
                weather = {
                    "city": data["name"],
                    "temp": data["main"]["temp"],
                    "temp_max": data["main"].get("temp_max", data["main"]["temp"]),
                    "temp_min": data["main"].get("temp_min", data["main"]["temp"]),
                    "feels_like": data["main"].get("feels_like", data["main"]["temp"]),
                    "humidity": data["main"]["humidity"],
                    "description": data["weather"][0]["description"].title(),
                    "icon": data["weather"][0]["icon"],
                    "wind": round(data.get("wind", {}).get("speed", 0) * 3.6, 1),
                    "visibility": round((data.get("visibility", 0) / 1000), 1),
                    "sunrise": format_time(data.get("sys", {}).get("sunrise", 0), timezone_offset, "%I:%M %p"),
                    "sunset": format_time(data.get("sys", {}).get("sunset", 0), timezone_offset, "%I:%M %p"),
                    "clouds": data.get("clouds", {}).get("all", 0),
                    "pressure": data["main"].get("pressure", 0)
                }

                if lat is not None and lon is not None:
                    forecast_params = {
                        "lat": lat,
                        "lon": lon,
                        "appid": API_KEY,
                        "units": "metric"
                    }
                    try:
                        forecast_response = requests.get(FORECAST_URL, params=forecast_params, timeout=10)
                    except requests.RequestException:
                        forecast_response = None
                    if forecast_response and forecast_response.status_code == 200:
                        forecast_data = forecast_response.json().get("list", [])
                        for slot in forecast_data[:6]:
                            forecast.append({
                                "time": format_time(slot["dt"], timezone_offset, "%I%p").lstrip("0"),
                                "temp": round(slot["main"]["temp"]),
                                "icon": slot["weather"][0]["icon"]
                            })

                    air_params = {
                        "lat": lat,
                        "lon": lon,
                        "appid": API_KEY
                    }
                    try:
                        air_response = requests.get(AIR_QUALITY_URL, params=air_params, timeout=10)
                    except requests.RequestException:
                        air_response = None
                    if air_response and air_response.status_code == 200:
                        air_data = air_response.json().get("list", [])
                        if air_data:
                            aqi = air_data[0]
                            index = aqi["main"]["aqi"]
                            status, note = aqi_meta(index)
                            components = aqi.get("components", {})
                            air = {
                                "index": index,
                                "status": status,
                                "note": note,
                                "marker": max(2, min(98, ((index - 1) / 4) * 100)),
                                "co": round(components.get("co", 0)),
                                "no2": round(components.get("no2", 0)),
                                "o3": round(components.get("o3", 0)),
                                "pm10": round(components.get("pm10", 0))
                            }

                    seven_day = fetch_seven_day_forecast(lat, lon)

                tips = build_tips(weather, air)
            else:
                error = "City not found or weather service unavailable. Try again!"

    return render_template(
        "index.html",
        weather=weather,
        forecast=forecast,
        air=air,
        tips=tips,
        seven_day=seven_day,
        error=error,
        user=session.get("user", "Guest")
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        if username and password:
            session["user"] = username.title()
            return redirect(url_for("index"))
        error = "Please enter both username and password."

    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/feedback", methods=["GET", "POST"])
def feedback():
    if "user" not in session:
        return redirect(url_for("login"))

    success = False
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        message = request.form.get("message", "").strip()
        if name and message:
            success = True

    return render_template(
        "support_form.html",
        page_title="Feedback",
        help_text="Share your experience to help us improve SkyPulse.",
        success=success,
        user=session.get("user", "Guest")
    )


@app.route("/contact-us", methods=["GET", "POST"])
def contact_us():
    if "user" not in session:
        return redirect(url_for("login"))

    success = False
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        message = request.form.get("message", "").strip()
        if name and message:
            success = True

    return render_template(
        "support_form.html",
        page_title="Contact Us",
        help_text="Have a question? Send us a message and we will reach out soon.",
        success=success,
        user=session.get("user", "Guest")
    )


if __name__ == "__main__":
    app.run(debug=True)
