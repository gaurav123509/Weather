from flask import Flask, render_template, request, redirect, url_for, session
import requests
from datetime import datetime, timedelta, timezone

app = Flask(__name__)
app.secret_key = "change-this-secret-key"

API_KEY = "056bc2805c791e9a8ac92d45aeb77836"
BASE_URL = "https://api.openweathermap.org/data/2.5/weather"
FORECAST_URL = "https://api.openweathermap.org/data/2.5/forecast"
AIR_QUALITY_URL = "https://api.openweathermap.org/data/2.5/air_pollution"


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

@app.route("/", methods=["GET", "POST"])
def index():
    if "user" not in session:
        return redirect(url_for("login"))

    weather = None
    forecast = []
    air = None
    tips = []
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

                tips = build_tips(weather, air)
            else:
                error = "City not found or weather service unavailable. Try again!"

    return render_template(
        "index.html",
        weather=weather,
        forecast=forecast,
        air=air,
        tips=tips,
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

if __name__ == "__main__":
    app.run(debug=True)
