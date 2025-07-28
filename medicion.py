import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import serial
import numpy as np

class FlowCalibrationApp:
    def __init__(self, master):
        self.master = master
        master.title("Calibración de Flujómetro")
        master.geometry("960x750")

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

        # Voltaje leído
        ttk.Label(control, text="Voltaje (V):").pack(anchor=tk.W)
        self.voltage_var = tk.StringVar(value="n/a")
        self.voltage_entry = ttk.Entry(control, textvariable=self.voltage_var, state="readonly")
        self.voltage_entry.pack(fill=tk.X, pady=(0,10))

        # Botón para tomar medida
        self.take_btn = ttk.Button(control, text="Tomar medida", command=self.take_measurement)
        self.take_btn.pack(fill=tk.X, pady=(0,10))

        # Botón para exportar datos
        self.export_btn = ttk.Button(control, text="Exportar datos (.txt)", command=self.export_data)
        self.export_btn.pack(fill=tk.X)

        # Datos y selección
        self.experiments = []        # [(flujo, voltaje), ...]
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

        # Consola estilo Arduino
        console_frame = ttk.Frame(right_frame)
        console_frame.pack(fill=tk.BOTH, expand=False, pady=(10,0))

        self.console_text = tk.Text(console_frame, height=8, state='disabled')
        scrollbar = ttk.Scrollbar(console_frame, orient='vertical', command=self.console_text.yview)
        self.console_text['yscrollcommand'] = scrollbar.set
        self.console_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Promedio de datos recibidos
        self.avg_var = tk.StringVar(value="Promedio: n/a")
        ttk.Label(console_frame, textvariable=self.avg_var).pack(anchor=tk.W, pady=(5,0))

        # Entrada para enviar comandos y botón Send
        send_frame = ttk.Frame(console_frame)
        send_frame.pack(fill=tk.X, pady=(5,0))
        self.console_entry = ttk.Entry(send_frame)
        self.console_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.send_btn = ttk.Button(send_frame, text="Enviar", command=self.send_serial)
        self.send_btn.pack(side=tk.RIGHT, padx=(5,0))

        # Buffer de lectura de consola
        self.console_values = []

        # Serial
        self.ser = None

        # Iniciar loop de lectura de serial
        self.master.after(100, self.read_serial)

    def connect_serial(self):
        port = self.port_entry.get().strip()
        if self.ser:
            try: self.ser.close()
            except: pass
            self.ser = None
        try:
            self.ser = serial.Serial(port, baudrate=9600, timeout=0.1)
            messagebox.showinfo("Puerto conectado", f"Conectado a {port}")
        except Exception as e:
            messagebox.showwarning("No conectado",
                                   f"No se pudo abrir {port}:\n{e}\nModo test activo.")
            self.ser = None

    def take_measurement(self):
        try:
            flow = float(self.flow_entry.get())
        except ValueError:
            messagebox.showerror("Entrada inválida", "El flujo debe ser un número.")
            return

        if self.ser and self.ser.is_open:
            line = self.ser.readline().decode(errors='ignore').strip()
            try:
                voltage = float(line)
            except ValueError:
                messagebox.showerror("Lectura inválida", f"No se pudo convertir '{line}' a float.")
                return
        else:
            try:
                raw = input("Modo TEST – introduce voltaje (V): ")
                voltage = float(raw)
            except Exception:
                messagebox.showerror("Entrada inválida", "Voltaje no válido.")
                return

        self.voltage_var.set(f"{voltage:.3f}")
        self.experiments.append((flow, voltage))
        self.update_plots()

    def read_serial(self):
        """Lee continuamente el puerto y actualiza la consola."""
        if self.ser and self.ser.is_open:
            try:
                line = self.ser.readline().decode(errors='ignore').strip()
                if line:
                    # Mostrar en consola
                    self._console_insert(line + '\n')
                    # Intentar parsear número y actualizar promedio
                    try:
                        val = float(line)
                        self.console_values.append(val)
                        avg = sum(self.console_values) / len(self.console_values)
                        self.avg_var.set(f"Promedio: {avg:.3f}")
                    except:
                        pass
            except:
                pass
        self.master.after(100, self.read_serial)

    def send_serial(self):
        """Envía el contenido de la entrada a la serial y lo muestra."""
        cmd = self.console_entry.get().strip()
        if not cmd:
            return
        if self.ser and self.ser.is_open:
            try:
                self.ser.write((cmd + '\n').encode())
                self._console_insert(f">> {cmd}\n")
            except Exception as e:
                messagebox.showerror("Error envío", f"No se pudo enviar:\n{e}")
        else:
            messagebox.showwarning("Sin conexión", "No hay puerto serie abierto.")
        self.console_entry.delete(0, tk.END)

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
        self.flows = np.array([f for f, v in self.experiments])
        self.volts = np.array([v for f, v in self.experiments])

        # ── Scatter & regresión global ──────────────────────────────────────
        self.ax_scatter.clear()
        colors = ['C1' if f in self.selected_flows else 'C0' for f in self.flows]
        self.ax_scatter.scatter(self.flows, self.volts,
                                c=colors, edgecolor='k',
                                picker=5, zorder=3)
        self.ax_scatter.set_xlabel("Flujo real (L/min)")
        self.ax_scatter.set_ylabel("Voltaje (V)")
        if len(self.flows) > 1:
            m, b = np.polyfit(self.flows, self.volts, 1)
            r2 = np.corrcoef(self.flows, self.volts)[0,1]**2
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
                group = self.volts[mask]
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
        flows = np.array([f for f, v in self.experiments])
        volts = np.array([v for f, v in self.experiments])
        if len(flows) > 1:
            m, b = np.polyfit(flows, volts, 1)
            r2 = np.corrcoef(flows, volts)[0,1]**2
            std = volts.std()
            max_dev = np.abs(volts - volts.mean()).max()
        else:
            m = b = r2 = std = max_dev = 0.0
        with open(path, "w") as f:
            f.write("Exp\tFlujo(L/min)\tVoltaje(V)\n")
            for i, (fv, vv) in enumerate(self.experiments, 1):
                f.write(f"{i}\t{fv:.3f}\t{vv:.3f}\n")
            f.write("\n--- Estadísticas ---\n")
            f.write(f"y = {m:.6f} x + {b:.6f}\n")
            f.write(f"R² = {r2:.6f}\n")
            f.write(f"Std (V) = {std:.6f}\n")
            f.write(f"Max dev = {max_dev:.6f} V\n")
        messagebox.showinfo("Exportado", f"Datos guardados en:\n{path}")

if __name__ == "__main__":
    root = tk.Tk()
    app = FlowCalibrationApp(root)
    root.mainloop()
