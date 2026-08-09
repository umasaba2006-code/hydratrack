/* ------------------------------------------------------------------
   HydraTrack frontend
   - No frameworks: plain DOM + fetch().
   - The user's age/weight/target live in localStorage so the backend
     doesn't need login/session handling for a single-user demo app.
   - Every water addition is POSTed to Flask, which appends a row to
     hydration.csv and returns fresh totals.
-------------------------------------------------------------------*/

const STORAGE_KEY = "hydratrack_profile";

const screens = {
  welcome: document.getElementById("screen-welcome"),
  target: document.getElementById("screen-target"),
  dashboard: document.getElementById("screen-dashboard"),
};

function showScreen(name) {
  Object.values(screens).forEach(s => s.classList.remove("active"));
  screens[name].classList.add("active");
}

function getProfile() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || "null");
  } catch {
    return null;
  }
}

function saveProfile(profile) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(profile));
}

/* ---------------------------------------------------------------
   Wave-fill gauge (doubles as circular progress + water-level view)
----------------------------------------------------------------*/
const TOP_Y = 14;      // top of the clipped circle (cy 110, r 96)
const BOTTOM_Y = 206;  // bottom of the clipped circle
const RANGE = BOTTOM_Y - TOP_Y;

function buildWavePath(width, amplitude, wavelength, phase) {
  let d = `M 0 ${amplitude * Math.sin(phase)}`;
  for (let x = 0; x <= width; x += 10) {
    const y = amplitude * Math.sin((x / wavelength) * 2 * Math.PI + phase);
    d += ` L ${x} ${y.toFixed(2)}`;
  }
  d += ` L ${width} 300 L 0 300 Z`;
  return d;
}

function initWaves() {
  const back = document.getElementById("wave-path-back");
  const front = document.getElementById("wave-path-front");
  back.setAttribute("d", buildWavePath(660, 8, 220, Math.PI / 2));
  front.setAttribute("d", buildWavePath(660, 6, 220, 0));
}

function setGaugePercent(percent) {
  const fraction = Math.max(0, Math.min(percent / 100, 1));
  const ty = BOTTOM_Y - fraction * RANGE;
  document.getElementById("wave-group").style.transform = `translateY(${ty}px)`;
  document.getElementById("gauge-percent").textContent = `${Math.round(percent)}%`;
}

/* ---------------------------------------------------------------
   Screen 1 -> 2 : calculate target
----------------------------------------------------------------*/
document.getElementById("form-profile").addEventListener("submit", async (e) => {
  e.preventDefault();
  const age = document.getElementById("input-age").value;
  const weight_kg = document.getElementById("input-weight").value;
  const errorEl = document.getElementById("profile-error");
  errorEl.hidden = true;

  try {
    const res = await fetch("/api/target", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ age, weight_kg }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Something went wrong.");

    saveProfile({
      age: parseInt(age, 10),
      weight_kg: parseFloat(weight_kg),
      target_ml: data.target_ml,
    });

    document.getElementById("target-value").textContent = `${data.target_ml} ml`;
    document.getElementById("target-formula").textContent = `How we got this: ${data.formula}`;
    showScreen("target");
  } catch (err) {
    errorEl.textContent = err.message;
    errorEl.hidden = false;
  }
});

document.getElementById("btn-start-tracking").addEventListener("click", () => {
  showScreen("dashboard");
  loadDashboard();
});

document.getElementById("btn-edit-profile").addEventListener("click", () => {
  const profile = getProfile();
  if (profile) {
    document.getElementById("input-age").value = profile.age;
    document.getElementById("input-weight").value = profile.weight_kg;
  }
  showScreen("welcome");
});

/* ---------------------------------------------------------------
   Screen 3 : dashboard
----------------------------------------------------------------*/
function renderTotals(totals) {
  document.getElementById("gauge-percent").textContent = `${Math.round(totals.percent)}%`;
  document.getElementById("readout-consumed").textContent = totals.consumed_ml;
  document.getElementById("readout-target").textContent = totals.target_ml;
  document.getElementById("readout-remaining").textContent = `${totals.remaining_ml} ml remaining`;

  document.getElementById("stat-consumed").textContent = `${totals.consumed_ml} ml`;
  document.getElementById("stat-target").textContent = `${totals.target_ml} ml`;
  document.getElementById("stat-remaining").textContent = `${totals.remaining_ml} ml`;
  document.getElementById("stat-percent").textContent = `${Math.round(totals.percent)}%`;

  setGaugePercent(totals.percent);
}

