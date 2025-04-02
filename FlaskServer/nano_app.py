#!/usr/bin/env python3
"""
================================================================================
NanoVNA – Aplicativo Completo com Interface “Premium”
  - Conexão real com o NanoVNA via pynanovna
  - Sweep (varredura) e streaming com parâmetros configuráveis
  - Calibração: manual, automática e carregamento de calibração
  - Gráficos: S‑Parameters (dB e fase), Smith Chart e TDR (em ns)
  - Marcas arrastáveis que exibem interseções com os gráficos (valores de S11, S21, VSWR, impedância, etc.)
  - Menu de botão direito (context menu) com opções: Exportar Imagem, Exportar s2P, Aplicar Escala personalizada
  - Exportação de imagens e dados Touchstone
  - Layout com sidebar “premium” e status bar de fácil leitura
  - Logo exibido em cada gráfico
================================================================================
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
import threading, time, datetime, os, warnings
warnings.filterwarnings("ignore", category=RuntimeWarning)

import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import numpy as np

import scipy

# Aplicando o patch para mapear scipy.linspace para numpy.linspace
scipy.linspace = np.linspace

import skrf as rf
from pynanovna import VNA  # Certifique-se de ter esta biblioteca instalada

from scipy.interpolate import interp1d
from scipy.signal import windows

# Para exportar dados em XLS (usando openpyxl)
from openpyxl import Workbook
# Para exportar imagens (usando Pillow)
from PIL import Image, ImageTk, ImageGrab

###############################################################################
# Classe DraggableMark – Marca arrastável (para exibir valores sobrepostos)
###############################################################################
class DraggableMark:
    def __init__(self, x_value, app_ref, domain="freq"):
        """
        x_value: valor (em MHz se domain=="freq", ou em segundos se domain=="time")
        app_ref: referência para o aplicativo principal
        domain: "freq" ou "time"
        """
        self.x_value = x_value
        self.app = app_ref
        self.domain = domain
        self.plots_data = {}  # Guarda, para cada eixo, o objeto (linha ou ponto), conexões de eventos e textos
        self._press_info = None

    def ensure_line_on_axis(self, ax, plot_type="cartesian"):
        if ax in self.plots_data:
            return
        fig = ax.figure
        if plot_type == "cartesian":
            line = ax.axvline(self.x_value, color="blue", linestyle="--", picker=5)
            cidp = fig.canvas.mpl_connect("button_press_event", self.on_press)
            cidm = fig.canvas.mpl_connect("motion_notify_event", self.on_motion)
            cidr = fig.canvas.mpl_connect("button_release_event", self.on_release)
            self.plots_data[ax] = {"line": line, "cids": (cidp, cidm, cidr), "texts": []}
        else:
            freq_arr = self.app.freq
            if freq_arr is not None and freq_arr.size > 0 and self.app.s11 is not None:
                idx = np.argmin(np.abs(freq_arr - self.x_value * 1e6))
                if 0 <= idx < len(freq_arr):
                    s11_val = self.app.s11[idx]
                    point, = ax.plot([s11_val.real], [s11_val.imag],
                                     marker='o', color="red", alpha=1.0, picker=5)
                    cidp = fig.canvas.mpl_connect("button_press_event", self.on_press)
                    cidm = fig.canvas.mpl_connect("motion_notify_event", self.on_motion)
                    cidr = fig.canvas.mpl_connect("button_release_event", self.on_release)
                    self.plots_data[ax] = {"point": point, "cids": (cidp, cidm, cidr), "texts": []}
        self.app.update_mark_annotation(self, ax)

    def remove_from_axis(self, ax):
        if ax not in self.plots_data:
            return
        data = self.plots_data[ax]
        try:
            if "line" in data:
                data["line"].remove()
            if "point" in data:
                data["point"].remove()
            for txt in data["texts"]:
                txt.remove()
        except Exception:
            pass
        data["texts"].clear()
        fig = ax.figure
        cidp, cidm, cidr = data["cids"]
        fig.canvas.mpl_disconnect(cidp)
        fig.canvas.mpl_disconnect(cidm)
        fig.canvas.mpl_disconnect(cidr)
        del self.plots_data[ax]

    def remove_all_axes(self):
        for ax in list(self.plots_data.keys()):
            self.remove_from_axis(ax)

    def on_press(self, event):
        if event.button != 1:
            return
        for ax, data in self.plots_data.items():
            if "line" in data and event.inaxes == ax:
                contains, _ = data["line"].contains(event)
                if contains:
                    self._press_info = (ax, self.x_value, event.xdata)
                    return
        self._press_info = None

    def on_motion(self, event):
        if not self._press_info:
            return
        ax, old_val, old_mouse = self._press_info
        if event.inaxes != ax:
            return
        dx = event.xdata - old_mouse
        self.x_value = old_val + dx
        for axis, pdata in self.plots_data.items():
            if "line" in pdata:
                pdata["line"].set_xdata([self.x_value, self.x_value])
            elif "point" in pdata:
                freq_arr = self.app.freq
                if freq_arr is not None and freq_arr.size > 0 and self.app.s11 is not None:
                    idx = np.argmin(np.abs(freq_arr - self.x_value * 1e6))
                    if 0 <= idx < len(freq_arr):
                        s11_val = self.app.s11[idx]
                        pdata["point"].set_xdata([s11_val.real])
                        pdata["point"].set_ydata([s11_val.imag])
            self.app.update_mark_annotation(self, axis)
            axis.figure.canvas.draw_idle()

    def on_release(self, event):
        self._press_info = None

###############################################################################
# Classe NanoVNAApp – Aplicativo Principal com Interface “Premium”
###############################################################################
class NanoVNAApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("NanoVNA – Aplicativo Completo")
        try:
            self.state('zoomed')
        except Exception:
            self.attributes('-zoomed', True)
        self.geometry("1600x1000")

        # Carrega logo se disponível
        try:
            logo_img = Image.open("logo.png").resize((150,80), Image.ANTIALIAS)
            self.logo_array = np.array(logo_img)
        except Exception:
            self.logo_array = None

        # Atributos do VNA e dados
        self.vna = None
        self.freq = None
        self.s11 = None
        self.s21 = None
        self.streaming = False
        self.stream_thread = None
        self.stream_gen = None
        self.is_calibrated = False

        # Variáveis para manter escala fixa após primeira varredura
        self.first_sweep_done = False
        self.fixed_ylim_sparam = None
        self.fixed_xlim_tdr = None

        # Parâmetros do sweep
        self.sweep_mode = tk.StringVar(value="startstop")
        self.start_freq = tk.DoubleVar(value=700.0)
        self.stop_freq = tk.DoubleVar(value=900.0)
        self.center_freq = tk.DoubleVar(value=800.0)
        self.span_freq = tk.DoubleVar(value=200.0)
        self.points = tk.IntVar(value=101)

        # Opções de traços
        self.show_s11_db = tk.BooleanVar(value=True)
        self.show_s11_phase = tk.BooleanVar(value=False)
        self.show_s21_db = tk.BooleanVar(value=True)
        self.show_s21_phase = tk.BooleanVar(value=False)

        # Interpolação e suavização – slider
        self.interp_points = tk.IntVar(value=101)
        self.smooth_window = tk.IntVar(value=0)

        # Gabarito para sobreposição
        self.freq_gab = None
        self.s11_gab = None
        self.s21_gab = None

        # TDR: usamos apenas velocidade de propagação relativa (VF)
        self.tdr_vf = tk.DoubleVar(value=0.66)
        self.tdr_cable_len = tk.StringVar(value="---")

        # Marcas arrastáveis
        self.draggable_marks = []

        # Widgets do Notebook e gráficos
        self.notebook = None
        self.tab_sparam = None
        self.tab_smith = None
        self.tab_tdr = None
        self.tab_multi = None
        self.tab_markinfo = None

        self.fig_sparam = None
        self.ax_sparam = None
        self.canvas_sparam = None

        self.fig_smith = None
        self.ax_smith = None
        self.canvas_smith = None

        self.fig_tdr = None
        self.ax_tdr = None
        self.canvas_tdr = None

        self.multi_chart_frame = None
        self.fig_multi = []
        self.ax_multi = []
        self.multi_canvases = []

        self.markinfo_tree = None

        # Layout: Sidebar, Área Principal e Status Bar
        self.sidebar = None
        self.main_area = None
        self.status_bar = None

        self.create_interface()
        self.update_status_time()

    ###########################################################################
    # Criação da Interface – Sidebar, Área Principal e Status Bar
    ###########################################################################
    def create_interface(self):
        pw = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        pw.pack(fill=tk.BOTH, expand=True)
        self.sidebar = tk.Frame(pw, width=300, bg="lightgray")
        self.sidebar.pack_propagate(False)
        self.create_sidebar_widgets()
        self.main_area = ttk.Frame(pw)
        self.create_notebook_widgets()
        pw.add(self.sidebar, weight=0)
        pw.add(self.main_area, weight=1)
        self.status_bar = tk.Label(self, text="Status: ---", bd=1, relief=tk.SUNKEN,
                                   anchor=tk.W, fg="white", bg="darkblue")
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    ###########################################################################
    # Criação dos Widgets da Sidebar
    ###########################################################################
    def create_sidebar_widgets(self):
        frm_conn = ttk.LabelFrame(self.sidebar, text="Conexão", padding=5)
        frm_conn.pack(fill=tk.X, padx=5, pady=5)
        ttk.Button(frm_conn, text="Conectar", command=self.connect_vna).pack(fill=tk.X, pady=2)
        ttk.Button(frm_conn, text="Desconectar", command=self.disconnect_vna).pack(fill=tk.X, pady=2)

        frm_sweep = ttk.LabelFrame(self.sidebar, text="Sweep", padding=5)
        frm_sweep.pack(fill=tk.X, padx=5, pady=5)
        rb1 = ttk.Radiobutton(frm_sweep, text="Start/Stop", variable=self.sweep_mode, value="startstop", command=self.on_sweep_mode_change)
        rb2 = ttk.Radiobutton(frm_sweep, text="Center/Span", variable=self.sweep_mode, value="centerspan", command=self.on_sweep_mode_change)
        rb1.grid(row=0, column=0, sticky="w")
        rb2.grid(row=0, column=1, sticky="w")
        ttk.Label(frm_sweep, text="Start (MHz):").grid(row=1, column=0, sticky="e")
        self.start_entry = ttk.Entry(frm_sweep, width=7, textvariable=self.start_freq)
        self.start_entry.grid(row=1, column=1, padx=2)
        ttk.Label(frm_sweep, text="Stop (MHz):").grid(row=2, column=0, sticky="e")
        self.stop_entry = ttk.Entry(frm_sweep, width=7, textvariable=self.stop_freq)
        self.stop_entry.grid(row=2, column=1, padx=2)
        ttk.Label(frm_sweep, text="Center (MHz):").grid(row=3, column=0, sticky="e")
        self.center_entry = ttk.Entry(frm_sweep, width=7, textvariable=self.center_freq, state="disabled")
        self.center_entry.grid(row=3, column=1, padx=2)
        ttk.Label(frm_sweep, text="Span (MHz):").grid(row=4, column=0, sticky="e")
        self.span_entry = ttk.Entry(frm_sweep, width=7, textvariable=self.span_freq, state="disabled")
        self.span_entry.grid(row=4, column=1, padx=2)
        ttk.Label(frm_sweep, text="Points:").grid(row=5, column=0, sticky="e")
        spn_pts = tk.Spinbox(frm_sweep, from_=2, to=2001, increment=1, textvariable=self.points, width=7)
        spn_pts.grid(row=5, column=1, padx=2)
        ttk.Button(frm_sweep, text="Aplicar Sweep", command=self.apply_sweep_params).grid(row=6, column=0, columnspan=2, pady=5)
        ttk.Button(frm_sweep, text="Sweep Único", command=self.do_sweep).grid(row=7, column=0, columnspan=2, pady=2)
        ttk.Button(frm_sweep, text="Iniciar Stream", command=self.start_stream).grid(row=8, column=0, columnspan=2, pady=2)
        ttk.Button(frm_sweep, text="Parar Stream", command=self.stop_stream).grid(row=9, column=0, columnspan=2, pady=2)

        frm_plot = ttk.LabelFrame(self.sidebar, text="Plot Config", padding=5)
        frm_plot.pack(fill=tk.X, padx=5, pady=5)
        ttk.Checkbutton(frm_plot, text="S11 dB", variable=self.show_s11_db, command=self.update_all_plots).pack(anchor="w")
        ttk.Checkbutton(frm_plot, text="S11 Phase", variable=self.show_s11_phase, command=self.update_all_plots).pack(anchor="w")
        ttk.Checkbutton(frm_plot, text="S21 dB", variable=self.show_s21_db, command=self.update_all_plots).pack(anchor="w")
        ttk.Checkbutton(frm_plot, text="S21 Phase", variable=self.show_s21_phase, command=self.update_all_plots).pack(anchor="w")
        ttk.Label(frm_plot, text="Interp Points:").pack(anchor="w")
        frm_interp = tk.Frame(frm_plot)
        frm_interp.pack(fill=tk.X)
        self.entry_interp = ttk.Entry(frm_interp, width=7, textvariable=self.interp_points)
        self.entry_interp.pack(side=tk.LEFT)
        scale_interp = tk.Scale(frm_interp, from_=10, to=2001, orient=tk.HORIZONTAL, variable=self.interp_points,
                                 command=lambda val: (self.entry_interp.delete(0, tk.END), self.entry_interp.insert(0, val)))
        scale_interp.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(frm_plot, text="Smooth Window:").pack(anchor="w")
        frm_smooth = tk.Frame(frm_plot)
        frm_smooth.pack(fill=tk.X)
        self.entry_smooth = ttk.Entry(frm_smooth, width=7, textvariable=self.smooth_window)
        self.entry_smooth.pack(side=tk.LEFT)
        scale_smooth = tk.Scale(frm_smooth, from_=0, to=50, orient=tk.HORIZONTAL, variable=self.smooth_window,
                                command=lambda val: (self.entry_smooth.delete(0, tk.END), self.entry_smooth.insert(0, val)))
        scale_smooth.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(frm_plot, text="Importar Gabarito (SnP)", command=self.import_gabarito).pack(fill=tk.X, pady=5)

        frm_cal = ttk.LabelFrame(self.sidebar, text="Calibração", padding=5)
        frm_cal.pack(fill=tk.X, padx=5, pady=5)
        ttk.Button(frm_cal, text="Carregar Calib (.cal)", command=self.calibration_load_file).pack(fill=tk.X, pady=2)
        ttk.Button(frm_cal, text="Calib Manual", command=self.calibration_manual_start).pack(fill=tk.X, pady=2)
        ttk.Button(frm_cal, text="Calib Automática", command=self.calibration_auto).pack(fill=tk.X, pady=2)
        self.cal_buttons = []
        for txt, cmd in [("Open", lambda: self.calibration_step("open")),
                         ("Short", lambda: self.calibration_step("short")),
                         ("Load", lambda: self.calibration_step("load")),
                         ("Isolation", lambda: self.calibration_step("isolation")),
                         ("Through", lambda: self.calibration_step("through")),
                         ("Finalizar Manual", self.calibration_manual_finish)]:
            btn = ttk.Button(frm_cal, text=txt, command=cmd)
            btn.pack(fill=tk.X, pady=2)
            btn.pack_forget()
            self.cal_buttons.append(btn)

        frm_marks = ttk.LabelFrame(self.sidebar, text="Marcas", padding=5)
        frm_marks.pack(fill=tk.X, padx=5, pady=5)
        ttk.Button(frm_marks, text="Add Mark", command=self.add_mark_center).pack(fill=tk.X, pady=2)
        ttk.Button(frm_marks, text="Remove Mark", command=self.remove_mark).pack(fill=tk.X, pady=2)
        ttk.Button(frm_marks, text="Exportar Marcas", command=self.export_markinfo).pack(fill=tk.X, pady=2)

        frm_tdr = ttk.LabelFrame(self.sidebar, text="TDR", padding=5)
        frm_tdr.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(frm_tdr, text="VF:").grid(row=0, column=0, sticky="e")
        ttk.Entry(frm_tdr, width=7, textvariable=self.tdr_vf).grid(row=0, column=1, padx=2)
        ttk.Button(frm_tdr, text="Calcular TDR", command=self.calculate_tdr).grid(row=1, column=0, columnspan=2, pady=5)
        ttk.Label(frm_tdr, text="Cable Len:").grid(row=2, column=0, sticky="e")
        ttk.Label(frm_tdr, textvariable=self.tdr_cable_len).grid(row=2, column=1, sticky="w")

        frm_export = ttk.LabelFrame(self.sidebar, text="Exportar", padding=5)
        frm_export.pack(fill=tk.X, padx=5, pady=5)
        ttk.Button(frm_export, text="Exportar Imagem S-Param", command=self.export_image_sparam).pack(fill=tk.X, pady=2)
        ttk.Button(frm_export, text="Exportar s2P", command=self.export_touchstone).pack(fill=tk.X, pady=2)

    ###########################################################################
    # Criação dos Widgets do Notebook (áreas de plotagem)
    ###########################################################################
    def create_notebook_widgets(self):
        self.notebook = ttk.Notebook(self.main_area)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        # Aba S-Parameters
        self.tab_sparam = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_sparam, text="S-Parameters")
        self.fig_sparam = plt.Figure(figsize=(8,5), dpi=100, facecolor='black')
        self.ax_sparam = self.fig_sparam.add_subplot(111, facecolor='black')
        self.setup_axes(self.ax_sparam, "S-Parameters", "Freq (MHz)")
        if self.logo_array is not None:
            self.fig_sparam.figimage(self.logo_array,
                                      self.fig_sparam.bbox.xmax - 160,
                                      self.fig_sparam.bbox.ymax - 90, zorder=10)
        self.canvas_sparam = FigureCanvasTkAgg(self.fig_sparam, master=self.tab_sparam)
        self.canvas_sparam.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        # Binding para botão direito
        self.canvas_sparam.get_tk_widget().bind("<Button-3>", self.on_graph_right_click_sparam)

        # Aba Smith Chart
        self.tab_smith = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_smith, text="Smith Chart")
        self.fig_smith = plt.Figure(figsize=(8,5), dpi=100, facecolor='black')
        self.ax_smith = self.fig_smith.add_subplot(111, facecolor='black')
        self.setup_axes(self.ax_smith, "Smith Chart", "")
        if self.logo_array is not None:
            self.fig_smith.figimage(self.logo_array,
                                     self.fig_smith.bbox.xmax - 160,
                                     self.fig_smith.bbox.ymax - 90, zorder=10)
        self.canvas_smith = FigureCanvasTkAgg(self.fig_smith, master=self.tab_smith)
        self.canvas_smith.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.canvas_smith.get_tk_widget().bind("<Button-3>", self.on_graph_right_click_smith)

        # Aba TDR
        self.tab_tdr = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_tdr, text="TDR (ns)")
        self.fig_tdr = plt.Figure(figsize=(8,5), dpi=100, facecolor='black')
        self.ax_tdr = self.fig_tdr.add_subplot(111, facecolor='black')
        self.setup_axes(self.ax_tdr, "TDR", "Tempo (ns)")
        if self.logo_array is not None:
            self.fig_tdr.figimage(self.logo_array,
                                   self.fig_tdr.bbox.xmax - 160,
                                   self.fig_tdr.bbox.ymax - 90, zorder=10)
        self.canvas_tdr = FigureCanvasTkAgg(self.fig_tdr, master=self.tab_tdr)
        self.canvas_tdr.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.canvas_tdr.get_tk_widget().bind("<Button-3>", self.on_graph_right_click_tdr)

        # Aba Multi-Chart: 6 gráficos em grid
        self.tab_multi = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_multi, text="Multi Chart")
        self.multi_chart_frame = tk.Frame(self.tab_multi)
        self.multi_chart_frame.pack(fill=tk.BOTH, expand=True)
        titles = ["S11 dB", "S21 dB", "S11 Phase", "S21 Phase", "Smith (S11)", "TDR"]
        rows, cols = 2, 3
        for i in range(6):
            fig = plt.Figure(figsize=(4,3), dpi=100, facecolor='black')
            ax = fig.add_subplot(111, facecolor='black')
            self.setup_axes(ax, titles[i], "")
            if self.logo_array is not None:
                fig.figimage(self.logo_array,
                             fig.bbox.xmax - 160,
                             fig.bbox.ymax - 90, zorder=10)
            canvas = FigureCanvasTkAgg(fig, master=self.multi_chart_frame)
            # Binding para botão direito genérico
            canvas.get_tk_widget().bind("<Button-3>", self.on_graph_right_click_generic)
            self.fig_multi.append(fig)
            self.ax_multi.append(ax)
            self.multi_canvases.append(canvas)
        for i, canvas in enumerate(self.multi_canvases):
            r, c = i // cols, i % cols
            canvas.get_tk_widget().grid(row=r, column=c, sticky="nsew", padx=2, pady=2)
        for r in range(rows):
            self.multi_chart_frame.grid_rowconfigure(r, weight=1)
        for c in range(cols):
            self.multi_chart_frame.grid_columnconfigure(c, weight=1)

        # Aba Mark Info
        self.tab_markinfo = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_markinfo, text="Mark Info")
        lbl = ttk.Label(self.tab_markinfo, text="Informações das Marcas", font=("Arial", 12, "bold"))
        lbl.pack(pady=5)
        cols_info = ("Mark", "Freq(MHz)", "S11(dB)", "S11(°)", "S21(dB)", "S21(°)", "VSWR", "R(Ω)", "X(Ω)", "Extra")
        self.markinfo_tree = ttk.Treeview(self.tab_markinfo, columns=cols_info, show="headings", height=15)
        for col in cols_info:
            self.markinfo_tree.heading(col, text=col)
            self.markinfo_tree.column(col, width=90, anchor="center")
        self.markinfo_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        ttk.Button(self.tab_markinfo, text="Exportar Mark Info", command=self.export_markinfo).pack(pady=5)

    ###########################################################################
    # Configuração Comum dos Eixos dos Gráficos
    ###########################################################################
    def setup_axes(self, ax, title, xlabel):
        ax.set_title(title, color='white')
        ax.set_facecolor('black')
        ax.grid(True, color='white', alpha=0.3)
        for sp in ['bottom','top','left','right']:
            ax.spines[sp].set_color('white')
        ax.tick_params(axis='x', colors='white')
        ax.tick_params(axis='y', colors='white')
        ax.set_xlabel(xlabel, color='white')

    ###########################################################################
    # Atualiza Todos os Gráficos
    ###########################################################################
    def update_all_plots(self):
        self.update_sparam_plot()
        self.update_smith_plot()
        self.update_tdr_plot()
        self.update_multi_chart()
        self.update_markinfo_tab()

    ###########################################################################
    # Atualização do Gráfico S‑Parameters
    ###########################################################################
    def update_sparam_plot(self):
        self.ax_sparam.clear()
        self.setup_axes(self.ax_sparam, "S-Parameters", "Freq (MHz)")
        if self.freq is not None and self.freq.size > 0:
            f_interp, s11_interp, s21_interp = self.apply_advanced_functions(self.freq, self.s11, self.s21)
            freq_mhz_interp = f_interp / 1e6
            if self.show_s11_db.get():
                db_s11 = 20 * np.log10(np.abs(s11_interp) + 1e-15)
                self.ax_sparam.plot(freq_mhz_interp, db_s11, color='yellow', label='S11(dB)')
            if self.show_s11_phase.get():
                ph_s11 = np.angle(s11_interp, deg=True)
                self.ax_sparam.plot(freq_mhz_interp, ph_s11, color='orange', label='S11(°)')
            if self.show_s21_db.get():
                db_s21 = 20 * np.log10(np.abs(s21_interp) + 1e-15)
                self.ax_sparam.plot(freq_mhz_interp, db_s21, color='green', label='S21(dB)')
            if self.show_s21_phase.get():
                ph_s21 = np.angle(s21_interp, deg=True)
                self.ax_sparam.plot(freq_mhz_interp, ph_s21, color='cyan', label='S21(°)')
            if self.freq_gab is not None and self.freq_gab.size > 0 and self.s11_gab is not None:
                freq_mhz_g = self.freq_gab / 1e6
                db_s11g = 20 * np.log10(np.abs(self.s11_gab) + 1e-15)
                self.ax_sparam.plot(freq_mhz_g, db_s11g, color='white', linestyle='--', label='S11_gab(dB)')
                if self.s21_gab is not None:
                    db_s21g = 20 * np.log10(np.abs(self.s21_gab) + 1e-15)
                    self.ax_sparam.plot(freq_mhz_g, db_s21g, color='gray', linestyle='--', label='S21_gab(dB)')
            self.ax_sparam.legend(facecolor='black', edgecolor='white', labelcolor='white')
        for mk in self.draggable_marks:
            mk.remove_from_axis(self.ax_sparam)
            mk.ensure_line_on_axis(self.ax_sparam, "cartesian")
        if not self.first_sweep_done and self.freq is not None and self.freq.size > 0:
            self.ax_sparam.relim()
            self.ax_sparam.autoscale_view()
            self.fixed_ylim_sparam = self.ax_sparam.get_ylim()
            self.first_sweep_done = True
        elif self.fixed_ylim_sparam is not None:
            self.ax_sparam.set_ylim(self.fixed_ylim_sparam)
        self.canvas_sparam.draw()

    ###########################################################################
    # Atualização do Gráfico Smith
    ###########################################################################
    def update_smith_plot(self):
        self.ax_smith.clear()
        self.setup_axes(self.ax_smith, "Smith Chart", "")
        if self.freq is not None and self.freq.size > 0:
            npts = len(self.freq)
            s11_array = self.s11.reshape(npts, 1, 1)
            fq_obj = rf.Frequency(self.freq, unit='hz')
            net = rf.Network(frequency=fq_obj, s=s11_array)
            net.plot_s_smith(ax=self.ax_smith, marker='.', markersize=4, color='yellow')
        for mk in self.draggable_marks:
            mk.remove_from_axis(self.ax_smith)
            mk.ensure_line_on_axis(self.ax_smith, "smith")
        self.canvas_smith.draw()

    ###########################################################################
    # Atualização do Gráfico TDR
    ###########################################################################
    def update_tdr_plot(self):
        self.ax_tdr.clear()
        self.setup_axes(self.ax_tdr, "TDR", "Tempo (ns)")
        if self.freq is not None and self.freq.size > 0:
            f_interp, s11_interp, _ = self.apply_advanced_functions(self.freq, self.s11, self.s21)
            t_axis, t_resp = self.compute_tdr(f_interp, s11_interp)
            t_axis_ns = t_axis * 1e9
            self.ax_tdr.plot(t_axis_ns, np.abs(t_resp), color='cyan')
        self.canvas_tdr.draw()

    ###########################################################################
    # Atualização do Multi‑Chart (6 gráficos em grid)
    ###########################################################################
    def update_multi_chart(self):
        if self.freq is None or self.freq.size < 2:
            for i in range(6):
                self.ax_multi[i].clear()
                self.setup_axes(self.ax_multi[i], f"Chart {i+1}", "")
                self.multi_canvases[i].draw()
            return
        freq_mhz = self.freq / 1e6
        s11_abs = np.abs(self.s11)
        s21_abs = np.abs(self.s21)
        s11_ph = np.angle(self.s11, deg=True)
        s21_ph = np.angle(self.s21, deg=True)
        f_interp, s11_interp, s21_interp = self.apply_advanced_functions(self.freq, self.s11, self.s21)
        t_axis, t_resp = self.compute_tdr(f_interp, s11_interp)
        t_axis_ns = t_axis * 1e9
        self.ax_multi[0].clear()
        self.setup_axes(self.ax_multi[0], "S11 dB", "")
        self.ax_multi[0].plot(freq_mhz, 20*np.log10(s11_abs+1e-15), color='yellow')
        self.ax_multi[1].clear()
        self.setup_axes(self.ax_multi[1], "S21 dB", "")
        self.ax_multi[1].plot(freq_mhz, 20*np.log10(s21_abs+1e-15), color='green')
        self.ax_multi[2].clear()
        self.setup_axes(self.ax_multi[2], "S11 Phase", "")
        self.ax_multi[2].plot(freq_mhz, s11_ph, color='orange')
        self.ax_multi[3].clear()
        self.setup_axes(self.ax_multi[3], "S21 Phase", "")
        self.ax_multi[3].plot(freq_mhz, s21_ph, color='cyan')
        self.ax_multi[4].clear()
        self.setup_axes(self.ax_multi[4], "Smith (S11)", "")
        npts = len(self.freq)
        s11_array = self.s11.reshape(npts, 1, 1)
        fq_obj = rf.Frequency(self.freq, unit='hz')
        net = rf.Network(frequency=fq_obj, s=s11_array)
        net.plot_s_smith(ax=self.ax_multi[4], marker='.', markersize=4, color='magenta')
        self.ax_multi[5].clear()
        self.setup_axes(self.ax_multi[5], "TDR", "Tempo (ns)")
        self.ax_multi[5].plot(t_axis_ns, np.abs(t_resp), color='white')
        for i in range(6):
            self.multi_canvases[i].draw()

    ###########################################################################
    # Atualiza a Aba de Informações das Marcas
    ###########################################################################
    def update_markinfo_tab(self):
        for item in self.markinfo_tree.get_children():
            self.markinfo_tree.delete(item)
        if self.freq is None or self.freq.size < 2:
            return
        for i, mk in enumerate(self.draggable_marks):
            idx = np.argmin(np.abs(self.freq - mk.x_value * 1e6))
            freq_mhz = self.freq[idx] / 1e6
            s11_val = self.s11[idx]
            s21_val = self.s21[idx]
            s11_db = 20 * np.log10(np.abs(s11_val) + 1e-15)
            s11_ph = np.angle(s11_val, deg=True)
            s21_db = 20 * np.log10(np.abs(s21_val) + 1e-15)
            s21_ph = np.angle(s21_val, deg=True)
            mag_s11 = np.abs(s11_val)
            vswr = (1 + mag_s11) / (1 - mag_s11) if mag_s11 < 1 else float("inf")
            z0 = 50.0
            try:
                z_val = z0 * (1 + s11_val) / (1 - s11_val)
            except ZeroDivisionError:
                z_val = float("inf")
            r_val = z_val.real
            x_val = z_val.imag
            omega = 2 * np.pi * (freq_mhz * 1e6)
            extra_txt = ""
            if abs(x_val) > 1e-9 and freq_mhz > 0:
                if x_val > 0:
                    L_val = x_val / omega
                    extra_txt = f"L={L_val*1e9:.2f} nH"
                else:
                    C_val = -1 / (omega * x_val)
                    extra_txt = f"C={C_val*1e12:.2f} pF"
            vals = (f"{i+1}", f"{freq_mhz:.3f}", f"{s11_db:.2f}", f"{s11_ph:.1f}",
                    f"{s21_db:.2f}", f"{s21_ph:.1f}", f"{vswr:.2f}", f"{r_val:.1f}",
                    f"{x_val:.1f}", extra_txt)
            self.markinfo_tree.insert("", "end", values=vals)

    ###########################################################################
    # Função de Interpolação e Suavização
    ###########################################################################
    def apply_advanced_functions(self, freq_hz, s11_data, s21_data):
        n_new = self.interp_points.get()
        if n_new > len(freq_hz):
            fmin = freq_hz[0]
            fmax = freq_hz[-1]
            freq_lin = np.linspace(fmin, fmax, n_new)
            interp_s11 = interp1d(freq_hz, s11_data, kind='cubic', fill_value='extrapolate')
            s11_interp = interp_s11(freq_lin)
            interp_s21 = interp1d(freq_hz, s21_data, kind='cubic', fill_value='extrapolate')
            s21_interp = interp_s21(freq_lin)
        else:
            freq_lin = freq_hz
            s11_interp = s11_data
            s21_interp = s21_data
        w = self.smooth_window.get()
        if w > 1:
            s11_interp = self.moving_average_complex(s11_interp, w)
            s21_interp = self.moving_average_complex(s21_interp, w)
        return freq_lin, s11_interp, s21_interp

    def moving_average_complex(self, arr, w):
        real_part = np.convolve(arr.real, np.ones(w)/w, mode='same')
        imag_part = np.convolve(arr.imag, np.ones(w)/w, mode='same')
        return real_part + 1j*imag_part

    ###########################################################################
    # Função para calcular TDR
    ###########################################################################
    def compute_tdr(self, freq_hz, sparam, num_points=1024):
        if len(freq_hz) < 2:
            return np.array([0]), np.array([0])
        try:
            fmin = np.min(freq_hz)
            fmax = np.max(freq_hz)
            interp_func = interp1d(freq_hz, sparam, kind='cubic', fill_value='extrapolate')
        except Exception:
            return np.array([0]), np.array([0])
        freq_lin = np.linspace(fmin, fmax, num_points)
        sparam_interp = interp_func(freq_lin)
        t_dom = np.fft.ifft(sparam_interp)
        win = windows.kaiser(num_points, beta=5)
        t_resp = t_dom * win
        df = (fmax - fmin) / (num_points - 1)
        dt = 1.0 / df if df > 0 else 0
        t_axis = np.arange(num_points) * dt
        return t_axis, t_resp

    ###########################################################################
    # Menus de clique direito
    ###########################################################################
    def on_graph_right_click_sparam(self, event):
        if event.num == 3:
            menu = tk.Menu(self, tearoff=0)
            menu.add_command(label="Exportar Imagem", command=self.export_image_sparam)
            menu.add_command(label="Exportar s2P", command=self.export_touchstone)
            menu.add_command(label="Aplicar Escala Y", command=self.apply_y_scale_sparam)
            menu.tk_popup(event.x_root, event.y_root)

    def on_graph_right_click_tdr(self, event):
        if event.num == 3:
            menu = tk.Menu(self, tearoff=0)
            menu.add_command(label="Exportar Imagem", command=self.export_image_tdr)
            menu.add_command(label="Aplicar Escala X", command=self.apply_x_scale_tdr)
            menu.tk_popup(event.x_root, event.y_root)

    def on_graph_right_click_smith(self, event):
        if event.num == 3:
            menu = tk.Menu(self, tearoff=0)
            menu.add_command(label="Exportar Imagem", command=self.export_image_smith)
            menu.tk_popup(event.x_root, event.y_root)

    def on_graph_right_click_generic(self, event):
        if event.num == 3:
            menu = tk.Menu(self, tearoff=0)
            menu.add_command(label="Exportar Imagem", command=lambda: messagebox.showinfo("Exportar", "Função não implementada"))
            menu.tk_popup(event.x_root, event.y_root)

    ###########################################################################
    # Funções para aplicar escalas personalizadas
    ###########################################################################
    def apply_y_scale_sparam(self):
        ymin = simpledialog.askfloat("Escala Y", "Valor mínimo do eixo Y:")
        ymax = simpledialog.askfloat("Escala Y", "Valor máximo do eixo Y:")
        if ymin is not None and ymax is not None:
            self.fixed_ylim_sparam = (ymin, ymax)
            self.ax_sparam.set_ylim(self.fixed_ylim_sparam)
            self.canvas_sparam.draw()

    def apply_x_scale_tdr(self):
        xmin = simpledialog.askfloat("Escala X", "Valor mínimo (ns):")
        xmax = simpledialog.askfloat("Escala X", "Valor máximo (ns):")
        if xmin is not None and xmax is not None:
            self.ax_tdr.set_xlim(xmin, xmax)
            self.canvas_tdr.draw()

    ###########################################################################
    # Funções de Importação/Exportação
    ###########################################################################
    def import_gabarito(self):
        path = filedialog.askopenfilename(filetypes=[("Touchstone", "*.s1p *.s2p"), ("All", "*.*")])
        if not path:
            return
        try:
            net = rf.Network(path)
            self.freq_gab = net.f
            if net.s.shape[1] == 1:
                self.s11_gab = net.s[:, 0, 0]
                self.s21_gab = None
            else:
                self.s11_gab = net.s[:, 0, 0]
                self.s21_gab = net.s[:, 1, 0]
            messagebox.showinfo("Touchstone", f"Carregado {len(self.freq_gab)} pts de {os.path.basename(path)}.")
            self.update_all_plots()
        except Exception as ex:
            messagebox.showerror("Erro", f"Falha ao importar Touchstone: {ex}")

    def export_touchstone(self):
        if self.freq is None or self.s11 is None:
            messagebox.showwarning("Aviso", "Nada para exportar.")
            return
        fname = filedialog.asksaveasfilename(defaultextension=".s2p",
                                             filetypes=[("Touchstone", "*.s2p"), ("All", "*.*")])
        if not fname:
            return
        try:
            npts = len(self.freq)
            S = np.zeros((npts, 2, 2), dtype=complex)
            S[:, 0, 0] = self.s11
            S[:, 1, 0] = self.s21
            S[:, 0, 1] = self.s21
            S[:, 1, 1] = 0.0
            fq = rf.Frequency(self.freq, unit='hz')
            net = rf.Network(frequency=fq, s=S)
            net.write_touchstone(fname)
            messagebox.showinfo("Touchstone", f"Exportado para {fname}.")
        except Exception as ex:
            messagebox.showerror("Erro", f"Falha ao exportar: {ex}")

    def export_image_sparam(self):
        fname = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG", "*.png")])
        if not fname:
            return
        try:
            self.fig_sparam.savefig(fname, facecolor=self.fig_sparam.get_facecolor())
            messagebox.showinfo("Exportar Imagem", f"Imagem S-Param salva em {fname}")
        except Exception as ex:
            messagebox.showerror("Erro", f"Falha ao exportar imagem: {ex}")

    def export_image_smith(self):
        fname = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG", "*.png")])
        if not fname:
            return
        try:
            self.fig_smith.savefig(fname, facecolor=self.fig_smith.get_facecolor())
            messagebox.showinfo("Exportar Imagem", f"Imagem Smith salva em {fname}")
        except Exception as ex:
            messagebox.showerror("Erro", f"Falha ao exportar imagem: {ex}")

    def export_image_tdr(self):
        fname = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG", "*.png")])
        if not fname:
            return
        try:
            self.fig_tdr.savefig(fname, facecolor=self.fig_tdr.get_facecolor())
            messagebox.showinfo("Exportar Imagem", f"Imagem TDR salva em {fname}")
        except Exception as ex:
            messagebox.showerror("Erro", f"Falha ao exportar imagem: {ex}")

    def export_markinfo(self):
        if not self.draggable_marks:
            messagebox.showwarning("Exportar Marcas", "Nenhuma marca para exportar.")
            return
        fname = filedialog.asksaveasfilename(defaultextension=".csv",
                                             filetypes=[("CSV", "*.csv"), ("TXT", "*.txt"), ("XLS", "*.xls"), ("All", "*.*")])
        if not fname:
            return
        ext = os.path.splitext(fname)[1].lower()
        lines = []
        header = "Mark#,Freq(MHz),S11(dB),S11(°),S21(dB),S21(°),VSWR,R(Ω),X(Ω),Extra"
        lines.append(header)
        for item in self.markinfo_tree.get_children():
            vals = self.markinfo_tree.item(item)["values"]
            line = ",".join(str(v) for v in vals)
            lines.append(line)
        try:
            if ext in [".csv", ".txt"]:
                with open(fname, "w", encoding="utf-8") as f:
                    f.write("\n".join(lines))
                messagebox.showinfo("Exportar Marcas", f"Arquivo salvo em {fname}")
            elif ext == ".xls":
                wb = Workbook()
                ws = wb.active
                for r in lines:
                    ws.append(r.split(","))
                wb.save(fname)
                messagebox.showinfo("Exportar Marcas", f"Arquivo XLS salvo em {fname}")
            else:
                with open(fname, "w", encoding="utf-8") as f:
                    f.write("\n".join(lines))
                messagebox.showinfo("Exportar Marcas", f"Arquivo salvo em {fname}")
        except Exception as ex:
            messagebox.showerror("Erro", f"Falha ao exportar marcas: {ex}")

    ###########################################################################
    # Funções de Marcas: Adicionar/Remover
    ###########################################################################
    def add_mark_center(self):
        if self.freq is not None and self.freq.size > 0:
            center_mhz = (self.freq[0]/1e6 + self.freq[-1]/1e6) / 2
        else:
            center_mhz = 800.0
        new_mark = DraggableMark(center_mhz, self, domain="freq")
        self.draggable_marks.append(new_mark)
        self.update_all_plots()

    def remove_mark(self):
        if self.draggable_marks:
            mark = self.draggable_marks.pop()
            mark.remove_all_axes()
            self.update_all_plots()
        else:
            messagebox.showinfo("Marcas", "Nenhuma marca para remover.")

    ###########################################################################
    # Conexão com o NanoVNA
    ###########################################################################
    def connect_vna(self):
        try:
            self.vna = VNA()
            if not self.vna.is_connected():
                self.vna = None
                messagebox.showerror("Erro", "NanoVNA não encontrado.")
            else:
                messagebox.showinfo("Conexão", "NanoVNA conectado.")
        except Exception as e:
            messagebox.showerror("Erro", f"Falha ao conectar: {e}")
        self.update_status_bar()

    def disconnect_vna(self):
        if self.vna:
            try:
                self.vna.kill()
                self.vna = None
                messagebox.showinfo("Desconexão", "Desconectado do NanoVNA.")
            except Exception as e:
                messagebox.showerror("Erro", f"Falha ao desconectar: {e}")
        else:
            messagebox.showwarning("Aviso", "Nenhum VNA conectado.")
        self.update_status_bar()

    def on_sweep_mode_change(self):
        if self.sweep_mode.get() == "startstop":
            self.start_entry.config(state="normal")
            self.stop_entry.config(state="normal")
            self.center_entry.config(state="disabled")
            self.span_entry.config(state="disabled")
        else:
            self.start_entry.config(state="disabled")
            self.stop_entry.config(state="disabled")
            self.center_entry.config(state="normal")
            self.span_entry.config(state="normal")

    ###########################################################################
    # Calibração: Carregar, Manual e Automática
    ###########################################################################
    def calibration_load_file(self):
        if not self.vna:
            messagebox.showwarning("Aviso", "VNA não conectado.")
            return
        path = filedialog.askopenfilename(filetypes=[("Calibração", "*.cal"), ("All", "*.*")])
        if not path:
            return
        try:
            self.vna.load_calibration(path)
            self.is_calibrated = True
            messagebox.showinfo("Calibração", f"Calib carregada: {path}")
        except Exception as e:
            messagebox.showerror("Erro", f"Falha ao carregar calib: {e}")
        self.update_status_bar()

    def calibration_manual_start(self):
        if not self.vna or not self.vna.is_connected():
            messagebox.showwarning("Aviso", "NanoVNA não conectado.")
            return
        mode = self.sweep_mode.get()
        if mode == "startstop":
            st = self.start_freq.get()
            sp = self.stop_freq.get()
        else:
            c = self.center_freq.get()
            s = self.span_freq.get()
            st = c - s / 2
            sp = c + s / 2
        resp = messagebox.askyesno("Calib Manual", f"Faixa {st:.1f}-{sp:.1f} MHz. Confirmar?")
        if not resp:
            return
        self.apply_sweep_params()
        for btn in self.cal_buttons:
            btn.pack(fill=tk.X, pady=2)

    def calibration_step(self, step_name):
        if not self.vna:
            return
        try:
            self.vna.sweep()
            self.vna.calibration_step(step_name)
            messagebox.showinfo("Calibração", f"Passo '{step_name}' concluído.")
        except Exception as e:
            messagebox.showerror("Erro Calib", f"Falha no passo {step_name}: {e}")

    def calibration_manual_finish(self):
        if not self.vna:
            return
        try:
            self.vna.calibrate()
            self.is_calibrated = True
            for btn in self.cal_buttons:
                btn.pack_forget()
            mode = self.sweep_mode.get()
            if mode == "startstop":
                st = self.start_freq.get()
                sp = self.stop_freq.get()
            else:
                c = self.center_freq.get()
                s = self.span_freq.get()
                st = c - s / 2
                sp = c + s / 2
            cal_file = f"calibration_{int(st)}_{int(sp)}.cal"
            self.vna.save_calibration(cal_file)
            messagebox.showinfo("Calibração", f"Calib finalizada e salva em {cal_file}.")
        except Exception as e:
            messagebox.showerror("Erro", f"Falha ao finalizar calib: {e}")
        self.update_status_bar()

    def calibration_auto(self):
        if not self.vna or not self.vna.is_connected():
            messagebox.showwarning("Aviso", "VNA não conectado.")
            return
        mode = self.sweep_mode.get()
        if mode == "startstop":
            st = self.start_freq.get()
            sp = self.stop_freq.get()
        else:
            c = self.center_freq.get()
            s = self.span_freq.get()
            st = c - s / 2
            sp = c + s / 2
        resp = messagebox.askyesno("Calib Automática", f"Faixa {st:.1f}-{sp:.1f} MHz. Confirmar?")
        if not resp:
            return
        self.apply_sweep_params()
        steps = [
            ("open", "Conecte OPEN na porta 1"),
            ("short", "Conecte SHORT na porta 1"),
            ("load", "Conecte LOAD na porta 1"),
            ("isolation", "Conecte LOAD na porta 2"),
            ("through", "Conecte cabo entre porta 1 e 2"),
        ]
        try:
            for step_cmd, msg in steps:
                if not messagebox.askokcancel("Calib Automática", f"{msg}\nClique OK para prosseguir"):
                    return
                self.vna.sweep()
                self.vna.calibration_step(step_cmd)
            self.vna.calibrate()
            self.is_calibrated = True
            cal_file = f"calibration_{int(st)}_{int(sp)}.cal"
            self.vna.save_calibration(cal_file)
            messagebox.showinfo("Calibração", f"Auto concluída e salva em {cal_file}.")
        except Exception as e:
            messagebox.showerror("Erro", f"Falha na calib auto: {e}")
        self.update_status_bar()

    ###########################################################################
    # Função para calcular TDR e estimar o comprimento do cabo
    ###########################################################################
    def calculate_tdr(self):
        if not self.vna or not self.vna.is_connected():
            messagebox.showwarning("Aviso", "VNA não conectado.")
            return
        try:
            speed_of_light = 299792458  # m/s
            self.apply_sweep_params()
            s11, s21, freqs = self.vna.sweep()
            s11 = np.array(s11, dtype=complex)
            freqs = np.array(freqs, dtype=float)
            time_domain = np.fft.ifft(s11)
            df = freqs[1] - freqs[0] if len(freqs) > 1 else 1
            time_vals = np.fft.fftfreq(len(freqs), d=df)
            mask = time_vals >= 0
            time_pos = time_vals[mask]
            td_pos = time_domain[mask]
            peak_idx = np.argmax(np.abs(td_pos))
            peak_time = time_pos[peak_idx]
            velocity_factor = self.tdr_vf.get()
            cable_length = speed_of_light * velocity_factor * peak_time / 2.0
            self.tdr_cable_len.set(f"{cable_length:.2f} m")
            self.ax_tdr.clear()
            self.setup_axes(self.ax_tdr, "TDR", "Tempo (ns)")
            self.ax_tdr.plot(time_pos * 1e9, np.abs(td_pos), color='cyan')
            self.canvas_tdr.draw()
            messagebox.showinfo("TDR", f"Cabo ~ {cable_length:.2f} m (pico em {peak_time:.2e} s)")
        except Exception as e:
            messagebox.showerror("Erro TDR", f"{e}")

    ###########################################################################
    # Aplica os parâmetros de sweep no VNA
    ###########################################################################
    def apply_sweep_params(self):
        if self.vna and self.vna.is_connected():
            pts = self.points.get()
            if self.sweep_mode.get() == "startstop":
                st = self.start_freq.get()
                sp = self.stop_freq.get()
            else:
                c = self.center_freq.get()
                s = self.span_freq.get()
                st = c - s / 2
                sp = c + s / 2
            self.vna.set_sweep(st * 1e6, sp * 1e6, pts)
            messagebox.showinfo("Sweep", "Parâmetros de sweep aplicados ao VNA.")
        else:
            messagebox.showwarning("Aviso", "VNA não conectado.")

    ###########################################################################
    # Executa um Sweep Único
    ###########################################################################
    def do_sweep(self):
        if not self.vna or not self.vna.is_connected():
            messagebox.showwarning("Aviso", "NanoVNA não conectado.")
            return
        try:
            self.apply_sweep_params()
            s11, s21, freq = self.vna.sweep()
            self.s11 = np.array(s11, dtype=complex)
            self.s21 = np.array(s21, dtype=complex)
            self.freq = np.array(freq, dtype=float)
            messagebox.showinfo("Sweep", f"Sweep concluído com {len(freq)} pontos.")
            self.update_all_plots()
            if not self.first_sweep_done:
                self.ax_sparam.relim()
                self.ax_sparam.autoscale_view()
                self.fixed_ylim_sparam = self.ax_sparam.get_ylim()
                self.first_sweep_done = True
        except Exception as e:
            messagebox.showerror("Erro", f"Falha no sweep: {e}")
        self.update_status_bar()

    ###########################################################################
    # Streaming – Atualiza os gráficos em tempo real
    ###########################################################################
    def _stream_loop(self):
        while self.streaming:
            try:
                s11, s21, freq = next(self.stream_gen)
                self.s11 = np.array(s11, dtype=complex)
                self.s21 = np.array(s21, dtype=complex)
                self.freq = np.array(freq, dtype=float)
                self.after(0, self.update_all_plots)
            except StopIteration:
                break
            except Exception as ex:
                print("Erro no streaming:", ex)
                break
        self.streaming = False
        self.after(0, self.update_status_bar)

    def start_stream(self):
        if not self.vna:
            messagebox.showwarning("Aviso", "VNA não conectado.")
            return
        if self.streaming:
            messagebox.showinfo("Stream", "Streaming já ativo.")
            return
        try:
            self.apply_sweep_params()
            self.stream_gen = self.vna.stream()
            self.streaming = True
            self.stream_thread = threading.Thread(target=self._stream_loop, daemon=True)
            self.stream_thread.start()
            messagebox.showinfo("Streaming", "Streaming iniciado.")
        except Exception as e:
            messagebox.showerror("Erro", f"Falha ao iniciar streaming: {e}")
        self.update_status_bar()

    def stop_stream(self):
        if self.streaming:
            self.streaming = False
            if self.stream_thread:
                self.stream_thread.join(timeout=1)
            self.stream_thread = None
            self.stream_gen = None
            messagebox.showinfo("Streaming", "Streaming parado.")
        else:
            messagebox.showwarning("Aviso", "Streaming não ativo.")
        self.update_status_bar()

    ###########################################################################
    # Atualiza a Barra de Status
    ###########################################################################
    def update_status_bar(self):
        conn_str = "Conectado" if (self.vna and self.vna.is_connected()) else "Desconectado"
        swp_str = "Streaming" if self.streaming else "Idle"
        cal_str = "Calibrado" if self.is_calibrated else "Não Calib"
        now_str = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        status_txt = f"[{conn_str}] | [{swp_str}] | [{cal_str}] | {now_str}"
        self.status_bar.config(text=status_txt)

    def update_status_time(self):
        self.update_status_bar()
        self.after(1000, self.update_status_time)

    ###########################################################################
    # Atualiza as anotações das marcas em um gráfico
    ###########################################################################
    def update_mark_annotation(self, mark, ax):
        if self.freq is None or self.freq.size < 2:
            return
        data = mark.plots_data[ax]
        for txt in data["texts"]:
            try:
                txt.remove()
            except Exception:
                pass
        data["texts"].clear()
        idx = np.argmin(np.abs(self.freq - mark.x_value * 1e6))
        freq_mhz = self.freq[idx] / 1e6
        s11_val = self.s11[idx]
        s21_val = self.s21[idx]
        if ax == self.ax_smith:
            mag = np.abs(s11_val)
            phase_deg = np.angle(s11_val, deg=True)
            vswr = (1 + mag) / (1 - mag) if mag < 1 else float('inf')
            z0 = 50
            try:
                z_val = z0 * (1 + s11_val) / (1 - s11_val)
            except ZeroDivisionError:
                z_val = float('inf')
            info = (f"Freq: {freq_mhz:.2f} MHz\n"
                    f"|Γ|= {mag:.3f}, ∠= {phase_deg:.1f}°\n"
                    f"Z= {z_val.real:.1f}+j{z_val.imag:.1f}, VSWR= {vswr:.2f}")
            t = ax.text(0.02, 0.9, info, transform=ax.transAxes, color="white",
                        bbox=dict(facecolor='black', alpha=0.7))
            data["texts"].append(t)
        else:
            db11 = 20 * np.log10(np.abs(s11_val) + 1e-15)
            ph11 = np.angle(s11_val, deg=True)
            db21 = 20 * np.log10(np.abs(s21_val) + 1e-15)
            ph21 = np.angle(s21_val, deg=True)
            ylim = ax.get_ylim()
            offset = 0.03 * (ylim[1] - ylim[0])
            y_pos = ylim[1] - offset
            txt_str = (f"Freq: {freq_mhz:.2f} MHz\n"
                       f"S11: {db11:.2f} dB, {ph11:.1f}°\n"
                       f"S21: {db21:.2f} dB, {ph21:.1f}°")
            t = ax.text(mark.x_value, y_pos, txt_str, color="white", ha="center", va="top",
                        bbox=dict(facecolor='black', alpha=0.7))
            data["texts"].append(t)
        ax.figure.canvas.draw_idle()

    ###########################################################################
    # Funções de Exportação
    ###########################################################################
    def export_image_sparam(self):
        fname = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG", "*.png")])
        if not fname:
            return
        try:
            self.fig_sparam.savefig(fname, facecolor=self.fig_sparam.get_facecolor())
            messagebox.showinfo("Exportar Imagem", f"Imagem S-Param salva em {fname}")
        except Exception as ex:
            messagebox.showerror("Erro", f"Falha ao exportar imagem: {ex}")

    def export_image_smith(self):
        fname = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG", "*.png")])
        if not fname:
            return
        try:
            self.fig_smith.savefig(fname, facecolor=self.fig_smith.get_facecolor())
            messagebox.showinfo("Exportar Imagem", f"Imagem Smith salva em {fname}")
        except Exception as ex:
            messagebox.showerror("Erro", f"Falha ao exportar imagem: {ex}")

    def export_image_tdr(self):
        fname = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG", "*.png")])
        if not fname:
            return
        try:
            self.fig_tdr.savefig(fname, facecolor=self.fig_tdr.get_facecolor())
            messagebox.showinfo("Exportar Imagem", f"Imagem TDR salva em {fname}")
        except Exception as ex:
            messagebox.showerror("Erro", f"Falha ao exportar imagem: {ex}")

    def export_touchstone(self):
        if self.freq is None or self.s11 is None:
            messagebox.showwarning("Aviso", "Nada para exportar.")
            return
        fname = filedialog.asksaveasfilename(defaultextension=".s2p",
                                             filetypes=[("Touchstone", "*.s2p"), ("All", "*.*")])
        if not fname:
            return
        try:
            npts = len(self.freq)
            S = np.zeros((npts, 2, 2), dtype=complex)
            S[:, 0, 0] = self.s11
            S[:, 1, 0] = self.s21
            S[:, 0, 1] = self.s21
            S[:, 1, 1] = 0.0
            fq = rf.Frequency(self.freq, unit='hz')
            net = rf.Network(frequency=fq, s=S)
            net.write_touchstone(fname)
            messagebox.showinfo("Touchstone", f"Exportado para {fname}.")
        except Exception as ex:
            messagebox.showerror("Erro", f"Falha ao exportar: {ex}")

    def export_markinfo(self):
        if not self.draggable_marks:
            messagebox.showwarning("Exportar Marcas", "Nenhuma marca para exportar.")
            return
        fname = filedialog.asksaveasfilename(defaultextension=".csv",
                                             filetypes=[("CSV", "*.csv"), ("TXT", "*.txt"), ("XLS", "*.xls"), ("All", "*.*")])
        if not fname:
            return
        ext = os.path.splitext(fname)[1].lower()
        lines = []
        header = "Mark#,Freq(MHz),S11(dB),S11(°),S21(dB),S21(°),VSWR,R(Ω),X(Ω),Extra"
        lines.append(header)
        for item in self.markinfo_tree.get_children():
            vals = self.markinfo_tree.item(item)["values"]
            line = ",".join(str(v) for v in vals)
            lines.append(line)
        try:
            if ext in [".csv", ".txt"]:
                with open(fname, "w", encoding="utf-8") as f:
                    f.write("\n".join(lines))
                messagebox.showinfo("Exportar Marcas", f"Arquivo salvo em {fname}")
            elif ext == ".xls":
                wb = Workbook()
                ws = wb.active
                for r in lines:
                    ws.append(r.split(","))
                wb.save(fname)
                messagebox.showinfo("Exportar Marcas", f"Arquivo XLS salvo em {fname}")
            else:
                with open(fname, "w", encoding="utf-8") as f:
                    f.write("\n".join(lines))
                messagebox.showinfo("Exportar Marcas", f"Arquivo salvo em {fname}")
        except Exception as ex:
            messagebox.showerror("Erro", f"Falha ao exportar marcas: {ex}")

    ###########################################################################
    # Funções de Marcas: Adicionar/Remover
    ###########################################################################
    def add_mark_center(self):
        if self.freq is not None and self.freq.size > 0:
            center_mhz = (self.freq[0]/1e6 + self.freq[-1]/1e6) / 2
        else:
            center_mhz = 800.0
        new_mark = DraggableMark(center_mhz, self, domain="freq")
        self.draggable_marks.append(new_mark)
        self.update_all_plots()

    def remove_mark(self):
        if self.draggable_marks:
            mark = self.draggable_marks.pop()
            mark.remove_all_axes()
            self.update_all_plots()
        else:
            messagebox.showinfo("Marcas", "Nenhuma marca para remover.")

    ###########################################################################
    # Atualiza a Aba de Informações das Marcas
    ###########################################################################
    def update_markinfo_tab(self):
        for item in self.markinfo_tree.get_children():
            self.markinfo_tree.delete(item)
        if self.freq is None or self.freq.size < 2:
            return
        for i, mk in enumerate(self.draggable_marks):
            idx = np.argmin(np.abs(self.freq - mk.x_value * 1e6))
            freq_mhz = self.freq[idx] / 1e6
            s11_val = self.s11[idx]
            s21_val = self.s21[idx]
            s11_db = 20 * np.log10(np.abs(s11_val) + 1e-15)
            s11_ph = np.angle(s11_val, deg=True)
            s21_db = 20 * np.log10(np.abs(s21_val) + 1e-15)
            s21_ph = np.angle(s21_val, deg=True)
            mag_s11 = np.abs(s11_val)
            vswr = (1 + mag_s11) / (1 - mag_s11) if mag_s11 < 1 else float("inf")
            z0 = 50.0
            try:
                z_val = z0 * (1 + s11_val) / (1 - s11_val)
            except ZeroDivisionError:
                z_val = float("inf")
            r_val = z_val.real
            x_val = z_val.imag
            omega = 2 * np.pi * (freq_mhz * 1e6)
            extra_txt = ""
            if abs(x_val) > 1e-9 and freq_mhz > 0:
                if x_val > 0:
                    L_val = x_val / omega
                    extra_txt = f"L={L_val*1e9:.2f} nH"
                else:
                    C_val = -1 / (omega * x_val)
                    extra_txt = f"C={C_val*1e12:.2f} pF"
            vals = (f"{i+1}", f"{freq_mhz:.3f}", f"{s11_db:.2f}", f"{s11_ph:.1f}",
                    f"{s21_db:.2f}", f"{s21_ph:.1f}", f"{vswr:.2f}", f"{r_val:.1f}",
                    f"{x_val:.1f}", extra_txt)
            self.markinfo_tree.insert("", "end", values=vals)

    ###########################################################################
    # Atualiza Todos os Gráficos e Status
    ###########################################################################
    def update_status_bar(self):
        conn_str = "Conectado" if (self.vna and self.vna.is_connected()) else "Desconectado"
        swp_str = "Streaming" if self.streaming else "Idle"
        cal_str = "Calibrado" if self.is_calibrated else "Não Calib"
        now_str = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        status_txt = f"[{conn_str}] | [{swp_str}] | [{cal_str}] | {now_str}"
        self.status_bar.config(text=status_txt)

    def update_status_time(self):
        self.update_status_bar()
        self.after(1000, self.update_status_time)

    ###########################################################################
    # Função para fechar o aplicativo
    ###########################################################################
    def on_closing(self):
        self.streaming = False
        if self.stream_thread:
            self.stream_thread.join(timeout=1)
        if self.vna:
            self.vna.kill()
        self.destroy()

    def run(self):
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.mainloop()

###############################################################################
# Execução Principal
###############################################################################
if __name__ == "__main__":
    app = NanoVNAApp()
    app.run()
