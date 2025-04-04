// static/nano.js

let vnaChart = null;
let sweepInterval = null;
const POLLING_INTERVAL = 500;  // 500 ms polling for continuous updates

document.addEventListener("DOMContentLoaded", () => {
  const ctx = document.getElementById("vnaChart").getContext("2d");
  // Initialize Chart.js with two datasets for S11 and S21
  vnaChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: [], // Frequencies in MHz
      datasets: [
        {
          label: 'S11 (dB)',
          data: [],
          borderColor: 'yellow',
          borderWidth: 2,
          pointRadius: 0,
          fill: false,
          tension: 0.1
        },
        {
          label: 'S21 (dB)',
          data: [],
          borderColor: 'cyan',
          borderWidth: 2,
          pointRadius: 0,
          fill: false,
          tension: 0.1
        }
      ]
    },
    options: {
      responsive: true,
      animation: { duration: 0 },
      plugins: {
        legend: { labels: { color: '#fff' } }
      },
      scales: {
        x: {
          title: { display: true, text: 'Frequency (MHz)', color: '#fff' },
          ticks: { color: '#fff' },
          grid: { color: 'rgba(255,255,255,0.2)' }
        },
        y: {
          title: { display: true, text: 'Magnitude (dB)', color: '#fff' },
          ticks: { color: '#fff' },
          grid: { color: 'rgba(255,255,255,0.2)' }
        }
      }
    }
  });
});

// Called when "Start Sweep" is clicked
function startSweep() {
  const form = document.getElementById("nanoForm");
  const formData = new FormData(form);

  fetch("/nano/sweep", { method: "POST", body: formData })
    .then(res => res.json())
    .then(data => {
      document.getElementById("chartStatus").textContent = data.message || "Sweep started";
      if (data.status === "ok") {
        const mode = document.getElementById("mode").value;
        // If continuous, poll /nano/data every 500ms
        if (mode === "continuous") {
          if (sweepInterval) clearInterval(sweepInterval);
          sweepInterval = setInterval(fetchData, POLLING_INTERVAL);
        } else {
          // Single sweep: just fetch data once
          fetchData();
        }
      }
    })
    .catch(err => {
      console.error("Error starting sweep:", err);
      document.getElementById("chartStatus").textContent = "Error starting sweep";
    });
}

// Called when "Stop Sweep" is clicked
function stopSweep() {
  if (sweepInterval) {
    clearInterval(sweepInterval);
    sweepInterval = null;
    document.getElementById("chartStatus").textContent = "Sweep stopped";
  }
}

// Poll the backend for new data
function fetchData() {
  fetch("/nano/data")
    .then(res => res.json())
    .then(json => {
      if (json.status === "ok") {
        document.getElementById("chartStatus").textContent = "Data received at " + new Date().toLocaleTimeString();
        updateChart(json.data);
      } else {
        document.getElementById("chartStatus").textContent = json.message;
      }
    })
    .catch(err => {
      console.error("Error fetching data:", err);
      document.getElementById("chartStatus").textContent = "Error fetching data";
    });
}

// Interpolation helper
function interpolateData(x, y, newLength) {
  if (newLength <= x.length) return { newX: x, newY: y };
  const xMin = x[0], xMax = x[x.length - 1];
  const step = (xMax - xMin) / (newLength - 1);
  const newX = [];
  const newY = [];

  for (let i = 0; i < newLength; i++) {
    const xi = xMin + i * step;
    let j = 0;
    while (j < x.length && x[j] < xi) j++;
    if (j === 0) {
      newX.push(x[0]);
      newY.push(y[0]);
    } else if (j >= x.length) {
      newX.push(x[x.length - 1]);
      newY.push(y[x.length - 1]);
    } else {
      const x0 = x[j - 1], x1 = x[j];
      const y0 = y[j - 1], y1 = y[j];
      const t = (xi - x0) / (x1 - x0);
      newX.push(xi);
      newY.push(y0 + t * (y1 - y0));
    }
  }
  return { newX, newY };
}

