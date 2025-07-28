import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import serial
import numpy as np
import time

class FlowCalibrationApp:
    def __init__(self, master):
        self.master = master
        master.title("Calibración de Flujómetro")
        master.geometry("960x700")

        # ── Marco de controles a la izquierda ────────────────────────────────
        control = ttk.Frame(master, padding=20)
        control.pack(side=tk.LEFT, fill=tk.Y)

        # Puerto y botón Conectar
        ttk.Label(control, text="Puerto serie (ej. COM3 / /dev/ttyUSB0):").pack(anchor=tk.W)
        self.port_entry = ttk.Entry(control)
        self.port_entry.insert(0, "COM3")
        self.port_entry.pack(fill=tk.X, pady=(0,10))
        self.connect_btn = ttk.Button(control, text="Conectar", command=self.connect_serial)
        self.connect_btn.pack(fill=tk.X, pady=(0,10))

        # Flujo real (anemómetro)
        ttk.Label(control, text="Flujo real (L/min):").pack(anchor=tk.W)
        self.flow_entry = ttk.Entry(control)
        self.flow_entry.pack(fill=tk.X, pady=(0,10))

        # Voltaje/precisión leído
        ttk.Label(control, text="Precisión (σ) V:").pack(anchor=tk.W)
        self.precision_var = tk.StringVar(value="n/a")
        self.precision_entry = ttk.Entry(control, textvariable=self.precision_var, state="readonly")
        self.precision_entry.pack(fill=tk.X, pady=(0,10))

        # Botón para tomar medida (envía referencia y parsea precisión)
        self.take_btn = ttk.Button(control, text="Tomar medida", command=self.take_measurement)
        self.take_btn.pack(fill=tk.X, pady=(0,10))

        # Botón para exportar datos
        self.export_btn = ttk.Button(control, text="Exportar datos (.txt)", command=self.export_data)
        self.export_btn.pack(fill=tk.X)

        # Datos y selección
        self.experiments = []        # [(flujo, precisión), ...]
        self.selected_flows = []     # flujos seleccionados para desviaciones

        # ── Panel de gráficas y consola a la derecha ─────────────────────────
        right_frame = ttk.Frame(master)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # Gráficas
        self.fig, (self.ax_scatter, self.ax_dev) = plt.subplots(2, 1, figsize=(6, 6))
        self.fig.tight_layout(pad=3)
        self.canvas = FigureCanvasTkAgg(self.fig, master=right_frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.canvas.mpl_connect('pick_event', self.on_pick)

        # Consola estilo Arduino (solo lectura)
        console_frame = ttk.Frame(right_frame)
        console_frame.pack(fill=tk.BOTH, expand=False, pady=(10,0))
        self.console_text = tk.Text(console_frame, height=8, state='disabled')
        scrollbar = ttk.Scrollbar(console_frame, orient='vertical', command=self.console_text.yview)
        self.console_text['yscrollcommand'] = scrollbar.set
        self.console_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Serial
        self.ser = None

        # Iniciar loop de lectura de serial
        self.master.after(100, self.read_serial)

    def connect_serial(self):
        port = self.port_entry.get().strip()
        if self.ser:
            try: self.ser.close()
            except: pass
        try:
            self.ser = serial.Serial(port, baudrate=9600, timeout=0.1)
            messagebox.showinfo("Puerto conectado", f"Conectado a {port}")
        except Exception as e:
            messagebox.showwarning("No conectado",
                                   f"No se pudo abrir {port}:\n{e}\nModo test activo.")
            self.ser = None

    def take_measurement(self):
        # validar flujo ingresado
        try:
            flow = float(self.flow_entry.get())
        except ValueError:
            messagebox.showerror("Entrada inválida", "El flujo debe ser un número.")
            return

        if not (self.ser and self.ser.is_open):
            messagebox.showwarning("Sin conexión", "No hay puerto serie abierto.")
            return

        # enviar referencia de flujo al Arduino
        try:
            self.ser.write(f"{flow}\n".encode())
        except Exception as e:
            messagebox.showerror("Error envío", f"No se pudo enviar referencia:\n{e}")
            return

        # bloquear hasta recibir la línea "Precisión (σ) = X V"
        precision = None
        t0 = time.time()
        timeout = 30.0  # segundos máximos de espera
        while True:
            if time.time() - t0 > timeout:
                messagebox.showerror("Timeout",
                                     f"No se recibió 'Precisión' en {timeout:.0f}s.")
                return

            raw = self.ser.readline().decode(errors='ignore')
            if not raw:
                continue
            line = raw.strip()
            self._console_insert(line + "\n")

            if line.lower().startswith("precisión"):
                # form. esperada: "Precisión (σ) = 0.0229 V"
                try:
                    val_str = line.split('=')[1].split('V')[0].strip()
                    precision = float(val_str)
                except Exception:
                    precision = None
                break

        if precision is None:
            messagebox.showerror("No data", "No se recibió el dato de precisión.")
            return

        # actualizar casilla y añadir experimento
        self.precision_var.set(f"{precision:.4f}")
        self.experiments.append((flow, precision))
        self.update_plots()

    def read_serial(self):
        """Lee líneas de la serial y las muestra (solo logs)."""
        if self.ser and self.ser.is_open:
            try:
                line = self.ser.readline().decode(errors='ignore')
                if line:
                    self._console_insert(line)
            except:
                pass
        self.master.after(100, self.read_serial)

    def _console_insert(self, text):
        self.console_text.configure(state='normal')
        self.console_text.insert('end', text)
        self.console_text.see('end')
        self.console_text.configure(state='disabled')

    def on_pick(self, event):
        idx = event.ind[0]
        flow = self.flows[idx]
        count = np.sum(np.isclose(self.flows, flow, atol=1e-3))
        if count < 2:
            messagebox.showwarning("Sin comparaciones",
                                   f"El flujo {flow:.3f} L/min solo tiene {count} muestra(s).")
            return
        if flow in self.selected_flows:
            self.selected_flows.remove(flow)
        else:
            self.selected_flows.append(flow)
        self.update_plots()

    def update_plots(self):
        # preparar arrays
        self.flows = np.array([f for f, p in self.experiments])
        self.precs = np.array([p for f, p in self.experiments])

        # ── Scatter & regresión global ──────────────────────────────────────
        self.ax_scatter.clear()
        colors = ['C1' if f in self.selected_flows else 'C0' for f in self.flows]
        self.ax_scatter.scatter(self.flows, self.precs,
                                c=colors, edgecolor='k',
                                picker=5, zorder=3)
        self.ax_scatter.set_xlabel("Flujo real (L/min)")
        self.ax_scatter.set_ylabel("Precisión (σ) V")
        if len(self.flows) > 1:
            m, b = np.polyfit(self.flows, self.precs, 1)
            r2 = np.corrcoef(self.flows, self.precs)[0,1]**2
            xs = np.linspace(self.flows.min(), self.flows.max(), 100)
            self.ax_scatter.plot(xs, m*xs + b, label=f"y={m:.3f}x+{b:.3f}", zorder=2)
            self.ax_scatter.text(0.05, 0.95,
                                 f"y = {m:.3f}x + {b:.3f}\nR² = {r2:.3f}",
                                 transform=self.ax_scatter.transAxes,
                                 va="top", bbox=dict(fc="w", alpha=0.7))
        self.ax_scatter.legend()

        # ── Campanas de desviación ─────────────────────────────────────────
        self.ax_dev.clear()
        if not self.selected_flows:
            self.ax_dev.text(0.5, 0.5,
                             "Haz click en uno o varios\npuntos arriba",
                             ha="center", va="center",
                             transform=self.ax_dev.transAxes)
        else:
            cmap = plt.cm.get_cmap("tab10", len(self.selected_flows))
            global_limit = 0
            for i, flow in enumerate(self.selected_flows):
                mask = np.isclose(self.flows, flow, atol=1e-3)
                group = self.precs[mask]
                μ = group.mean()
                deviations = group - μ
                σ = deviations.std(ddof=0)
                limit_dev = max(4*σ, np.abs(deviations).max())
                global_limit = max(global_limit, limit_dev)
                x = np.linspace(-limit_dev, limit_dev, 300)
                pdf_norm = np.exp(-0.5 * (x/σ)**2)
                color = cmap(i)
                self.ax_dev.plot(x, pdf_norm, color=color,
                                 label=f"{flow:.3f} L/min", zorder=2)
                idx_max = np.argmax(np.abs(deviations))
                wd = deviations[idx_max]
                wp = np.exp(-0.5*(wd/σ)**2)
                self.ax_dev.scatter(wd, wp, color=color,
                                    edgecolor='k', s=60, zorder=3)
                self.ax_dev.text(wd, wp+0.05,
                                 f"{wd:.3f} V", ha="center", va="bottom",
                                 color=color)
            self.ax_dev.set_xlabel("Desviación del voltaje (V)")
            self.ax_dev.set_ylabel("Densidad relativa")
            self.ax_dev.set_xlim(-global_limit, global_limit)
            self.ax_dev.set_ylim(0, 1.1)
            self.ax_dev.legend(loc="upper right")

        self.canvas.draw()

    def export_data(self):
        if not self.experiments:
            messagebox.showwarning("Sin datos", "No hay experimentos para exportar.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".txt",
                                            filetypes=[("Texto plano","*.txt")])
        if not path:
            return
        flows = np.array([f for f, p in self.experiments])
        precs = np.array([p for f, p in self.experiments])
        if len(flows) > 1:
            m, b = np.polyfit(flows, precs, 1)
            r2 = np.corrcoef(flows, precs)[0,1]**2
            std = precs.std()
            max_dev = np.abs(precs - precs.mean()).max()
        else:
            m = b = r2 = std = max_dev = 0.0
        with open(path, "w") as f:
            f.write("Exp\tFlujo(L/min)\tPrecisión(σ) V\n")
            for i, (fv, vv) in enumerate(self.experiments, 1):
                f.write(f"{i}\t{fv:.3f}\t{vv:.4f}\n")
            f.write("\n--- Estadísticas ---\n")
            f.write(f"y = {m:.6f} x + {b:.6f}\n")
            f.write(f"R² = {r2:.6f}\n")
            f.write(f"Std (σ) = {std:.6f} V\n")
            f.write(f"Max dev = {max_dev:.6f} V\n")
        messagebox.showinfo("Exportado", f"Datos guardados en:\n{path}")

if __name__ == "__main__":
    root = tk.Tk()
    app = FlowCalibrationApp(root)
    root.mainloop()