async function refreshToday() {
  const profile = getProfile();
  const res = await fetch(`/api/today?target_ml=${profile.target_ml}`);
  const totals = await res.json();
  renderTotals(totals);
}

async function refreshStats() {
  const res = await fetch("/api/stats");
  const stats = await res.json();
  document.getElementById("stat-average").textContent = `${stats.average_daily_ml} ml`;
  document.getElementById("stat-goalrate").textContent = `${stats.goal_completion_rate}%`;
  document.getElementById("stat-streak").textContent = `${stats.current_streak} day${stats.current_streak === 1 ? "" : "s"}`;
}

function refreshChart() {
  const img = document.getElementById("weekly-chart");
  img.src = `/api/chart.png?ts=${Date.now()}`; // cache-bust so it always re-fetches
}

async function refreshInsight() {
  const body = document.getElementById("insight-body");
  const note = document.getElementById("insight-note");
  body.textContent = "Loading insight…";
  note.textContent = "";

  const res = await fetch("/api/insight");
  const data = await res.json();

  body.innerHTML = `Predicted intake for a day like today: <strong>~${data.predicted_ml} ml</strong>`;

  let noteParts = [];
  if (data.using_sample_data) {
    noteParts.push(
      `Not enough of your own history yet (${data.real_days_logged}/${data.days_needed} days logged) — ` +
      `this prediction is trained on labeled sample data just to demonstrate the model. Keep logging daily to unlock personal predictions.`
    );
  } else {
    noteParts.push(`Trained on ${data.trained_on_rows} days of your own logged data.`);
    if (data.fit_r2 !== null) {
      noteParts.push(`Fit to your data (R²): ${data.fit_r2} — not an accuracy or confidence score, just how well a straight line matches your history.`);
    }
  }
  noteParts.push("This is an educational estimate, not medical advice.");
  note.textContent = noteParts.join(" ");
}

async function loadDashboard() {
  const profile = getProfile();
  if (!profile) {
    showScreen("welcome");
    return;
  }
  document.getElementById("readout-target").textContent = profile.target_ml;
  await refreshToday();
  await refreshStats();
  refreshChart();
  await refreshInsight();
}

/* ---------------------------------------------------------------
   Adding water
----------------------------------------------------------------*/
async function addWater(amount) {
  const profile = getProfile();
  const errorEl = document.getElementById("water-error");
  errorEl.hidden = true;

  const activity_level = document.getElementById("input-activity").value;
  const temperature = document.getElementById("input-temperature").value;

  try {
    const res = await fetch("/api/water", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        water_ml: amount,
        age: profile.age,
        weight_kg: profile.weight_kg,
        target_ml: profile.target_ml,
        activity_level,
        temperature,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Could not log that amount.");

    renderTotals(data);
    refreshChart();
    refreshStats();
    refreshInsight();
  } catch (err) {
    errorEl.textContent = err.message;
    errorEl.hidden = false;
  }
}

document.querySelectorAll(".btn--chip").forEach(btn => {
  btn.addEventListener("click", () => {
    btn.classList.remove("just-added");
    void btn.offsetWidth; // restart animation
    btn.classList.add("just-added");
    addWater(parseFloat(btn.dataset.amount));
  });
});

document.getElementById("form-custom").addEventListener("submit", (e) => {
  e.preventDefault();
  const input = document.getElementById("input-custom-amount");
  const amount = parseFloat(input.value);
  const errorEl = document.getElementById("water-error");
  if (!amount || amount <= 0) {
    errorEl.textContent = "Enter an amount greater than 0.";
    errorEl.hidden = false;
    return;
  }
  addWater(amount);
  input.value = "";
});

/* ---------------------------------------------------------------
   Boot
----------------------------------------------------------------*/
initWaves();

const existingProfile = getProfile();
if (existingProfile) {
  document.getElementById("target-value").textContent = `${existingProfile.target_ml} ml`;
  showScreen("dashboard");
  loadDashboard();
} else {
  showScreen("welcome");
}
