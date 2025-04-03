# app.py
import os
import datetime
import numpy as np
import io
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from flask import Flask, render_template, redirect, url_for, request, flash, jsonify, send_file
from config import Config
from extensions import db, login_manager
from flask_migrate import Migrate
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename

from pynanovna import VNA  # Real NanoVNA library (replace with your actual API if needed)

# Global NanoVNA instance
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

# --------------------------
# Main / Auth / Profile
# --------------------------
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
            flash("Invalid username or password", "danger")
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
        full_name = request.form.get("full_name")
        email = request.form.get("email")
        phone = request.form.get("phone")

        if User.query.filter_by(username=username).first():
            flash("User already exists!", "danger")
            return redirect(url_for("register"))
        new_user = User(username=username, full_name=full_name, email=email, phone=phone)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        flash("Registration successful. You can log in now.", "success")
        return redirect(url_for("login_route"))
    return render_template("register.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login_route"))

@app.route("/profile", methods=["POST"])
@login_required
def profile():
    """Updates user profile and shows success message."""
    current_user.full_name = request.form.get("full_name")
    current_user.email = request.form.get("email")
    current_user.phone = request.form.get("phone")
    db.session.commit()
    flash("Profile updated successfully!", "success")
    return redirect(url_for("index"))

# --------------------------
# Antenna Management
# --------------------------
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
        flash("Antenna successfully created.", "success")
        return redirect(url_for("antena"))

    all_antennas = Antena.query.all()
    return render_template("antena.html", antennas=all_antennas)

@app.route("/select_antenna", methods=["POST"])
@login_required
def select_antenna():
    antenna_id = request.form.get("antenna_id")
    antenna = Antena.query.get(antenna_id)
    if antenna:
        current_user.antenna_id = antenna.id
        db.session.commit()
    return redirect(url_for("index"))

# --------------------------
# NanoVNA Control
# --------------------------
@app.route("/nano")
@login_required
def nano_page():
    """NanoVNA control interface."""
    return render_template("nano.html")

@app.route("/nano/sweep", methods=["POST"])
@login_required
def nano_sweep():
    """Initiates a sweep on the NanoVNA with given start/stop/points."""
    try:
        start_mhz = float(request.form.get("start_mhz"))
        stop_mhz = float(request.form.get("stop_mhz"))
        points = int(request.form.get("points"))
        nano_device.set_sweep(start_mhz * 1e6, stop_mhz * 1e6, points)
        s11, s21, freq = nano_device.sweep()
        nano_device.s11 = np.array(s11, dtype=complex)
        nano_device.s21 = np.array(s21, dtype=complex)
        nano_device.freq = np.array(freq, dtype=float)
        nano_device.last_sweep_time = datetime.datetime.now()
        return jsonify({
            "status": "ok",
            "message": "Sweep initiated successfully",
            "timestamp": nano_device.last_sweep_time.isoformat()
        })
    except Exception as e:
        return jsonify({"status": "error", "message": f"Sweep failed: {e}"}), 500

@app.route("/nano/data", methods=["GET"])
@login_required
def nano_data():
    """Returns the latest S-parameter data (freq in MHz, S11 & S21 in dB/phase)."""
    if not hasattr(nano_device, 'freq') or nano_device.freq is None:
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

# --------------------------
# Step-by-step Calibration
# --------------------------
@app.route("/nano/calibration_step/<step_name>", methods=["POST"])
@login_required
def nano_calibration_step(step_name):
    """
    Perform a single calibration step: 'open', 'short', 'load',
    'isolation', 'through', etc.
    """
    try:
        nano_device.calibration_step(step_name)
        return jsonify({"status": "ok", "message": f"Calibration step '{step_name}' done."})
    except Exception as e:
        return jsonify({"status": "error", "message": f"Calibration step failed: {e}"}), 500

@app.route("/nano/calibration_finish", methods=["POST"])
@login_required
def nano_calibration_finish():
    """Finalize the calibration after all steps."""
    try:
        nano_device.calibrate()
        return jsonify({"status": "ok", "message": "Calibration finalized."})
    except Exception as e:
        return jsonify({"status": "error", "message": f"Calibration finalize failed: {e}"}), 500

# --------------------------
# Save / Load Calibration
# --------------------------
@app.route("/nano/calibration_save", methods=["POST"])
@login_required
def nano_calibration_save():
    """Saves the current calibration to a local file."""
    filename = request.form.get("filename")
    if not filename:
        return jsonify({"status": "error", "message": "No filename provided"}), 400
    save_path = os.path.join(app.config["CALIBRATION_FOLDER"], filename)
    try:
        nano_device.save_calibration(save_path)
        return jsonify({"status": "ok", "message": f"Calibration saved to {filename}"})
    except Exception as e:
        return jsonify({"status": "error", "message": f"Save calibration failed: {e}"}), 500

@app.route("/nano/calibration_load", methods=["POST"])
@login_required
def nano_calibration_load():
    """Loads a previously saved calibration from local file."""
    filename = request.form.get("filename")
    if not filename:
        return jsonify({"status": "error", "message": "No filename provided"}), 400
    load_path = os.path.join(app.config["CALIBRATION_FOLDER"], filename)
    if not os.path.exists(load_path):
        return jsonify({"status": "error", "message": f"File {filename} not found"}), 404
    try:
        nano_device.load_calibration(load_path)
        return jsonify({"status": "ok", "message": f"Calibration {filename} loaded successfully"})
    except Exception as e:
        return jsonify({"status": "error", "message": f"Load calibration failed: {e}"}), 500

# --------------------------
# Export S11 as PNG
# --------------------------
@app.route("/nano/export_image", methods=["GET"])
@login_required
def nano_export_image():
    """
    Generates a PNG of S11 vs freq and returns it as a file download.
    """
    if not hasattr(nano_device, 'freq') or nano_device.freq is None:
        return jsonify({"status": "error", "message": "No data available"}), 400
    try:
        fig, ax = plt.subplots(figsize=(8,5))
        freq_mhz = nano_device.freq / 1e6
        s11_db = 20 * np.log10(np.abs(nano_device.s11) + 1e-15)

        ax.plot(freq_mhz, s11_db, color="yellow")
        ax.set_title("S11 (dB)")
        ax.set_xlabel("Frequency (MHz)")
        ax.set_ylabel("Magnitude (dB)")
        ax.grid(True)

        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight")
        buf.seek(0)
        plt.close(fig)
        return send_file(buf, mimetype="image/png", as_attachment=True, attachment_filename="s11.png")
    except Exception as e:
        return jsonify({"status": "error", "message": f"Export failed: {e}"}), 500

# --------------------------
# Device Status
# --------------------------
@app.route("/nano/status", methods=["GET"])
@login_required
def nano_status():
    """
    Returns current NanoVNA status (e.g., last sweep time).
    """
    status = {
        "connected": nano_device.is_connected() if hasattr(nano_device, "is_connected") else True,
        "last_sweep": nano_device.last_sweep_time.isoformat() if hasattr(nano_device, 'last_sweep_time') and nano_device.last_sweep_time else None
    }
    return jsonify({"status": "ok", "data": status})

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0")
