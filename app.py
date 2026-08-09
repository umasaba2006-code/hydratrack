"""
app.py
------
HydraTrack's Flask backend.

Routes:
    GET  /                  -> the single-page app (templates/index.html)
    POST /api/target        -> compute an estimated daily hydration target
    POST /api/water         -> log a water entry, returns updated totals
    GET  /api/today         -> today's totals (consumed / target / remaining / %)
    GET  /api/stats         -> average intake, goal completion rate, streak
    GET  /api/chart.png     -> a matplotlib PNG of the last 7 days
    GET  /api/insight       -> the scikit-learn hydration prediction

All persistent state lives in data/hydration.csv, read/written with pandas.
There is no login system -- the browser keeps the user's age/weight/target
in localStorage and sends it along with each water entry.
"""

import os
import io
from datetime import datetime, date, timedelta

import pandas as pd
import matplotlib
matplotlib.use("Agg")  # render without a GUI backend
import matplotlib.pyplot as plt

from flask import Flask, render_template, request, jsonify, send_file

from ml.model import get_hydration_insight

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE_DIR, "data", "hydration.csv")
CHART_PATH = os.path.join(BASE_DIR, "charts", "weekly_chart.png")

CSV_COLUMNS = [
    "date", "time", "age", "weight_kg", "target_ml",
    "water_ml", "activity_level", "temperature",
]

ML_PER_KG = 33  # ml of water per kg of body weight -- the estimate formula


def ensure_csv():
    """Create the CSV with headers if it doesn't exist yet."""
    if not os.path.exists(CSV_PATH):
        pd.DataFrame(columns=CSV_COLUMNS).to_csv(CSV_PATH, index=False)


def read_csv() -> pd.DataFrame:
    ensure_csv()
    if os.path.getsize(CSV_PATH) == 0:
        return pd.DataFrame(columns=CSV_COLUMNS)
    df = pd.read_csv(CSV_PATH)
    for col in CSV_COLUMNS:
        if col not in df.columns:
            df[col] = None
    return df


def append_row(row: dict):
    ensure_csv()
    df = pd.DataFrame([row], columns=CSV_COLUMNS)
    df.to_csv(CSV_PATH, mode="a", header=False, index=False)


def today_str() -> str:
    return date.today().isoformat()


# ---------------------------------------------------------------- helpers

def compute_today_totals(target_ml: int) -> dict:
    df = read_csv()
    today = today_str()
    todays_rows = df[df["date"] == today] if not df.empty else df

    consumed = int(todays_rows["water_ml"].sum()) if not todays_rows.empty else 0
    target_ml = int(target_ml) if target_ml else 0
    remaining = max(target_ml - consumed, 0)
    percent = round((consumed / target_ml) * 100, 1) if target_ml > 0 else 0.0
    percent = min(percent, 999.9)  # sanity guard, no hard cap at 100 so
                                    # "goal smashed" still reads sensibly

    return {
        "consumed_ml": consumed,
        "target_ml": target_ml,
        "remaining_ml": remaining,
        "percent": percent,
    }


# ------------------------------------------------------------------ routes

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/target", methods=["POST"])
def api_target():
    data = request.get_json(silent=True) or {}
    try:
        age = int(data.get("age"))
        weight_kg = float(data.get("weight_kg"))
    except (TypeError, ValueError):
        return jsonify({"error": "Age must be a whole number and weight a number."}), 400

    if age <= 0 or age > 120:
        return jsonify({"error": "Please enter a realistic age (1-120)."}), 400
    if weight_kg <= 0 or weight_kg > 400:
        return jsonify({"error": "Please enter a realistic weight in kg (1-400)."}), 400

    target_ml = round(weight_kg * ML_PER_KG)

    return jsonify({
        "target_ml": target_ml,
        "formula": f"{weight_kg:g} kg x {ML_PER_KG} ml/kg = {target_ml} ml",
    })


