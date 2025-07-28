import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import serial
import numpy as np
import pandas as pd
import time
import re
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm

class FlowCalibrationApp:
    def __init__(self, master):
        self.master = master
        master.title("Calibración de Flujómetro")
        master.geometry("960x800")

        # Controles izquierda
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

        ttk.Button(control, text="Tomar medida", command=self.take_measurement).pack(fill=tk.X, pady=(0,10))
        ttk.Button(control, text="Exportar datos (.txt)", command=self.export_data).pack(fill=tk.X, pady=(0,5))
        ttk.Button(control, text="Generar reporte (.pdf)", command=self.generate_report).pack(fill=tk.X)

        ttk.Label(control, text="Datos resumen:").pack(anchor=tk.W, pady=(10,0))
        self.info_var = tk.StringVar(value="")
        ttk.Label(control, textvariable=self.info_var, wraplength=200, justify=tk.LEFT).pack(fill=tk.X)

        # Datos
        self.experiments = []   # cada dict: ref, flowAvg, voltAvg, prec, exact, meas
        self.selected = []      # índices seleccionados

        # Panel derecho: gráficos + consola
        right = ttk.Frame(master); right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        self.fig, (self.ax_scatter, self.ax_dev) = plt.subplots(2, 1, figsize=(6,6))
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
        try:
            ref = float(self.flow_entry.get())
        except ValueError:
            messagebox.showerror("Entrada inválida", "El flujo debe ser un número.")
            return
        if not (self.ser and self.ser.is_open):
            messagebox.showwarning("Sin conexión", "Conecta primero el puerto serie.")
            return

        self.ser.reset_input_buffer()
        self.ser.write(f"{ref}\n".encode())

        meas, flowAvg, voltAvg, prec, exact = [], None, None, None, None
        t0, timeout = time.time(), 30.0

        while True:
            if time.time() - t0 > timeout:
                messagebox.showerror("Timeout", f"No se recibió resumen en {timeout:.0f}s.")
                return
            raw = self.ser.readline().decode(errors='ignore')
            if not raw:
                self.master.update(); continue
            line = raw.strip()
            self._console_insert(line + "\n")

            if re.match(r'^\d+(\.\d+)?$', line):
                meas.append(float(line)); self.master.update()

            low = line.lower()
            if low.startswith("promedio flujo"):
                try: flowAvg = float(line.split('=')[1].split()[0])
                except: pass
            elif low.startswith("voltavg"):
                try: voltAvg = float(line.split('=')[1].split()[0])
                except: pass
            elif low.startswith("precisión") or low.startswith("prec"):
                try: prec = float(line.split('=')[1].split()[0])
                except: pass
            elif low.startswith("exactitud"):
                try: exact = float(line.split('=')[1].split()[0])
                except: pass
                break

        if None in (flowAvg, prec, exact):
            messagebox.showerror("Parse error", "Faltan datos en el resumen.")
            return

        self.precision_var.set(f"{prec:.4f}")
        self.experiments.append({
            'ref': ref,
            'flowAvg': flowAvg,
            'voltAvg': voltAvg if voltAvg is not None else flowAvg,
            'prec': prec,
            'exact': exact,
            'meas': meas
        })
        self.selected = [len(self.experiments)-1]
        self._update_summary(len(self.experiments)-1)
        self.update_plots()

    def _update_summary(self, idx):
        e = self.experiments[idx]
        summary = (
            f"1. Ref: {e['ref']:.2f} slm\n"
            f"2. VoltAvg: {e['voltAvg']:.3f} V\n"
            f"3. Precisión: {e['prec']:.3f}\n"
            f"4. Exactitud: {e['exact']:.3f}\n"
            f"5. N datos: {len(e['meas'])}"
        )
        self.info_var.set(summary)

    def read_serial(self):
        if self.ser and self.ser.is_open:
            try:
                line = self.ser.readline().decode(errors='ignore')
                if line: self._console_insert(line)
            except: pass
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
        # Gráfica superior: scatter vs referencia y linealización
        self.ax_scatter.clear()
        if self.experiments:
            refs  = np.array([e['ref']     for e in self.experiments])
            volts = np.array([e['voltAvg'] for e in self.experiments])
            colors= ['r' if i in self.selected else 'C0' for i in range(len(refs))]
            sizes = [100 if i in self.selected else 60 for i in range(len(refs))]
            self.ax_scatter.scatter(refs, volts,
                                    c=colors, s=sizes,
                                    edgecolor='k', picker=5, zorder=3,
                                    label="Mediciones")
            if len(refs) > 1:
                m, b = np.polyfit(refs, volts, 1)
                r2   = np.corrcoef(refs, volts)[0,1]**2
                xs   = np.linspace(refs.min(), refs.max(), 100)
                self.ax_scatter.plot(xs, m*xs + b,
                                     label=f"y={m:.3f}x+{b:.3f}, R²={r2:.3f}",
                                     zorder=2)
            self.ax_scatter.legend()
        else:
            self.ax_scatter.set_title("Sin datos")
        self.ax_scatter.set_xlabel("Flujo de referencia (slm)")
        self.ax_scatter.set_ylabel("VoltAvg (V)")

        # Gráfica inferior: desviaciones del experimento seleccionado
        self.ax_dev.clear()
        if self.experiments and self.selected:
            idx  = self.selected[0]
            data = np.array(self.experiments[idx]['meas'])
            mu, dev, std = data.mean(), data - data.mean(), data.std()
            lim = max(4*std, abs(dev).max())
            x   = np.linspace(-lim, lim, 300)
            pdf = np.exp(-0.5*(x/std)**2)
            self.ax_dev.plot(x, pdf, color='C0', label=f"Exp {idx+1}", zorder=2)

            y_pts = np.exp(-0.5*(dev/std)**2)
            self.ax_dev.scatter(dev, y_pts, color='C0', s=30, alpha=0.6, zorder=3)

            ki = np.argmax(abs(dev))
            wd, wp = dev[ki], np.exp(-0.5*(dev[ki]/std)**2)
            self.ax_dev.scatter(wd, wp, color='r', edgecolor='k', s=80, zorder=4)
            self.ax_dev.text(wd, wp+0.05, f"{data[ki]:.2f}",
                             ha="center", va="bottom", color='r')

            self.ax_dev.legend(loc="upper left")
            self.ax_dev.set_title(f"Prom={mu:.2f} slm   σ={std:.2f} slm")
            self.ax_dev.set_xlabel("Desviación (slm)")
            self.ax_dev.set_ylabel("Densidad relativa")
        self.canvas.draw()

    def export_data(self):
        """Exporta todos los experimentos a un .txt completo."""
        if not self.experiments:
            messagebox.showwarning("Sin datos", "No hay experimentos para exportar.")
            return

        path = filedialog.asksaveasfilename(defaultextension=".txt",
                                            filetypes=[("Texto plano", "*.txt")])
        if not path:
            return

        with open(path, "w") as f:
            for i, e in enumerate(self.experiments, start=1):
                f.write(f"=== Experimento {i} ===\n")
                f.write(f"Flujo referencia: {e['ref']:.2f} slm\n")
                f.write(f"VoltAvg:          {e['voltAvg']:.3f} V\n")
                f.write(f"Precisión (σ):    {e['prec']:.3f}\n")
                f.write(f"Exactitud (abs):  {e['exact']:.3f}\n")
                f.write(f"Nº de datos:      {len(e['meas'])}\n")
                f.write("Mediciones:\n")
                # particionar en líneas de 10 valores
                for j in range(0, len(e['meas']), 10):
                    chunk = e['meas'][j:j+10]
                    line = ", ".join(f"{v:.3f}" for v in chunk)
                    f.write("  " + line + "\n")
                f.write("\n")

            # al final, la linealización global
            refs  = np.array([ex['ref']     for ex in self.experiments])
            volts = np.array([ex['voltAvg'] for ex in self.experiments])
            if len(refs) > 1:
                m, b = np.polyfit(refs, volts, 1)
                r2   = np.corrcoef(refs, volts)[0,1]**2
                f.write("=== Linealización global ===\n")
                f.write(f"y = {m:.6f} x + {b:.6f}\n")
                f.write(f"R² = {r2:.6f}\n")
        messagebox.showinfo("Exportado", f"Datos guardados en:\n{path}")

    def generate_report(self):
        if not self.experiments:
            messagebox.showwarning("Sin datos", "No hay datos para generar reporte.")
            return
        # Diálogo para guardar PDF
        path = filedialog.asksaveasfilename(defaultextension=".pdf",
                                            filetypes=[("PDF","*.pdf")])
        if not path:
            return

        # Crear canvas
        c = canvas.Canvas(path, pagesize=letter)
        width, height = letter

        # Título con estilo
        c.setFont("Helvetica-Bold", 18)
        c.drawString(2*cm, height - 2*cm, "Reporte de Calibración de Flujómetro")
        c.setLineWidth(1)
        c.line(2*cm, height - 2.3*cm, width - 2*cm, height - 2.3*cm)

        # Preparar texto
        text = c.beginText(2*cm, height - 3*cm)
        text.setFont("Helvetica", 10)
        leading = 12
        text.setLeading(leading)

        # Escribir cada experimento
        for i, e in enumerate(self.experiments, start=1):
            # Encabezado de experimento en negrita
            text.setFont("Helvetica-Bold", 12)
            text.textLine(f"Experimento {i}:")
            text.setFont("Helvetica", 10)

            # Datos básicos
            text.textLine(f"  • Flujo ref: {e['ref']:.2f} slm")
            text.textLine(f"  • VoltAvg:   {e['voltAvg']:.3f} V")
            text.textLine(f"  • Precisión: {e['prec']:.3f}")
            text.textLine(f"  • Exactitud: {e['exact']:.3f}")
            text.textLine(f"  • N datos:   {len(e['meas'])}")

            # Mediciones, en líneas de máximo 10 valores
            chunks = [e['meas'][j:j+10] for j in range(0, len(e['meas']), 10)]
            for chunk in chunks:
                line = ", ".join(f"{v:.3f}" for v in chunk)
                text.textLine(f"    {line}")

            # Espacio antes del siguiente experimento
            text.textLine("")
            # Si nos acercamos al final de la página, paginar
            if text.getY() < 4*cm:
                c.drawText(text)
                c.showPage()
                text = c.beginText(2*cm, height - 2*cm)
                text.setFont("Helvetica", 10)
                text.setLeading(leading)

        # Al final, ecuación y R²
        refs  = np.array([e['ref'] for e in self.experiments])
        volts = np.array([e['voltAvg'] for e in self.experiments])
        m, b  = np.polyfit(refs, volts, 1)
        r2    = np.corrcoef(refs, volts)[0,1]**2

        text.setFont("Helvetica-Bold", 12)
        text.textLine("Linealización final:")
        text.setFont("Helvetica", 10)
        text.textLine(f"  y = {m:.6f} x + {b:.6f}")
        text.textLine(f"  R² = {r2:.6f}")

        # Dibujar y guardar
        c.drawText(text)
        c.save()

        messagebox.showinfo("Reporte PDF", f"Reporte generado en:\n{path}")

if __name__ == "__main__":
    root = tk.Tk()
    app = FlowCalibrationApp(root)
    root.mainloop()
