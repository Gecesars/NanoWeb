// static/nano.js

let sweepInterval = null;
let currentGraphType = 's11'; 
const POLLING_INTERVAL = 500; // faster updates

function startSweep() {
  const form = document.getElementById("nanoForm");
  const formData = new FormData(form);
  const mode = document.getElementById("mode").value;

  fetch("/nano/sweep", {
    method: "POST",
    body: formData
  })
  .then(res => res.json())
  .then(data => {
    document.getElementById("chartStatus").textContent = data.message || "Sweep started";
    if (data.status === "ok") {
      if (mode === "continuous") {
        if (sweepInterval) clearInterval(sweepInterval);
        sweepInterval = setInterval(fetchData, POLLING_INTERVAL);
      } else {
        fetchData();
      }
    }
  })
  .catch(err => {
    console.error("Error starting sweep:", err);
    document.getElementById("chartStatus").textContent = "Error starting sweep";
  });
}

function stopSweep() {
  if (sweepInterval) {
    clearInterval(sweepInterval);
    sweepInterval = null;
    document.getElementById("chartStatus").textContent = "Sweep stopped";
  }
}

function fetchData() {
  fetch("/nano/data")
    .then(res => res.json())
    .then(json => {
      if (json.status === "ok") {
        document.getElementById("chartStatus").textContent = "Data received at " + new Date().toLocaleTimeString();
        renderChart(json.data);
      } else {
        document.getElementById("chartStatus").textContent = json.message;
      }
    })
    .catch(err => {
      console.error("Error fetching data:", err);
      document.getElementById("chartStatus").textContent = "Error fetching data";
    });
}

// Step-by-step calibration
function calibrationStep(stepName) {
  fetch(`/nano/calibration_step/${stepName}`, { method: "POST" })
    .then(res => res.json())
    .then(json => {
      if (json.status === "ok") {
        alert(json.message);
      } else {
        alert(json.message);
      }
    })
    .catch(err => alert("Calibration step error: " + err));
}

function finishCalibration() {
  fetch("/nano/calibration_finish", { method: "POST" })
    .then(res => res.json())
    .then(json => {
      if (json.status === "ok") {
        alert(json.message);
      } else {
        alert(json.message);
      }
    })
    .catch(err => alert("Calibration finalize error: " + err));
}

// Save / Load calibration
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
    .then(json => {
      if (json.status === "ok") {
        alert(json.message);
      } else {
        alert(json.message);
      }
    })
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
    .then(json => {
      if (json.status === "ok") {
        alert(json.message);
      } else {
        alert(json.message);
      }
    })
    .catch(err => alert("Load calibration error: " + err));
}

// Graph type selection
function setGraphType(type) {
  currentGraphType = type;
  fetchData(); // re-fetch to update chart with new type
}

// Render the chart with axis labels, grid, etc.
function renderChart(data) {
  const canvas = document.getElementById("vnaChart");
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  // Draw background
  ctx.fillStyle = "#222";
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  // Basic margin for axes
  const marginLeft = 50;
  const marginRight = 20;
  const marginTop = 20;
  const marginBottom = 50;

  const plotWidth = canvas.width - (marginLeft + marginRight);
  const plotHeight = canvas.height - (marginTop + marginBottom);

  // Draw axes border
  ctx.strokeStyle = "#fff";
  ctx.lineWidth = 2;
  ctx.strokeRect(marginLeft, marginTop, plotWidth, plotHeight);

  const freq = data.freq; // in MHz
  if (!freq || freq.length === 0) return;

  // Determine yData based on currentGraphType
  let yData;
  switch (currentGraphType) {
    case "s21":
      yData = data.s21db;
      break;
    case "phase":
      yData = data.s11phase; // for demonstration
      break;
    case "smith":
      // Smith chart is typically an image or separate rendering
      ctx.fillStyle = "#fff";
      ctx.font = "16px Arial";
      ctx.fillText("Smith chart not rendered on canvas", marginLeft + 10, marginTop + 30);
      return;
    case "tdr":
      // TDR example using s11db
      yData = data.s11db;
      break;
    case "s11":
    default:
      yData = data.s11db;
      break;
  }

  // Compute min/max
  const minFreq = freq[0];
  const maxFreq = freq[freq.length - 1];
  let yMin = Infinity;
  let yMax = -Infinity;
  for (let i = 0; i < yData.length; i++) {
    if (yData[i] < yMin) yMin = yData[i];
    if (yData[i] > yMax) yMax = yData[i];
  }
  // Axis expansions
  const freqRange = maxFreq - minFreq;
  const yRange = yMax - yMin || 1;

  // Draw grid lines (vertical and horizontal)
  ctx.strokeStyle = "#666";
  ctx.lineWidth = 1;
  ctx.setLineDash([3,3]); // dashed lines
  const numGridLines = 5;
  for (let i = 0; i <= numGridLines; i++) {
    // vertical lines
    const xPos = marginLeft + (i / numGridLines) * plotWidth;
    ctx.beginPath();
    ctx.moveTo(xPos, marginTop);
    ctx.lineTo(xPos, marginTop + plotHeight);
    ctx.stroke();

    // horizontal lines
    const yPos = marginTop + plotHeight - (i / numGridLines) * plotHeight;
    ctx.beginPath();
    ctx.moveTo(marginLeft, yPos);
    ctx.lineTo(marginLeft + plotWidth, yPos);
    ctx.stroke();
  }
  ctx.setLineDash([]); // reset dash

  // Axis labeling
  ctx.fillStyle = "#fff";
  ctx.font = "14px Arial";

  // X-axis freq labels
  for (let i = 0; i <= numGridLines; i++) {
    const freqVal = minFreq + (i / numGridLines) * freqRange;
    const xPos = marginLeft + (i / numGridLines) * plotWidth;
    const yPos = marginTop + plotHeight + 20;
    ctx.fillText(freqVal.toFixed(1), xPos - 10, yPos);
  }
  // Y-axis labels
  for (let i = 0; i <= numGridLines; i++) {
    const val = yMin + (i / numGridLines) * yRange;
    const xPos = marginLeft - 40;
    const yPos = marginTop + plotHeight - (i / numGridLines) * plotHeight;
    ctx.fillText(val.toFixed(1), xPos, yPos + 5);
  }

  // Plot data line
  ctx.strokeStyle = "yellow";
  ctx.lineWidth = 2;
  ctx.beginPath();
  for (let i = 0; i < freq.length; i++) {
    const xFrac = (freq[i] - minFreq) / freqRange;
    const yFrac = (yData[i] - yMin) / yRange;
    const xPixel = marginLeft + xFrac * plotWidth;
    const yPixel = marginTop + plotHeight - (yFrac * plotHeight);

    if (i === 0) ctx.moveTo(xPixel, yPixel);
    else ctx.lineTo(xPixel, yPixel);
  }
  ctx.stroke();
}

// Step-by-step calibration
function calibrateDevice() {
  alert("This is a simple calibrate button. Use step-by-step calibration below or implement a direct auto-calibrate if your device supports it.");
}
