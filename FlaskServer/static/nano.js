// static/nano.js

// Intervalo global para varredura contínua
let sweepInterval = null;

// Inicia o sweep (único ou contínuo) usando os dados do formulário
function startSweep() {
  const form = document.getElementById("nanoForm");
  const formData = new FormData(form);
  const mode = document.getElementById("mode").value;

  fetch("/nano/sweep", {
    method: "POST",
    body: formData
  })
  .then(response => response.json())
  .then(data => {
    document.getElementById("chartStatus").textContent = data.message || "Sweep started";
    if (data.status === "ok") {
      if (mode === "continuous") {
        if (sweepInterval) clearInterval(sweepInterval);
        sweepInterval = setInterval(fetchData, 1000);  // Atualiza a cada 1 segundo
      } else {
        fetchData();  // Sweep único
      }
    }
  })
  .catch(err => {
    console.error("Error starting sweep:", err);
    document.getElementById("chartStatus").textContent = "Error starting sweep";
  });
}

// Para a varredura contínua
function stopSweep() {
  if (sweepInterval) {
    clearInterval(sweepInterval);
    sweepInterval = null;
    document.getElementById("chartStatus").textContent = "Sweep stopped";
  }
}

// Busca os dados do NanoVNA via GET
function fetchData() {
  fetch("/nano/data")
    .then(response => response.json())
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

// Renderiza os dados no canvas
function renderChart(data) {
  const canvas = document.getElementById("vnaChart");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  // Desenha eixos
  ctx.strokeStyle = "#fff";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(50, canvas.height - 50);
  ctx.lineTo(canvas.width - 20, canvas.height - 50); // eixo X
  ctx.moveTo(50, canvas.height - 50);
  ctx.lineTo(50, 20); // eixo Y
  ctx.stroke();

  // Mapeia os dados para o canvas
  const freq = data.freq;  // em MHz
  const s11db = data.s11db;
  if (freq.length === 0) return;
  const minFreq = freq[0];
  const maxFreq = freq[freq.length - 1];
  const xScale = (canvas.width - 70) / (maxFreq - minFreq);
  const minVal = Math.min(...s11db);
  const maxVal = Math.max(...s11db);
  const yScale = (canvas.height - 70) / (maxVal - minVal);

  ctx.strokeStyle = "yellow";
  ctx.beginPath();
  for (let i = 0; i < freq.length; i++) {
    let x = 50 + (freq[i] - minFreq) * xScale;
    let y = canvas.height - 50 - (s11db[i] - minVal) * yScale;
    if (i === 0) {
      ctx.moveTo(x, y);
    } else {
      ctx.lineTo(x, y);
    }
  }
  ctx.stroke();
}
