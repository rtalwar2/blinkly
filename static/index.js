async function loadSettings() {
    const res = await fetch('/api/settings');
    const data = await res.json();
    document.getElementById('interval').value = data.break_interval;
    document.getElementById('duration').value = data.break_duration;
    document.getElementById('pause_blinkly').value=data.pause_blinkly;
}

document.getElementById('settings-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const formData = new FormData(e.target);
    const res = await fetch('/api/save', { method: 'POST', body: formData });
    const data = await res.json();
    const msg = document.getElementById('msg');
    msg.textContent = data.message;
    msg.style.display = 'block';
    setTimeout(() => msg.style.display = 'none', 2000);
});

loadSettings();