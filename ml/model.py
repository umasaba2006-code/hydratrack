"""
ml/model.py
-----------
The AI/ML piece of HydraTrack.

WHAT IT PREDICTS
    Given a day's conditions (activity level, temperature, hydration target,
    and how much water was drunk the PREVIOUS day), predict how much water
    the user is likely to drink TODAY.

FEATURES  -> X
    1. activity_level_encoded   (Low=0, Moderate=1, High=2)
    2. temperature               (deg C)
    3. previous_day_ml           (water drunk the day before)
    4. target_ml                 (that day's hydration goal)

TARGET    -> y
    water_ml   (total water actually drunk that day)

MODEL
    sklearn.linear_model.LinearRegression
    Chosen because it's small, fast, and every coefficient is directly
    explainable ("for every extra degree, the model expects X ml more/less"),
    which matters more here than squeezing out extra accuracy.

HONESTY RULES BAKED INTO THIS FILE
    - If there isn't enough REAL logged data, we say so and fall back to a
      clearly-labeled synthetic sample dataset just to demonstrate the
      pipeline. We never present sample-data predictions as if they were
      personal to the user.
    - We never invent an accuracy number. R^2 is only reported once there is
      a reasonable amount of real data, and it is labeled as a fit-to-data
      measure, not "accuracy" or "confidence".
"""

import os
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

ACTIVITY_ENCODING = {"low": 0, "moderate": 1, "high": 2}
MIN_REAL_DAYS_REQUIRED = 6  # need at least this many real days (with a
                             # previous-day value) before we trust real data


def _encode_activity(series):
    return series.str.lower().map(ACTIVITY_ENCODING).fillna(1).astype(int)


def _daily_aggregate(df: pd.DataFrame) -> pd.DataFrame:
    """Collapse event-level rows (one per water addition) into one row
    per calendar day."""
    daily = (
        df.groupby("date")
        .agg(
            water_ml=("water_ml", "sum"),
            target_ml=("target_ml", "last"),
            activity_level=("activity_level", "last"),
            temperature=("temperature", "mean"),
        )
        .reset_index()
        .sort_values("date")
    )
    daily["activity_encoded"] = _encode_activity(daily["activity_level"])
    daily["previous_day_ml"] = daily["water_ml"].shift(1)
    return daily


def _make_sample_dataset(n_days: int = 21, seed: int = 7) -> pd.DataFrame:
    """Small synthetic dataset used ONLY when the user doesn't have enough
    real history yet. Clearly separate from real user data -- never written
    to hydration.csv."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2026-01-01", periods=n_days, freq="D")
    activity = rng.choice(["low", "moderate", "high"], size=n_days, p=[0.3, 0.45, 0.25])
    activity_encoded = pd.Series(activity).map(ACTIVITY_ENCODING).values
    temperature = rng.normal(26, 4, size=n_days).round(1)
    target_ml = rng.integers(1800, 2600, size=n_days)

    # Loosely simulate a real relationship: higher activity/temperature and
    # a higher target nudge intake up, plus noise, so LinearRegression has
    # something genuine (if synthetic) to learn.
    water_ml = (
        0.55 * target_ml
        + 120 * activity_encoded
        + 8 * temperature
        + rng.normal(0, 120, size=n_days)
    ).round().astype(int)
    water_ml = np.clip(water_ml, 400, None)

    daily = pd.DataFrame(
        {
            "date": dates.strftime("%Y-%m-%d"),
            "water_ml": water_ml,
            "target_ml": target_ml,
            "activity_level": activity,
            "temperature": temperature,
            "activity_encoded": activity_encoded,
        }
    )
    daily["previous_day_ml"] = daily["water_ml"].shift(1)
    return daily


def get_hydration_insight(csv_path: str) -> dict:
    """Main entry point called by Flask. Returns a JSON-serializable dict."""
    feature_cols = ["activity_encoded", "temperature", "previous_day_ml", "target_ml"]

    real_daily = pd.DataFrame()
    if os.path.exists(csv_path):
        raw = pd.read_csv(csv_path)
        if not raw.empty:
            real_daily = _daily_aggregate(raw)

    real_trainable = real_daily.dropna(subset=feature_cols) if not real_daily.empty else real_daily

    using_sample_data = len(real_trainable) < MIN_REAL_DAYS_REQUIRED

    if using_sample_data:
        training_data = _make_sample_dataset().dropna(subset=feature_cols)
        # Predict for a "next day" using the most recent real day's
        # conditions if we have at least one real row, otherwise use the
        # sample data's own latest row.
        if not real_daily.empty:
            latest = real_daily.iloc[-1]
            latest_features = {
                "activity_encoded": ACTIVITY_ENCODING.get(str(latest["activity_level"]).lower(), 1),
                "temperature": latest["temperature"] if pd.notna(latest["temperature"]) else 25.0,
                "previous_day_ml": latest["water_ml"],
                "target_ml": latest["target_ml"],
            }
        else:
            latest_features = training_data.iloc[-1][feature_cols].to_dict()
    else:
        training_data = real_trainable
        latest = real_daily.iloc[-1]
        latest_features = {
            "activity_encoded": ACTIVITY_ENCODING.get(str(latest["activity_level"]).lower(), 1),
            "temperature": latest["temperature"] if pd.notna(latest["temperature"]) else 25.0,
            "previous_day_ml": latest["water_ml"],
            "target_ml": latest["target_ml"],
        }

    X = training_data[feature_cols].astype(float).values
    y = training_data["water_ml"].astype(float).values

    model = LinearRegression()
    model.fit(X, y)

    X_pred = np.array([[latest_features[c] for c in feature_cols]])
    predicted_ml = float(model.predict(X_pred)[0])
    predicted_ml = max(0, round(predicted_ml))

    result = {
        "predicted_ml": predicted_ml,
        "using_sample_data": bool(using_sample_data),
        "real_days_logged": int(len(real_trainable)),
        "days_needed": MIN_REAL_DAYS_REQUIRED,
        "trained_on_rows": int(len(training_data)),
        "features_used": [
            "activity level",
            "temperature",
            "previous day's intake",
            "daily target",
        ],
        "fit_r2": None,
    }

    # Only surface a fit score once there is a meaningful amount of REAL data
    # -- and call it what it is, not "accuracy".
    if not using_sample_data and len(training_data) >= 8:
        result["fit_r2"] = round(float(model.score(X, y)), 2)

    return result