// Smoothing helper (moving average)
function smoothData(arr, windowSize) {
  if (windowSize < 2) return arr;
  const smoothed = [];
  for (let i = 0; i < arr.length; i++) {
    let sum = 0, count = 0;
    for (let j = i - Math.floor(windowSize/2); j <= i + Math.floor(windowSize/2); j++) {
      if (j >= 0 && j < arr.length) {
        sum += arr[j];
        count++;
      }
    }
    smoothed.push(sum / count);
  }
  return smoothed;
}

// Convert real/imag to magnitude in dB
function computeMagnitudeDb(realArr, imagArr) {
  const dbArr = [];
  for (let i = 0; i < realArr.length; i++) {
    const mag = Math.sqrt(realArr[i]*realArr[i] + imagArr[i]*imagArr[i]);
    dbArr.push(20 * Math.log10(mag + 1e-15));
  }
  return dbArr;
}

// Update the Chart.js line for S11 and S21
function updateChart(data) {
  // Interpolation and smoothing settings
  const interpPoints = parseInt(document.getElementById("interpPoints").value) || data.freq.length;
  const smoothWindow = parseInt(document.getElementById("smoothWindow").value) || 0;

  // Raw freq, real, imag
  let freq = data.freq;
  let s11r = data.s11_real;
  let s11i = data.s11_imag;
  let s21r = data.s21_real;
  let s21i = data.s21_imag;

  // Interpolate if needed
  if (interpPoints > freq.length) {
    const freqInterp = interpolateData(freq, freq, interpPoints).newX;
    s11r = interpolateData(freq, s11r, interpPoints).newY;
    s11i = interpolateData(freq, s11i, interpPoints).newY;
    s21r = interpolateData(freq, s21r, interpPoints).newY;
    s21i = interpolateData(freq, s21i, interpPoints).newY;
    freq = freqInterp;
  }

  // Smoothing
  if (smoothWindow > 1) {
    s11r = smoothData(s11r, smoothWindow);
    s11i = smoothData(s11i, smoothWindow);
    s21r = smoothData(s21r, smoothWindow);
    s21i = smoothData(s21i, smoothWindow);
  }

  // Compute dB
  const s11db = computeMagnitudeDb(s11r, s11i);
  const s21db = computeMagnitudeDb(s21r, s21i);

  // Update chart
  vnaChart.data.labels = freq;
  vnaChart.data.datasets[0].data = s11db;  // S11 line
  vnaChart.data.datasets[1].data = s21db;  // S21 line
  vnaChart.update();
}

// Calibration steps
function calibrationStep(stepName) {
  fetch(`/nano/calibration_step/${stepName}`, { method: "POST" })
    .then(res => res.json())
    .then(json => alert(json.message))
    .catch(err => alert("Calibration step error: " + err));
}

function finishCalibration() {
  fetch("/nano/calibration_finish", { method: "POST" })
    .then(res => res.json())
    .then(json => alert(json.message))
    .catch(err => alert("Calibration finish error: " + err));
}

// Save/Load calibration
function saveCalibration(event) {
  event.preventDefault();
  const filename = document.getElementById("saveFile").value;
  if (!filename) {
    alert("Please enter a filename to save.");
    return;
  }
  const formData = new FormData();
  formData.append("filename", filename);
  fetch("/nano/calibration_save", { method: "POST", body: formData })
    .then(res => res.json())
    .then(json => alert(json.message))
    .catch(err => alert("Save calibration error: " + err));
}

function loadCalibration(event) {
  event.preventDefault();
  const filename = document.getElementById("loadFile").value;
  if (!filename) {
    alert("Please enter a filename to load.");
    return;
  }
  const formData = new FormData();
  formData.append("filename", filename);
  fetch("/nano/calibration_load", { method: "POST", body: formData })
    .then(res => res.json())
    .then(json => alert(json.message))
    .catch(err => alert("Load calibration error: " + err));
}
