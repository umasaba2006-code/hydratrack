# 💧 HydraTrack

A small full-stack web app that estimates a personal daily hydration target,
lets you log water intake through the day, and uses a simple, explainable
machine learning model to give an educational hydration prediction based on
your own logged history.

Built as a portfolio project to demonstrate a full pipeline — frontend,
backend, data storage, data analysis, and a genuine (if beginner-level) ML
component — end to end.

---

## Overview

HydraTrack has two parts:

1. **Personalized target** — enter your age and weight, get an estimated
   daily hydration target with the formula shown clearly.
2. **Daily tracker** — log water throughout the day with quick-add buttons
   or a custom amount, and watch a wave-fill circular gauge, live stats,
   a 7-day chart, and a scikit-learn-powered "Hydration Insight" update in
   real time.

---

## Features

- Age/weight-based hydration target calculation, shown with its formula
- Wave-fill circular progress gauge (doubles as the water-level visual)
- Quick-add buttons (+150 ml / +250 ml / +500 ml) and a custom-amount input
- Live stats: today's intake, target, remaining, % complete, average daily
  intake, goal completion rate, current streak
- Weekly bar-and-line chart (water drunk vs. target) rendered with
  Matplotlib
- Machine learning "Hydration Insight" predicting expected intake from
  logged history, built with scikit-learn
- CSV-based storage (via pandas) — no database setup required
- Fully responsive layout, no frameworks on the frontend

---

## Technologies Used

| Layer            | Technology                          |
|-------------------|--------------------------------------|
| Backend framework | **Python** + **Flask**              |
| Frontend          | **HTML5**, **CSS3**, **vanilla JavaScript** |
| Data storage       | **CSV** file, read/written with **pandas** |
| Data analysis      | **pandas** (daily aggregation, averages, streaks) |
| Visualization      | **Matplotlib** (server-rendered PNG chart) |
| Machine learning    | **scikit-learn** `LinearRegression` |

No React/Vue/Angular, no database server, no authentication, no external
APIs — kept intentionally small.

---

## Hydration Target Calculation

```
target_ml = weight_kg × 33
```

This uses a commonly cited **30–35 ml of water per kilogram of body
weight** baseline (30 was chosen at the low end conceptually, 33 as a
middle estimate). It is a **general estimate**, not a personalized medical
figure — real needs vary with activity level, climate, diet, and individual
health. This is stated directly in the UI. **HydraTrack does not provide
medical advice.**

---

## Machine Learning

**Where:** `ml/model.py`, called from the `/api/insight` Flask route.

**What it predicts:** given a day's conditions, how much water the user is
likely to drink *that day*.

**Dataset:** the user's own `data/hydration.csv`, aggregated from
event-level rows (one row per water addition) into one row per calendar
day using pandas (`groupby("date")`).

**Features (X):**
1. Activity level (Low / Moderate / High → encoded 0 / 1 / 2)
2. Temperature (°C)
3. Previous day's total intake (ml)
4. That day's hydration target (ml)

**Target variable (y):** total water intake that day (ml)

**Model:** `sklearn.linear_model.LinearRegression` — chosen because it's
small, fast to train on a handful of rows, and every coefficient is
directly explainable (e.g. "for each extra degree of temperature, the
model expects roughly X ml more").

**Training process:** on every request to `/api/insight`, the CSV is
re-read, aggregated to daily rows, and the model is retrained from scratch
(the dataset is tiny, so this is instant — no need to persist a trained
model file).

**Sample data fallback:** a new user has no history to learn from. Until
at least **6 real days** are logged, the model instead trains on a small,
clearly-labeled **synthetic sample dataset** generated in `model.py`, purely
to demonstrate that the pipeline works end to end. The response JSON always
includes `using_sample_data: true/false` and the frontend displays a visible
note whenever sample data is being used — it never presents a sample-data
prediction as if it were personal.

**Limitations (also shown honestly in the UI):**
- Linear regression assumes a roughly linear relationship; real hydration
  behavior is noisier than that.
- With only a handful of days of real data, the model can easily overfit —
  which is why a fit score (R²) is only shown once there's a reasonable
  amount of real data, and it's explicitly labeled as "fit to your data,"
  never as "accuracy" or "confidence."
- This is an **educational estimate**, not a medical or clinical
  prediction.

---

## Project Structure

```
hydratrack/
├── app.py                  # Flask app: routes, target formula, CSV I/O
├── requirements.txt
├── README.md
├── .gitignore
├── data/
│   └── hydration.csv       # event log: one row per water entry
├── templates/
│   └── index.html          # single-page app (3 screens)
├── static/
│   ├── style.css           # "Tide" design system
│   └── script.js           # DOM logic, wave gauge, fetch calls
├── ml/
│   └── model.py            # pandas aggregation + LinearRegression
└── charts/
    └── weekly_chart.png    # regenerated each time /api/chart.png is hit
```

---

## Installation (macOS)

```bash
# 1. Clone or unzip the project, then move into it
cd hydratrack

# 2. Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt
```

---

## Running the Application

```bash
source venv/bin/activate    # if not already active
python3 app.py
```

Then open **http://127.0.0.1:5000** in your browser.

Stop the server with `CTRL+C`.

---

## Screenshots

*(Add screenshots of the welcome screen, target screen, and dashboard
here once you've run the app locally.)*

---

## Future Improvements

- Reminders/notifications to drink water at set intervals
- Multi-user support with basic accounts
- Adjustable target formula (e.g. accounting for activity level directly
  in the calculation, not just as an ML feature)
- Export hydration history as CSV/PDF
- Smarter streak logic (e.g. partial-credit for near-misses)
- Swap Linear Regression for a slightly more flexible model once there's
  enough real data to justify it, while keeping predictions explainable

---

## Disclaimer

HydraTrack's hydration target and machine learning prediction are
**educational estimates only**. They are based on simplified formulas and
a small linear model, not on clinical guidance. They do not account for
medical conditions, medications, pregnancy, or individual physiology.
**This is not medical advice.** Consult a healthcare professional for
guidance specific to your body and circumstances.
