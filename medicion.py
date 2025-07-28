import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import serial
import numpy as np
import time
import re
import io
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader

class FlowCalibrationApp:
    def __init__(self, master):
        self.master = master
        master.title("Calibración de Flujómetro")
        master.geometry("960x900")

        # ── Estilos ────────────────────────────────────────────────────────
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background="#f0f0f0")
        style.configure("TLabel", background="#f0f0f0", font=("Segoe UI", 10))
        style.configure("TButton", padding=6)
        style.configure("Header.TLabel", font=("Segoe UI", 11, "bold"))

        # ── Controles izquierda ─────────────────────────────────────────────
        control = ttk.Frame(master, padding=20, style="TFrame")
        control.pack(side=tk.LEFT, fill=tk.Y)

        ttk.Label(control, text="Puerto serie (ej. COM3 / /dev/ttyUSB0):", style="Header.TLabel").pack(anchor=tk.W)
        self.port_entry = ttk.Entry(control); self.port_entry.insert(0, "COM3")
        self.port_entry.pack(fill=tk.X, pady=(0,10))
        ttk.Button(control, text="Conectar", command=self.connect_serial).pack(fill=tk.X, pady=(0,10))

        ttk.Label(control, text="Velocidad patrón (m/s):", style="Header.TLabel").pack(anchor=tk.W)
        self.velocity_entry = ttk.Entry(control)
        self.velocity_entry.pack(fill=tk.X, pady=(0,10))

        ttk.Label(control, text="Precisión (σ):", style="Header.TLabel").pack(anchor=tk.W)
        self.precision_var = tk.StringVar(value="n/a")
        ttk.Entry(control, textvariable=self.precision_var, state="readonly").pack(fill=tk.X, pady=(0,10))

        self.take_btn = ttk.Button(control, text="Tomar medida", command=self.take_measurement)
        self.take_btn.pack(fill=tk.X, pady=(0,10))

        ttk.Button(control, text="Exportar datos (.txt)", command=self.export_data).pack(fill=tk.X, pady=(0,5))
        ttk.Button(control, text="Generar reporte (.pdf)", command=self.generate_report).pack(fill=tk.X, pady=(0,5))
        ttk.Button(control, text="Reiniciar", command=self.reset_all).pack(fill=tk.X)

        ttk.Label(control, text="Datos resumen:", style="Header.TLabel").pack(anchor=tk.W, pady=(10,0))
        self.info_var = tk.StringVar(value="")
        ttk.Label(control, textvariable=self.info_var, wraplength=200, justify=tk.LEFT).pack(fill=tk.X)

        # ── Panel derecho ─────────────────────────────────────────────────
        right = ttk.Frame(master, style="TFrame")
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        self.fig, (self.ax_scatter, self.ax_dev, self.ax_bar) = plt.subplots(3,1,figsize=(6,9))
        self.fig.tight_layout(pad=3)
        self.canvas = FigureCanvasTkAgg(self.fig, master=right)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.canvas.mpl_connect('pick_event', self.on_pick)

        console_frame = ttk.Frame(right, style="TFrame")
        console_frame.pack(fill=tk.BOTH, pady=(10,0))
        self.console_text = tk.Text(console_frame, height=8, state='disabled', bg="#e8e8e8", font=("Consolas",10))
        sb = ttk.Scrollbar(console_frame, orient='vertical', command=self.console_text.yview)
        self.console_text['yscrollcommand'] = sb.set
        self.console_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        # ── Resolución ─────────────────────────────────────────────────────
        self.res_label = ttk.Label(master, text="Resolución sensor: 5 V / 1024", style="Header.TLabel")
        self.res_label.place(relx=1.0, rely=1.0, x=-10, y=-10, anchor="se")

        # datos internos
        self.experiments = []
        self.selected = []
        self.ser = None
        self.offset = None

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
        if self.take_btn['state']=='disabled': return
        self.take_btn.config(state='disabled')
        try:
            constante_proporcionalidad = 7.6
            ref = float(self.velocity_entry.get()) * constante_proporcionalidad
        except:
            messagebox.showerror("Error", "Velocidad inválida")
            self.take_btn.config(state='normal')
            return
        if not (self.ser and self.ser.is_open):
            messagebox.showwarning("Error", "Puerto no conectado")
            self.take_btn.config(state='normal')
            return

        self.ser.reset_input_buffer()
        self.ser.write(f"{ref}\n".encode())

        meas = []; flowAvg = None; prec = None; offset = None
        t0, TO = time.time(), 60.0
        try:
            while True:
                if time.time()-t0 > TO:
                    messagebox.showerror("Timeout","No llegó resumen")
                    return
                raw = self.ser.readline().decode(errors='ignore')
                if not raw:
                    self.master.update()
                    continue
                line = raw.strip(); low = line.lower()
                self._console_insert(line+"\n")

                if re.fullmatch(r'\d+(\.\d+)?', line):
                    meas.append(float(line)); continue
                m = re.search(r'promedio flujo\s*=\s*([-+]?\d*\.\d+)', low)
                if m:
                    flowAvg = float(m.group(1)); continue
                m2 = re.search(r'precisión.*=\s*([-+]?\d*\.\d+)', low)
                if m2:
                    prec = float(m2.group(1)); continue
                m3 = re.search(r'offset calculado\s*=\s*([-+]?\d*\.\d+)', low)
                if m3:
                    offset = float(m3.group(1))
                    break
                if low.startswith("exactitud"):
                    break
        finally:
            self.take_btn.config(state='normal')

        # si llegamos aquí con offset, pintarlo e irnos
        if offset is not None:
            self.offset = offset
            messagebox.showinfo("Offset", f"Offset calculado = {offset:.4f} V")
            # *inmediato* en la gráfica:
            self.ax_scatter.scatter([0], [offset],
                                    c='m', s=120, marker='X',
                                    label="Offset", zorder=4)
            self.ax_scatter.legend()
            self.canvas.draw()
            return

        # validación normal
        if flowAvg is None or prec is None or not meas:
            messagebox.showerror("Parse error",
                f"Faltan datos: flowAvg={flowAvg}, prec={prec}, N={len(meas)}")
            return

        voltAvg = float(np.mean(meas))
        exact_pct = abs(ref-flowAvg)/ref*100 if ref!=0 else 0.0
        self.precision_var.set(f"{prec:.4f}")
        self.experiments.append({
            'ref':ref,'flowAvg':flowAvg,'voltAvg':voltAvg,
            'prec':prec,'exact':exact_pct,'offset':offset,'meas':meas
        })
        self.selected=[len(self.experiments)-1]
        self._update_summary(self.selected[0])
        self.update_plots()

    def _update_summary(self, idx):
        e = self.experiments[idx]
        rel_prec = e['prec']/e['voltAvg']*100
        self.info_var.set(
            f"1. Referencia:       {e['ref']:.2f} slm\n"
            f"2. Flujo promedio:   {e['flowAvg']:.2f} slm\n"
            f"3. Voltaje promedio: {e['voltAvg']:.3f} V\n"
            f"4. Precisión (σ):    {e['prec']:.3f} V ({rel_prec:.1f} %)\n"
            f"5. Exactitud:        {e['exact']:.1f} %\n"
            f"6. Nº de datos:      {len(e['meas'])}"
        )

    def read_serial(self):
        if self.ser and self.ser.is_open:
            try:
                l = self.ser.readline().decode(errors='ignore')
                if l: self._console_insert(l)
            except: pass
        self.master.after(100, self.read_serial)

    def _console_insert(self, txt):
        self.console_text.configure(state='normal')
        self.console_text.insert('end', txt)
        self.console_text.see('end')
        self.console_text.configure(state='disabled')

    def on_pick(self, event):
        idx = event.ind[0]
        if event.mouseevent.button==3 and messagebox.askyesno("Eliminar",f"Borrar exp {idx+1}?"):
            del self.experiments[idx]; self.selected=[]
        else:
            self.selected=[idx]
        if self.selected: self._update_summary(self.selected[0])
        self.update_plots()

    def reset_all(self):
        if messagebox.askyesno("Reiniciar","Borrar todo?"):
            self.experiments=[]; self.selected=[]; self.info_var.set(""); self.update_plots()

    def update_plots(self):
        # ── Scatter + linealización (ahora incluye offset) ──────────────
        self.ax_scatter.clear()
        refs = np.array([e['ref'] for e in self.experiments])
        volts = np.array([e['voltAvg'] for e in self.experiments])
        # añadir offset al dataset si existe
        if self.offset is not None:
            refs = np.append(refs, 0.0)
            volts = np.append(volts, self.offset)

        if refs.size>0:
            cols = ['r' if i in self.selected else 'C0' for i in range(len(refs))]
            sz = [100 if i in self.selected else 60 for i in range(len(refs))]
            self.ax_scatter.scatter(refs, volts, c=cols, s=sz,
                                    picker=5, edgecolor='k', zorder=3,
                                    label="Mediciones")
            # regresión
            if len(refs)>1:
                m,b = np.polyfit(refs, volts, 1)
                r2 = np.corrcoef(refs, volts)[0,1]**2
                xs = np.linspace(refs.min(), refs.max(), 100)
                self.ax_scatter.plot(xs, m*xs+b,
                                     label=f"y={m:.3f}x+{b:.3f}, R²={r2:.3f}",
                                     zorder=2)
            self.ax_scatter.legend()
        else:
            self.ax_scatter.set_title("Sin datos")

        self.ax_scatter.set_xlabel("Flujo de referencia (slm)")
        self.ax_scatter.set_ylabel("Voltaje (V)")

        # ── Campana de desviaciones ───────────────────────────────────────
        self.ax_dev.clear()
        if self.experiments and self.selected:
            idx = self.selected[0]
            data = np.array(self.experiments[idx]['meas'])
            mu, dev, std = data.mean(), data-data.mean(), data.std()
            lim = max(4*std, abs(dev).max())
            x = np.linspace(-lim, lim, 300)
            pdf = np.exp(-0.5*(x/std)**2)
            self.ax_dev.plot(x, pdf, color='C0', zorder=2)
            ypts = np.exp(-0.5*(dev/std)**2)
            self.ax_dev.scatter(dev, ypts, color='C0', s=30, alpha=0.6, zorder=3)
            ki = np.argmax(abs(dev))
            wd, wp = dev[ki], np.exp(-0.5*(dev[ki]/std)**2)
            self.ax_dev.scatter(wd, wp, color='r', edgecolor='k', s=80, zorder=4)
            self.ax_dev.text(wd, wp+0.05, f"{data[ki]:.2f}", ha="center", va="bottom", color='r')
            self.ax_dev.set_title(f"Prom dev = {mu:.2f} V   σ = {std:.2f} V")
        self.ax_dev.set_xlabel("Desviación (V)")
        self.ax_dev.set_ylabel("Densidad relativa")

        # ── Barra peor desviación relativa ─────────────────────────────────
        self.ax_bar.clear()
        if self.experiments:
            worst_pct = []
            for e in self.experiments:
                arr = np.array(e['meas']); mu=arr.mean()
                worst_pct.append(float(np.max(np.abs(arr-mu))/mu*100))
            xs = np.arange(1, len(worst_pct)+1)
            cols = ['r' if i in self.selected else 'C0' for i in range(len(xs))]
            self.ax_bar.bar(xs, worst_pct, color=cols, edgecolor='k', zorder=3)
            self.ax_bar.set_xticks(xs)
            self.ax_bar.set_xlabel("Experimento")
            self.ax_bar.set_ylabel("Máx desviación (%)")
            self.ax_bar.set_title("Peor desviación relativa")
        self.canvas.draw()

    def export_data(self):
        path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Texto","*.txt")])
        if not path: return
        with open(path,"w") as f:
            for i,e in enumerate(self.experiments,1):
                f.write(f"=== Exp {i} ===\n")
                f.write(f"Referencia:        {e['ref']:.2f} slm\n")
                f.write(f"FlowAvg:           {e['flowAvg']:.2f} slm\n")
                f.write(f"VoltAvg:           {e['voltAvg']:.3f} V\n")
                f.write(f"σ:                  {e['prec']:.3f} V\n")
                f.write(f"Exactitud:         {e['exact']:.1f} %\n")
                if e.get('offset') is not None:
                    f.write(f"Offset:            {e['offset']:.4f} V\n")
                f.write(f"N datos:           {len(e['meas'])}\nMediciones:\n")
                for j in range(0,len(e['meas']),10):
                    chunk=e['meas'][j:j+10]
                    f.write("  "+", ".join(f"{v:.3f}" for v in chunk)+"\n")
                f.write("\n")
        messagebox.showinfo("Exportado","TXT guardado")

    def generate_report(self):
        path = filedialog.asksaveasfilename(defaultextension=".pdf",
                                            filetypes=[("PDF","*.pdf")])
        if not path:
            return

        # ── Cálculos previos ────────────────────────────────────────────────
        # Recolectar refs y volts (incluyendo offset como punto)
        refs  = np.array([e['ref']     for e in self.experiments])
        volts = np.array([e['voltAvg'] for e in self.experiments])
        if self.offset is not None:
            refs  = np.append(refs, 0.0)
            volts = np.append(volts, self.offset)

        # Ajuste lineal global
        m, b = np.polyfit(refs, volts, 1)
        r2   = np.corrcoef(refs, volts)[0,1]**2

        # --- NUEVO: Cálculo de peores métricas ---
        # Peor exactitud (%)
        worst_exact = max((e['exact'] for e in self.experiments), default=0.0)
        # Mayor sigma (desviación estándar en V)
        worst_sigma = max((np.std(e['meas']) for e in self.experiments), default=0.0)
        # ─────────────────────────────────────────────────────────────────────

        # ── Preparar PDF ────────────────────────────────────────────────────
        c = pdfcanvas.Canvas(path, pagesize=letter)
        w, h = letter

        # Título
        c.setFont("Helvetica-Bold", 16)
        c.drawString(2*cm, h-2*cm, "Reporte de Calibración de Flujómetro")

        # Empezamos a escribir desde aquí hacia abajo
        y = h - 2.7*cm
        c.setFont("Helvetica", 12)

        # Offset (si existe)
        if self.offset is not None:
            c.drawString(2*cm, y, f"Offset calculado: {self.offset:.4f} V")
            y -= 0.6*cm

        # --- NUEVO: Peores métricas al inicio ---
        c.drawString(2*cm, y, f"Peor exactitud:     {worst_exact:.1f} %")
        y -= 0.6*cm
        c.drawString(2*cm, y, f"Mayor σ (desv. est.): {worst_sigma:.3f} V")
        y -= 0.8*cm
        # ─────────────────────────────────────────────────────────────────

        # Ecuación global
        c.drawString(2*cm, y, f"Linealización global: y = {m:.3f} x + {b:.3f}, R² = {r2:.3f}")

        # ── Detalles por experimento ───────────────────────────────────────
        y -= 1*cm
        text = c.beginText(2*cm, y)
        text.setFont("Helvetica", 10)
        text.setLeading(12)
        for i, e in enumerate(self.experiments, start=1):
            rel_prec = e['prec'] / e['voltAvg'] * 100
            exact_pct = e['exact']
            text.textLine(f"Experimento {i}: Ref={e['ref']:.2f} slm, "
                          f"FlowAvg={e['flowAvg']:.2f} slm, VoltAvg={e['voltAvg']:.3f} V, "
                          f"σ={e['prec']:.3f} V ({rel_prec:.1f}%), Exactitud={exact_pct:.1f}%, "
                          f"N={len(e['meas'])}")
            if e.get('offset') is not None:
                text.textLine(f"  Offset: {e['offset']:.4f} V")
            text.textLine("  Mediciones crudas:")
            for j in range(0, len(e['meas']), 10):
                chunk = e['meas'][j:j+10]
                line  = "    " + ", ".join(f"{v:.3f}" for v in chunk)
                text.textLine(line)
            text.textLine("")
            if text.getY() < 4*cm:
                c.drawText(text)
                c.showPage()
                text = c.beginText(2*cm, h-2*cm)
                text.setFont("Helvetica", 10)
                text.setLeading(12)
        c.drawText(text)

        # ── Página de gráficas ─────────────────────────────────────────────
        c.showPage()

        # 1) Gráfica de linealización
        fig1, ax1 = plt.subplots(figsize=(4,3))
        ax1.scatter(refs, volts, zorder=3)
        xs = np.linspace(refs.min(), refs.max(), 100)
        ax1.plot(xs, m*xs + b, zorder=2)
        ax1.set_xlabel("Flujo de referencia (slm)")
        ax1.set_ylabel("Voltaje (V)")
        ax1.set_title("Calibración global")
        buf1 = io.BytesIO()
        fig1.savefig(buf1, format='png')
        plt.close(fig1)
        buf1.seek(0)
        c.drawImage(ImageReader(buf1), 2*cm, h/2, w-4*cm, h/2-3*cm)

        # 2) Gráfica de peor desviación relativa
        worst_pct = [float(np.max(np.abs(np.array(e['meas'])-np.array(e['meas']).mean()))/
                           np.array(e['meas']).mean()*100)
                     for e in self.experiments]
        fig2, ax2 = plt.subplots(figsize=(4,3))
        ax2.bar(np.arange(1, len(worst_pct)+1), worst_pct, edgecolor='k')
        ax2.set_xlabel("Experimento")
        ax2.set_ylabel("Máx desviación (%)")
        ax2.set_title("Peor desviación relativa")
        buf2 = io.BytesIO()
        fig2.savefig(buf2, format='png')
        plt.close(fig2)
        buf2.seek(0)
        c.drawImage(ImageReader(buf2), 2*cm, 2*cm, w-4*cm, h/2-5*cm)

        # Límite máximo absoluto del sensor
        overall = max(worst_pct, default=0.0)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(2*cm, 1.5*cm,
                     f"Límite máximo absoluto del sensor: {overall:.1f}%")

        c.save()
        messagebox.showinfo("Reporte PDF", "Reporte PDF generado exitosamente")

if __name__=="__main__":
    root=tk.Tk()
    app=FlowCalibrationApp(root)
    root.mainloop()
