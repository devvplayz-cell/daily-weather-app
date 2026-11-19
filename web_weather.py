import urllib.request
import urllib.parse
import json
from datetime import datetime
from flask import Flask, request

app = Flask(__name__)


def temp_color(temp_f):
    if temp_f <= 40:
        return "#3b82f6"
    elif temp_f <= 52:
        return "#38bdf8"
    elif temp_f <= 64:
        return "#2dd4bf"
    elif temp_f <= 75:
        return "#facc15"
    elif temp_f <= 86:
        return "#fb923c"
    else:
        return "#f87171"


def lookup_zip(zip_code):
    clean_zip = zip_code.strip()
    geo_url = f"https://api.zippopotam.us/us/{urllib.parse.quote(clean_zip)}"
    req = urllib.request.Request(geo_url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=5) as response:
        geo_data = json.loads(response.read().decode("utf-8"))

    place = geo_data["places"][0]
    city_name = place["place name"]
    state_abbr = place["state abbreviation"]
    lat = place["latitude"]
    lon = place["longitude"]
    return f"{city_name}, {state_abbr}", lat, lon


def build_temp_graph(hour_labels, temps_f):
    width = 360
    height = 120
    pad_left = 12
    pad_right = 42
    pad_top = 12
    pad_bottom = 22

    plot_w = width - pad_left - pad_right
    plot_h = height - pad_top - pad_bottom

    min_t = min(temps_f) - 3
    max_t = max(temps_f) + 3
    if max_t == min_t:
        max_t += 1

    points = []
    count = len(temps_f)
    for idx, t in enumerate(temps_f):
        x = pad_left if count == 1 else pad_left + (idx / (count - 1)) * plot_w
        ratio = (t - min_t) / (max_t - min_t)
        y = pad_top + (1 - ratio) * plot_h
        points.append((round(x, 1), round(y, 1), t))

    line_coords = " ".join(f"{x},{y}" for x, y, _ in points)
    first_x, _, _ = points[0]
    last_x, _, _ = points[-1]
    bottom_y = pad_top + plot_h
    area_coords = f"{line_coords} {last_x},{bottom_y} {first_x},{bottom_y}"

    stops = []
    for idx, (_, _, t) in enumerate(points):
        pct = 0 if count == 1 else round((idx / (count - 1)) * 100, 1)
        color = temp_color(t)
        stops.append(f'<stop offset="{pct}%" stop-color="{color}" />')

    # Build 4 evenly spaced horizontal dashed lines + right-side labels
    num_grid_lines = 4
    grid_elements = []
    for i in range(num_grid_lines):
        frac = i / (num_grid_lines - 1)
        gy = round(pad_top + frac * plot_h, 1)
        label_t = int(round(max_t - frac * (max_t - min_t)))
        grid_elements.append(
            f'<line x1="{pad_left}" y1="{gy}" x2="{width - pad_right}" y2="{gy}" class="grid-line" />'
            f'<text x="{width - 4}" y="{gy + 3.5}" text-anchor="end" class="axis-text">{label_t}°</text>'
        )

    tick_indices = [0, count // 3, (2 * count) // 3, count - 1]
    tick_indices = sorted(set(i for i in tick_indices if 0 <= i < count))
    time_ticks = []
    for i in tick_indices:
        tx, _, _ = points[i]
        short_label = hour_labels[i].replace(":00", "")
        time_ticks.append(
            f'<text x="{tx}" y="{height - 5}" text-anchor="middle" class="axis-text">{short_label}</text>'
        )

    return f"""
    <div class="graph-box">
        <svg viewBox="0 0 {width} {height}" class="temp-svg" aria-label="Hourly temperature graph">
            <defs>
                <linearGradient id="tempLineGrad" x1="0%" y1="0%" x2="100%" y2="0%">
                    {"".join(stops)}
                </linearGradient>
                <linearGradient id="tempAreaGrad" x1="0%" y1="0%" x2="0%" y2="100%">
                    <stop offset="0%" stop-color="#f59e0b" stop-opacity="0.24" />
                    <stop offset="100%" stop-color="#f59e0b" stop-opacity="0.02" />
                </linearGradient>
            </defs>

            {"".join(grid_elements)}

            <polygon points="{area_coords}" fill="url(#tempAreaGrad)" />
            <polyline
                fill="none"
                stroke="url(#tempLineGrad)"
                stroke-width="2.5"
                stroke-linecap="round"
                stroke-linejoin="round"
                points="{line_coords}"
            />

            {"".join(time_ticks)}
        </svg>
    </div>
    """


@app.route("/")
def home():
    zip_input = request.args.get("zip", "").strip()
    error_message = ""

    location_label = "Leander, TX"
    lat = "30.5788"
    lon = "-97.8531"

    if zip_input:
        try:
            location_label, lat, lon = lookup_zip(zip_input)
        except Exception:
            error_message = f'Could not find ZIP code "{zip_input}". Showing Leander, TX.'

    weather_url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        f"&current=temperature_2m,apparent_temperature"
        f"&hourly=temperature_2m,apparent_temperature"
        f"&temperature_unit=fahrenheit&timezone=auto"
    )

    try:
        with urllib.request.urlopen(weather_url, timeout=5) as response:
            weather_data = json.loads(response.read().decode("utf-8"))
    except Exception:
        return "<h1>Weather service temporarily unavailable. Please refresh.</h1>"

    current_data = weather_data.get("current", {})
    current_temp = int(round(current_data.get("temperature_2m", 0)))
    current_feels_like = int(round(current_data.get("apparent_temperature", current_temp)))
    current_color = temp_color(current_temp)

    hourly_data = weather_data["hourly"]
    times = hourly_data["time"]
    temps = hourly_data["temperature_2m"]
    feels_like_list = hourly_data["apparent_temperature"]

    current_time_str = current_data.get("time", "")
    start_index = 0
    if current_time_str in times:
        start_index = times.index(current_time_str)

    end_index = min(start_index + 24, len(times))

    hour_labels = []
    hour_temps = []
    lines = []

    for i in range(start_index, end_index):
        dt = datetime.fromisoformat(times[i])
        hour_label = dt.strftime("%I:%M %p").lstrip("0")
        temp_f = int(round(temps[i]))
        feels_f = int(round(feels_like_list[i]))
        row_color = temp_color(temp_f)

        hour_labels.append(hour_label)
        hour_temps.append(temp_f)

        lines.append(
            f'<div class="row">'
            f'<span class="time">{hour_label}</span>'
            f'<span class="temps">'
            f'<span class="temp" style="color: {row_color};">{temp_f}°F</span> '
            f'<span class="feels">Feels {feels_f}°F</span>'
            f'</span>'
            f'</div>'
        )

    graph_html = build_temp_graph(hour_labels, hour_temps)
    error_html = f'<p class="error">{error_message}</p>' if error_message else ""

    return f"""
    <html>
    <head>
        <title>Daily Weather in {location_label}</title>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
        <link
            href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@500;600;700&family=Plus+Jakarta+Sans:wght@500;600;700&display=swap"
            rel="stylesheet"
        />
        <style>
            body {{
                background-color: #14110f;
                color: #f5f0eb;
                font-family: "Plus Jakarta Sans", -apple-system, BlinkMacSystemFont, sans-serif;
                display: flex;
                justify-content: center;
                padding: 12px 16px;
                margin: 0;
            }}
            .card {{
                background-color: #1f1a17;
                border: 1px solid #332b26;
                padding: 16px 20px;
                border-radius: 16px;
                width: 100%;
                max-width: 396px;
                box-shadow: 0 14px 30px rgba(0, 0, 0, 0.5);
            }}
            h1 {{
                font-size: 19px;
                font-weight: 700;
                letter-spacing: -0.02em;
                margin: 0 0 10px 0;
                text-align: center;
                color: #f5f0eb;
            }}
            .zip-form {{
                display: flex;
                gap: 8px;
                margin-bottom: 10px;
            }}
            .zip-input {{
                flex: 1;
                padding: 6px 10px;
                border-radius: 8px;
                border: 1px solid #332b26;
                background-color: #14110f;
                color: #f5f0eb;
                font-family: "JetBrains Mono", monospace;
                font-size: 13px;
            }}
            .zip-input:focus {{
                outline: none;
                border-color: #f59e0b;
            }}
            .zip-btn {{
                padding: 6px 12px;
                border-radius: 8px;
                border: none;
                background-color: #f59e0b;
                color: #14110f;
                font-family: "Plus Jakarta Sans", sans-serif;
                font-weight: 700;
                font-size: 13px;
                cursor: pointer;
            }}
            .current-box {{
                background-color: #14110f;
                border: 1px solid #332b26;
                border-radius: 10px;
                padding: 10px 14px;
                margin-bottom: 10px;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }}
            .current-temp {{
                font-family: "JetBrains Mono", monospace;
                font-size: 28px;
                font-weight: 700;
                line-height: 1.1;
            }}
            .current-label {{
                font-size: 10px;
                font-weight: 600;
                letter-spacing: 0.08em;
                color: #b5a89e;
            }}
            .current-feels {{
                font-size: 13px;
                color: #e6ddd5;
                text-align: right;
            }}
            .current-feels strong {{
                font-family: "JetBrains Mono", monospace;
            }}
            .graph-box {{
                background-color: #14110f;
                border: 1px solid #332b26;
                border-radius: 10px;
                padding: 8px 10px;
                margin-bottom: 10px;
            }}
            .temp-svg {{
                width: 100%;
                height: auto;
                display: block;
            }}
            .grid-line {{
                stroke: #332b26;
                stroke-width: 1;
                stroke-dasharray: 3 3;
            }}
            .axis-text {{
                fill: #b5a89e;
                font-size: 9.5px;
                font-family: "JetBrains Mono", monospace;
            }}
            .error {{
                color: #f87171;
                font-size: 12px;
                margin: 0 0 8px 0;
                text-align: center;
            }}
            .row {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 3px 4px;
                border-bottom: 1px solid #332b26;
                font-size: 13px;
            }}
            .row:last-child {{
                border-bottom: none;
            }}
            .time {{
                font-family: "JetBrains Mono", monospace;
                font-size: 12px;
                color: #ede6df;
            }}
            .temp {{
                font-family: "JetBrains Mono", monospace;
                font-weight: 600;
                font-size: 12px;
            }}
            .feels {{
                font-family: "JetBrains Mono", monospace;
                color: #b5a89e;
                font-size: 11px;
                margin-left: 6px;
            }}
        </style>
    </head>
    <body>
        <div class="card">
            <h1>Daily Weather in {location_label}</h1>
            <form class="zip-form" method="GET" action="/">
                <input
                    class="zip-input"
                    type="text"
                    name="zip"
                    placeholder="Enter ZIP (e.g. 78641)"
                    value="{zip_input}"
                    maxlength="10"
                />
                <button class="zip-btn" type="submit">Go</button>
            </form>
            {error_html}
            <div class="current-box">
                <div>
                    <div class="current-label">NOW</div>
                    <div class="current-temp" style="color: {current_color};">{current_temp}°F</div>
                </div>
                <div class="current-feels">
                    Feels like<br />
                    <strong>{current_feels_like}°F</strong>
                </div>
            </div>
            {graph_html}
            {"".join(lines)}
        </div>
    </body>
    </html>
    """


if __name__ == "__main__":
    app.run(debug=True)