@app.route("/api/water", methods=["POST"])
def api_water():
    data = request.get_json(silent=True) or {}

    try:
        water_ml = float(data.get("water_ml"))
        age = int(data.get("age"))
        weight_kg = float(data.get("weight_kg"))
        target_ml = int(data.get("target_ml"))
    except (TypeError, ValueError):
        return jsonify({"error": "Missing or invalid fields."}), 400

    if water_ml <= 0 or water_ml > 5000:
        return jsonify({"error": "Enter an amount between 1 and 5000 ml."}), 400

    activity_level = str(data.get("activity_level", "moderate")).lower()
    if activity_level not in ("low", "moderate", "high"):
        activity_level = "moderate"

    try:
        temperature = float(data.get("temperature", 25))
    except (TypeError, ValueError):
        temperature = 25.0

    now = datetime.now()
    row = {
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "age": age,
        "weight_kg": weight_kg,
        "target_ml": target_ml,
        "water_ml": water_ml,
        "activity_level": activity_level,
        "temperature": temperature,
    }
    append_row(row)

    return jsonify(compute_today_totals(target_ml))


@app.route("/api/today")
def api_today():
    try:
        target_ml = int(request.args.get("target_ml", 0))
    except (TypeError, ValueError):
        target_ml = 0
    return jsonify(compute_today_totals(target_ml))


@app.route("/api/stats")
def api_stats():
    df = read_csv()
    if df.empty:
        return jsonify({
            "average_daily_ml": 0,
            "goal_completion_rate": 0,
            "current_streak": 0,
            "days_logged": 0,
        })

    daily = df.groupby("date").agg(
        water_ml=("water_ml", "sum"),
        target_ml=("target_ml", "last"),
    ).reset_index().sort_values("date")

    average_daily_ml = round(daily["water_ml"].mean())
    met_goal = daily["water_ml"] >= daily["target_ml"]
    goal_completion_rate = round((met_goal.sum() / len(daily)) * 100)

    # Current streak: count consecutive days (ending with the most recent
    # logged day) where the target was met.
    streak = 0
    for met in met_goal[::-1]:
        if met:
            streak += 1
        else:
            break

    return jsonify({
        "average_daily_ml": int(average_daily_ml),
        "goal_completion_rate": int(goal_completion_rate),
        "current_streak": int(streak),
        "days_logged": int(len(daily)),
    })


@app.route("/api/chart.png")
def api_chart():
    df = read_csv()

    daily = pd.DataFrame(columns=["date", "water_ml", "target_ml"])
    if not df.empty:
        daily = df.groupby("date").agg(
            water_ml=("water_ml", "sum"),
            target_ml=("target_ml", "last"),
        ).reset_index().sort_values("date").tail(7)

    fig, ax = plt.subplots(figsize=(6.4, 3.4), dpi=120)

    if daily.empty:
        ax.text(0.5, 0.5, "Log some water to see your weekly chart",
                 ha="center", va="center", fontsize=11, color="#5c8a94")
        ax.set_xticks([])
        ax.set_yticks([])
    else:
        labels = [d[5:] for d in daily["date"]]  # MM-DD
        ax.bar(labels, daily["water_ml"], color="#2EC4B6", label="Water drunk (ml)", zorder=3)
        ax.plot(labels, daily["target_ml"], color="#FF7B54", marker="o",
                 linewidth=2, label="Target (ml)", zorder=4)
        ax.set_ylabel("ml")
        ax.legend(loc="upper left", frameon=False, fontsize=8)
        ax.grid(axis="y", color="#e3eef0", zorder=0)
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)

    fig.tight_layout()

    os.makedirs(os.path.dirname(CHART_PATH), exist_ok=True)
    fig.savefig(CHART_PATH, transparent=True)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", transparent=True)
    plt.close(fig)
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


@app.route("/api/insight")
def api_insight():
    result = get_hydration_insight(CSV_PATH)
    return jsonify(result)


if __name__ == "__main__":
    ensure_csv()
    app.run(debug=True, port=5000)
