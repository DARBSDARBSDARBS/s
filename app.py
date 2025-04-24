#API_KEY = "3ee011971d532898559ff99fddfea107"  
#WEATHER_API_URL = "https://api.openweathermap.org/data/3.0/onecall/day_summary?lat={lat}&lon={lon}&date={date}&tz={tz}&appid={API key}"
#GEO_KEY = "AIzaSyB8z-j4bk-jq6e5h9Mni-9CEMjMwjD5Nfo"
#GEOLOCATION_API_URL = "https://maps.googleapis.com/maps/api/geocode/outputjson?parameters"

from flask import Flask, render_template, request, redirect, url_for, flash, make_response
import sqlite3
import requests
import os
import csv
from io import StringIO
from datetime import datetime
from urllib.parse import quote
from dotenv import load_dotenv
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import MaxNLocator
import base64

load_dotenv()

app = Flask(__name__)
app.GOOGLE_KEY = os.getenv('GOOGLE_API_KEY',)


def init_db():#uztais weather.db
    with sqlite3.connect('weather.db') as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS searches
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                     city TEXT,
                     date TEXT,
                     forecast_type TEXT)''')

init_db()

def generate_temp_chart(forecast):#uztaisa temperaturas tabulu
    try:
        dates = [datetime.strptime(item['datetime'], '%Y-%m-%d %H:%M') for item in forecast]
        temps = [item['temp'] for item in forecast]
        
        plt.figure(figsize=(10, 4))
        plt.plot(dates, temps, marker='o', linestyle='-', color='#4CAF50')
        plt.title('Temperature Trend')
        plt.ylabel('Temperature (°C)')
        plt.grid(True, alpha=0.3)
        ax = plt.gca()
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d %H:%M'))
        ax.xaxis.set_major_locator(MaxNLocator(10))
        plt.xticks(rotation=45)
        plt.tight_layout()
        buffer = StringIO()
        plt.savefig(buffer, format='png')
        plt.close()
        buffer.seek(0)
        return base64.b64encode(buffer.read()).decode('utf-8')
    except Exception as e:
        print(f"Error generating chart: {e}")
        return None
def get_coords(city):#pilsetas mekletajs
    OW_KEY = os.getenv('API_KEY')
    if not OW_KEY:
        return None, None, "API key not configured"
    
    try:
        url = f"http://api.openweathermap.org/geo/1.0/direct?q={quote(city)}&limit=1&appid={OW_KEY}"
        response = requests.get(url, timeout=10)
        data = response.json()
        
        if response.status_code == 200 and data:
            return data[0]['lat'], data[0]['lon'], None
        return None, None, "City not found"
    except Exception as e:
        return None, None, f"Geocoding error: {str(e)}"

def get_weather(city, forecast_days):
    """Get weather forecast"""
    OW_KEY = os.getenv('API_KEY')
    if not OW_KEY:
        return None, None, "API key not configured" 
    try: # dabu koordinates
        lat, lon, error = get_coords(city)
        if error:
            return None, None, error
        url = f"https://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={lon}&units=metric&appid={OW_KEY}"
        response = requests.get(url, timeout=10)
        
        if response.status_code != 200:# parbauditajs
            error_msg = f"API Error {response.status_code}"
            try:
                error_data = response.json()
                error_msg = error_data.get('message', error_msg)
            except:
                error_msg = response.text[:100]
            return None, None, error_msg
        
        data = response.json()
        if not data.get('list'):
            return None, None, "No forecast data available"

        forecast = []# uzin datus
        for item in data['list'][:forecast_days*8]:
            try:
                dt = datetime.fromtimestamp(item['dt'])
                forecast.append({
                    'datetime': dt.strftime('%Y-%m-%d %H:%M'),
                    'temp': round(item['main']['temp']),
                    'weather': item['weather'][0]['description'].capitalize(),
                    'icon': item['weather'][0]['icon']
                })
            except (KeyError, TypeError) as e:
                print(f"Skipping invalid forecast item: {e}")
                continue
        
        if not forecast:
            return None, None, "No valid forecast data found"
        
        chart_base64 = generate_temp_chart(forecast)
        return forecast, chart_base64, None
        
    except Exception as e:
        return None, None, f"Weather request failed: {str(e)}"

@app.route('/', methods=['GET', 'POST'])
def city_input():
    if request.method == 'POST':
        city = request.form.get('city', '').strip()
        if city:
            return redirect(url_for('day_selection', city=city))
        flash("Please enter a city name")
    return render_template('city_input.html')

@app.route('/days/<city>', methods=['GET', 'POST'])
def day_selection(city):
    if request.method == 'POST':
        try:
            days = int(request.form.get('days', 1))
            if 1 <= days <= 5:
                return redirect(url_for('show_forecast', city=city, days=days))
            flash("Please select 1-5 days")
        except ValueError:
            flash("Invalid day selection")
    return render_template('day_selection.html', city=city)

@app.route('/forecast/<city>/<int:days>')
def show_forecast(city, days):
    forecast, chart_base64, error = get_weather(city, days)
    
    if error:
        flash(error)
        return redirect(url_for('city_input'))
    
    if not forecast:
        flash("No forecast data available")
        return redirect(url_for('city_input'))
    try:# saglabatajs 
        with sqlite3.connect('weather.db') as conn:
            conn.execute(
                "INSERT INTO searches (city, date, forecast_type) VALUES (?, datetime('now'), ?)",
                (city, f"{days}-day")
            )
    except sqlite3.Error as e:
        print(f"Database error: {e}")
    
    return render_template(
        'show_forecast.html',
        city=city,
        days=days,
        forecast=forecast,
        chart_base64=chart_base64
    )

@app.route('/export/<city>/<int:days>')
def export_csv(city, days):
    forecast, _, error = get_weather(city, days)
    if error:
        flash(error)
        return redirect(url_for('show_forecast', city=city, days=days))
    csv_data = StringIO()# uztaisa csv
    writer = csv.writer(csv_data)
    writer.writerow(['DateTime', 'Temperature (°C)', 'Weather'])
    
    for item in forecast:
        writer.writerow([
            item['datetime'],
            item['temp'],
            item['weather']
        ])
    
    response = make_response(csv_data.getvalue())
    response.headers['Content-Disposition'] = f'attachment; filename={city}_forecast.csv'
    response.headers['Content-type'] = 'text/csv'
    return response

if __name__ == '__main__':
    app.run(debug=True)