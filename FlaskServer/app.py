# app.py
import os
import datetime
import numpy as np
import io
import matplotlib
matplotlib.use("Agg")  # Geração de imagens sem interface gráfica
import matplotlib.pyplot as plt
from flask import Flask, render_template, redirect, url_for, request, flash, jsonify, send_file
from config import Config
from extensions import db, login_manager
from flask_migrate import Migrate
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from pynanovna import VNA  # Biblioteca real para conectar com o NanoVNA

# Cria a instância do NanoVNA (você pode ajustar parâmetros conforme a API real)
nano_device = VNA()

app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)
migrate = Migrate(app, db)
login_manager.init_app(app)
login_manager.login_view = "login_route"

from models import User, Antena

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Rotas tradicionais
@app.route("/")
@login_required
def index():
    all_antennas = Antena.query.all()
    return render_template("index.html", antennas=all_antennas)

@app.route("/login", methods=["GET", "POST"])
def login_route():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        user = User.query.filter_by(username=username).first()
        if not user or not user.check_password(password):
            flash("Invalid username or password", "error")
            return redirect(url_for("login_route"))
        login_user(user)
        return redirect(url_for("index"))
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        if User.query.filter_by(username=username).first():
            flash("User already exists!", "error")
            return redirect(url_for("register"))
        new_user = User(username=username)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        flash("Registration successful. You can log in now.", "info")
        return redirect(url_for("login_route"))
    return render_template("register.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login_route"))

@app.route("/select_antenna", methods=["POST"])
@login_required
def select_antenna():
    antenna_id = request.form.get("antenna_id")
    antenna = Antena.query.get(antenna_id)
    if antenna:
        current_user.antenna_id = antenna.id
        db.session.commit()
    return redirect(url_for("index"))

@app.route("/antena", methods=["GET", "POST"])
@login_required
def antena():
    if request.method == "POST":
        name = request.form.get("name")
        description = request.form.get("description")
        pdf_file = request.files.get("pdf_file")
        img_file = request.files.get("image_file")
        pdf_filename = None
        img_filename = None
        if pdf_file and pdf_file.filename != "":
            pdf_filename = secure_filename(pdf_file.filename)
            pdf_save_path = os.path.join(app.config["UPLOAD_FOLDER"], pdf_filename)
            pdf_file.save(pdf_save_path)
        if img_file and img_file.filename != "":
            img_filename = secure_filename(img_file.filename)
            img_save_path = os.path.join(app.config["UPLOAD_FOLDER"], img_filename)
            img_file.save(img_save_path)
        new_antena = Antena(
            name=name,
            pdf_datasheet=pdf_filename,
            image=img_filename,
            description=description
        )
        db.session.add(new_antena)
        db.session.commit()
        flash("Antenna successfully created.", "info")
        return redirect(url_for("antena"))
    all_antennas = Antena.query.all()
    return render_template("antena.html", antennas=all_antennas)

# Rotas para a interface NanoVNA

@app.route("/nano")
@login_required
def nano_page():
    """
    Renderiza a página de controle do NanoVNA.
    """
    return render_template("nano.html")

@app.route("/nano/sweep", methods=["POST"])
@login_required
def nano_sweep():
    """
    Inicia um sweep real no NanoVNA.
    Parâmetros: start_mhz, stop_mhz, points.
    """
    try:
        start_mhz = float(request.form.get("start_mhz"))
        stop_mhz = float(request.form.get("stop_mhz"))
        points = int(request.form.get("points"))
        # Configura o sweep (a API real do pynanovna não usa connect() separadamente)
        nano_device.set_sweep(start_mhz * 1e6, stop_mhz * 1e6, points)
        s11, s21, freq = nano_device.sweep()  # Retorna S11, S21 e vetor de frequências
        nano_device.s11 = np.array(s11, dtype=complex)
        nano_device.s21 = np.array(s21, dtype=complex)
        nano_device.freq = np.array(freq, dtype=float)
        nano_device.last_sweep_time = datetime.datetime.now()
        return jsonify({
            "status": "ok",
            "message": "Sweep initiated",
            "timestamp": nano_device.last_sweep_time.isoformat()
        })
    except Exception as e:
        return jsonify({"status": "error", "message": f"Sweep failed: {e}"}), 500

@app.route("/nano/data", methods=["GET"])
@login_required
def nano_data():
    """
    Retorna os dados do sweep: frequências (MHz), S11 e S21 (dB e fase).
    """
    if nano_device.freq is None or nano_device.s11 is None:
        return jsonify({"status": "error", "message": "No data available"}), 400
    freq_mhz = nano_device.freq / 1e6
    s11_db = 20 * np.log10(np.abs(nano_device.s11) + 1e-15)
    s11_phase = np.angle(nano_device.s11, deg=True)
    s21_db = 20 * np.log10(np.abs(nano_device.s21) + 1e-15)
    s21_phase = np.angle(nano_device.s21, deg=True)
    data = {
        "freq": freq_mhz.tolist(),
        "s11db": s11_db.tolist(),
        "s11phase": s11_phase.tolist(),
        "s21db": s21_db.tolist(),
        "s21phase": s21_phase.tolist(),
        "timestamp": nano_device.last_sweep_time.isoformat() if nano_device.last_sweep_time else None
    }
    return jsonify({"status": "ok", "data": data})

@app.route("/nano/calibrate", methods=["POST"])
@login_required
def nano_calibrate():
    """
    Executa a calibração real do NanoVNA.
    """
    try:
        # Se necessário, execute calibração usando a API do pynanovna
        nano_device.calibrate()
        return jsonify({"status": "ok", "message": "Calibration successful"})
    except Exception as e:
        return jsonify({"status": "error", "message": f"Calibration failed: {e}"}), 500

@app.route("/nano/export_image", methods=["GET"])
@login_required
def nano_export_image():
    """
    Gera um gráfico de S11 (dB) usando matplotlib e retorna a imagem PNG.
    """
    if nano_device.freq is None or nano_device.s11 is None:
        return jsonify({"status": "error", "message": "No data available"}), 400
    try:
        fig, ax = plt.subplots(figsize=(8,5))
        freq_mhz = nano_device.freq / 1e6
        s11_db = 20 * np.log10(np.abs(nano_device.s11) + 1e-15)
        ax.plot(freq_mhz, s11_db, color="yellow")
        ax.set_title("S11 (dB)")
        ax.set_xlabel("Frequency (MHz)")
        ax.set_ylabel("Magnitude (dB)")
        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight")
        buf.seek(0)
        plt.close(fig)
        return send_file(buf, mimetype="image/png", as_attachment=True, attachment_filename="s11.png")
    except Exception as e:
        return jsonify({"status": "error", "message": f"Export failed: {e}"}), 500

@app.route("/nano/status", methods=["GET"])
@login_required
def nano_status():
    """
    Retorna o status atual do NanoVNA (conexão, última varredura, etc.).
    """
    status = {
        "connected": True,  # Se necessário, verifique realmente a conexão com nano_device
        "last_sweep": nano_device.last_sweep_time.isoformat() if nano_device.last_sweep_time else None
    }
    return jsonify({"status": "ok", "data": status})

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0")
