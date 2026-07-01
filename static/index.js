// Blinkly settings page logic: load current settings + capabilities + stats,
// populate the form, and save as JSON (validated server-side by pydantic).

const BOOL_FIELDS = [
  "sound_enabled", "strict_mode", "skip_on_fullscreen", "idle_reset",
  "micro_breaks_enabled", "autostart_enabled", "start_minimized", "pause_blinkly",
];
const INT_FIELDS = [
  "break_interval", "break_duration", "notify_before", "volume",
  "idle_threshold", "micro_break_interval", "micro_break_duration",
];

function setValue(id, value) {
  const el = document.getElementById(id);
  if (!el) return;
  if (el.type === "checkbox") el.checked = Boolean(value);
  else el.value = value;
}

function applyPresetLock() {
  const isCustom = document.getElementById("preset").value === "custom";
  document.getElementById("interval").disabled = !isCustom;
  document.getElementById("duration").disabled = !isCustom;
}

function updateVolumeLabel() {
  document.getElementById("volume_val").textContent =
    document.getElementById("volume").value;
}

async function loadCapabilities() {
  try {
    const caps = await (await fetch("/api/capabilities")).json();
    const notes = {
      sound: caps.sound ? "" : "No audio player found — install ffmpeg for sound.",
      notifications: caps.notifications ? "" : "notify-send not found — install libnotify-bin.",
      fullscreen: caps.fullscreen ? "" : "xprop not found — install x11-utils to detect fullscreen apps.",
      idle: caps.idle ? "" : "Idle detection unavailable — install xprintidle (or use GNOME).",
    };
    document.querySelectorAll(".cap-note").forEach((el) => {
      const key = el.getAttribute("data-cap");
      el.textContent = notes[key] || "";
      el.classList.toggle("cap-warn", Boolean(notes[key]));
    });
  } catch (e) {
    /* capabilities are advisory only */
  }
}

async function loadStats() {
  try {
    const s = await (await fetch("/api/stats")).json();
    document.getElementById("today_taken").textContent = s.today.taken;
    document.getElementById("today_skipped").textContent = s.today.skipped;
    document.getElementById("week_taken").textContent = s.last7.taken;
  } catch (e) {
    /* stats are optional */
  }
}

async function loadSettings() {
  const data = await (await fetch("/api/settings")).json();
  Object.keys(data).forEach((key) => setValue(key === "break_interval" ? "interval"
    : key === "break_duration" ? "duration" : key, data[key]));
  applyPresetLock();
  updateVolumeLabel();
}

function collectPayload() {
  const payload = {};
  BOOL_FIELDS.forEach((f) => { payload[f] = document.getElementById(f).checked; });
  INT_FIELDS.forEach((f) => {
    const id = f === "break_interval" ? "interval" : f === "break_duration" ? "duration" : f;
    payload[f] = parseInt(document.getElementById(id).value, 10);
  });
  payload.preset = document.getElementById("preset").value;
  return payload;
}

document.getElementById("preset").addEventListener("change", applyPresetLock);
document.getElementById("volume").addEventListener("input", updateVolumeLabel);

document.getElementById("settings-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const res = await fetch("/api/save", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(collectPayload()),
  });
  const msg = document.getElementById("msg");
  if (res.ok) {
    msg.textContent = "Saved successfully!";
    msg.classList.remove("msg-error");
    await loadSettings();
  } else {
    msg.textContent = "Could not save — please check the values.";
    msg.classList.add("msg-error");
  }
  msg.style.display = "block";
  setTimeout(() => (msg.style.display = "none"), 2500);
});

(async function init() {
  await loadCapabilities();
  await loadSettings();
  await loadStats();
  setInterval(loadStats, 30000);
})();
