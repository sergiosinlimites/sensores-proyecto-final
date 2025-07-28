import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import serial
import numpy as np
import time
import re

class FlowCalibrationApp:
    def __init__(self, master):
        self.master = master
        master.title("Calibración de Flujómetro")
        master.geometry("960x900")

        # ── Controles izquierda ─────────────────────────────────────────────
        control = ttk.Frame(master, padding=20)
        control.pack(side=tk.LEFT, fill=tk.Y)

        ttk.Label(control, text="Puerto serie (ej. COM3 / /dev/ttyUSB0):").pack(anchor=tk.W)
        self.port_entry = ttk.Entry(control); self.port_entry.insert(0, "COM3")
        self.port_entry.pack(fill=tk.X, pady=(0,10))
        ttk.Button(control, text="Conectar", command=self.connect_serial).pack(fill=tk.X, pady=(0,10))

        ttk.Label(control, text="Flujo real (L/min):").pack(anchor=tk.W)
        self.flow_entry = ttk.Entry(control); self.flow_entry.pack(fill=tk.X, pady=(0,10))

        ttk.Label(control, text="Precisión (σ):").pack(anchor=tk.W)
        self.precision_var = tk.StringVar(value="n/a")
        ttk.Entry(control, textvariable=self.precision_var, state="readonly").pack(fill=tk.X, pady=(0,10))

        self.take_btn = ttk.Button(control, text="Tomar medida", command=self.take_measurement)
        self.take_btn.pack(fill=tk.X, pady=(0,10))
        ttk.Button(control, text="Exportar datos (.txt)", command=self.export_data).pack(fill=tk.X, pady=(0,5))
        ttk.Button(control, text="Generar reporte (.pdf)", command=self.generate_report).pack(fill=tk.X)

        ttk.Label(control, text="Datos resumen:").pack(anchor=tk.W, pady=(10,0))
        self.info_var = tk.StringVar(value="")
        ttk.Label(control, textvariable=self.info_var, wraplength=200, justify=tk.LEFT).pack(fill=tk.X)

        # Datos
        self.experiments = []   # dicts con: ref, flowAvg, voltAvg, prec, exact, meas
        self.selected = []      # índice del experimento seleccionado

        # ── Panel derecho: gráficas + consola ───────────────────────────────
        right = ttk.Frame(master); right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        self.fig, (self.ax_scatter, self.ax_dev, self.ax_bar) = plt.subplots(3, 1, figsize=(6,9))
        self.fig.tight_layout(pad=3)
        self.canvas = FigureCanvasTkAgg(self.fig, master=right)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.canvas.mpl_connect('pick_event', self.on_pick)

        console_frame = ttk.Frame(right); console_frame.pack(fill=tk.BOTH, pady=(10,0))
        self.console_text = tk.Text(console_frame, height=8, state='disabled')
        sb = ttk.Scrollbar(console_frame, orient='vertical', command=self.console_text.yview)
        self.console_text['yscrollcommand'] = sb.set
        self.console_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        self.ser = None
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
            messagebox.showwarning("No conectado", f"No se pudo abrir {port}:\n{e}\nModo test activo.")
            self.ser = None

    def take_measurement(self):
        # evitar doble click
        if self.take_btn['state']=='disabled':
            return
        self.take_btn.config(state='disabled')

        try:
            ref = float(self.flow_entry.get())
        except ValueError:
            messagebox.showerror("Entrada inválida", "El flujo debe ser un número.")
            self.take_btn.config(state='normal')
            return
        if not (self.ser and self.ser.is_open):
            messagebox.showwarning("Sin conexión", "Conecta primero el puerto serie.")
            self.take_btn.config(state='normal')
            return

        # envío y lectura
        self.ser.reset_input_buffer()
        self.ser.write(f"{ref}\n".encode())
        meas, flowAvg, prec = [], None, None
        t0, timeout = time.time(), 30.0

        try:
            while True:
                if time.time()-t0>timeout:
                    messagebox.showerror("Timeout", f"No se recibió resumen en {timeout:.0f}s.")
                    return

                raw = self.ser.readline().decode(errors='ignore')
                if not raw:
                    self.master.update(); continue
                line = raw.strip()
                self._console_insert(line+"\n")
                low = line.lower()

                # 1) lecturas numéricas
                if re.fullmatch(r'\d+(\.\d+)?', line):
                    meas.append(float(line))
                    continue

                # 2) Promedio flujo
                if low.startswith("promedio flujo"):
                    try:
                        flowAvg = float(line.split('=')[1].split()[0])
                    except:
                        pass
                    continue

                # 3) Precisión
                if low.startswith("precisión") or low.startswith("prec"):
                    try:
                        prec = float(line.split('=')[1].split()[0])
                    except:
                        pass
                    continue

                # 4) Exactitud — solo rompe
                if low.startswith("exactitud"):
                    break
        finally:
            self.take_btn.config(state='normal')

        # Validar que haya llegado todo lo mínimo
        if flowAvg is None or prec is None or len(meas)==0:
            messagebox.showerror("Parse error", f"Faltan datos o no llegaron mediciones. ${flowAvg is None} ${prec is None} ${len(meas)==0}")
            return

        # Cálculos finales
        voltAvg = float(np.mean(meas))
        exact   = abs(ref - flowAvg)

        self.precision_var.set(f"{prec:.4f}")
        self.experiments.append({
            'ref':     ref,
            'flowAvg': flowAvg,
            'voltAvg': voltAvg,
            'prec':    prec,
            'exact':   exact,
            'meas':    meas
        })
        self.selected = [len(self.experiments)-1]
        self._update_summary(self.selected[0])
        self.update_plots()

    def _update_summary(self, idx):
        e = self.experiments[idx]
        self.info_var.set(
            f"1. Referencia:      {e['ref']:.2f} slm\n"
            f"2. Flujo promedio:  {e['flowAvg']:.2f} slm\n"
            f"3. Voltage promedio:{e['voltAvg']:.3f} V\n"
            f"4. Precisión (σ):   {e['prec']:.3f} V\n"
            f"5. Exactitud:       {e['exact']:.2f} slm\n"
            f"6. Nº de datos:     {len(e['meas'])}"
        )

    def read_serial(self):
        if self.ser and self.ser.is_open:
            try:
                line = self.ser.readline().decode(errors='ignore')
                if line: self._console_insert(line)
            except:
                pass
        self.master.after(100, self.read_serial)

    def _console_insert(self, txt):
        self.console_text.configure(state='normal')
        self.console_text.insert('end', txt)
        self.console_text.see('end')
        self.console_text.configure(state='disabled')

    def on_pick(self, event):
        idx = event.ind[0]
        self.selected = [idx]
        self._update_summary(idx)
        self.update_plots()

    def update_plots(self):
        # -- Scatter + regresión --
        self.ax_scatter.clear()
        if self.experiments:
            refs  = np.array([e['ref']     for e in self.experiments])
            volts = np.array([e['voltAvg'] for e in self.experiments])
            cols  = ['r' if i in self.selected else 'C0' for i in range(len(refs))]
            sz    = [100 if i in self.selected else 60 for i in range(len(refs))]
            self.ax_scatter.scatter(refs, volts, c=cols, s=sz,
                                    edgecolor='k', picker=5, zorder=3, label="Mediciones")
            if len(refs)>1:
                m,b = np.polyfit(refs, volts,1)
                r2  = np.corrcoef(refs, volts)[0,1]**2
                xs  = np.linspace(refs.min(), refs.max(), 100)
                self.ax_scatter.plot(xs, m*xs+b,
                                     label=f"y={m:.3f}x+{b:.3f}, R²={r2:.3f}", zorder=2)
            self.ax_scatter.legend()
        else:
            self.ax_scatter.set_title("Sin datos")
        self.ax_scatter.set_xlabel("Flujo de referencia (slm)")
        self.ax_scatter.set_ylabel("Voltage (V)")

        # -- Campana de desviaciones --
        self.ax_dev.clear()
        if self.experiments and self.selected:
            idx  = self.selected[0]
            data = np.array(self.experiments[idx]['meas'])
            mu, dev, std = data.mean(), data-data.mean(), data.std()
            lim = max(4*std, abs(dev).max())
            x   = np.linspace(-lim, lim,300)
            pdf = np.exp(-0.5*(x/std)**2)
            self.ax_dev.plot(x,pdf,color='C0',zorder=2)
            ypts = np.exp(-0.5*(dev/std)**2)
            self.ax_dev.scatter(dev,ypts,color='C0',s=30,alpha=0.6,zorder=3)
            ki = np.argmax(abs(dev))
            wd, wp = dev[ki], np.exp(-0.5*(dev[ki]/std)**2)
            self.ax_dev.scatter(wd,wp,color='r',edgecolor='k',s=80,zorder=4)
            self.ax_dev.text(wd,wp+0.05,f"{data[ki]:.2f}",ha="center",va="bottom",color='r')
            self.ax_dev.set_title(f"Prom dev = {mu:.2f} V   σ = {std:.2f} V")
        self.ax_dev.set_xlabel("Desviación (V)")
        self.ax_dev.set_ylabel("Densidad rel.")

        # -- Barra peor desviación --
        self.ax_bar.clear()
        if self.experiments:
            worst = [
                float(np.max(abs(np.array(e['meas']) - np.array(e['meas']).mean())))
                for e in self.experiments
            ]
            xs = np.arange(1,len(worst)+1)
            cols = ['r' if i in self.selected else 'C0' for i in xs-1]
            self.ax_bar.bar(xs, worst, color=cols, edgecolor='k', zorder=3)
            self.ax_bar.set_xticks(xs)
            self.ax_bar.set_xlabel("Experimento")
            self.ax_bar.set_ylabel("Máx desviación (V)")
            self.ax_bar.set_title("Peor desviación")
        self.canvas.draw()

    def export_data(self):
        # … tu código de exportar …
        pass

    def generate_report(self):
        # … tu código de reporte …
        pass

if __name__=="__main__":
    root = tk.Tk()
    app = FlowCalibrationApp(root)
    root.mainloop()
