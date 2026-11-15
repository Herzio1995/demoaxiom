using System;
using System.Collections.Generic;
using System.Drawing;
using System.Globalization;
using System.IO;
using System.Windows.Forms;

namespace TouchCal
{
    // Transformación afín: pantalla = f(touch crudo).
    //   x = A*u + B*v + C
    //   y = D*u + E*v + F
    // Con 6 coeficientes cubre ejes invertidos, ejes intercambiados, desplazamiento y escala.
    public sealed class Config
    {
        public double A, B, C, D, E, F;
        public Rectangle Monitor;          // monitor del tótem (píxeles físicos)
        public bool Calibrated;
        public bool Enabled = true;        // aplicar corrección
        public bool OutputTouch;           // false = mouse, true = touch inyectado
        public bool CalibrateOnStart;
        public int CalibrationTimeout = 30; // segundos sin tocar antes de cancelar

        public static string Folder
        {
            get { return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "TouchCal"); }
        }
        static string FilePath { get { return Path.Combine(Folder, "touchcal.ini"); } }

        public Config() { ResetToMonitor(Screen.PrimaryScreen.Bounds); }

        // Mapeo directo (sin corrección) sobre un monitor.
        public void ResetToMonitor(Rectangle mon)
        {
            Monitor = mon;
            A = mon.Width; B = 0; C = mon.Left;
            D = 0; E = mon.Height; F = mon.Top;
            Calibrated = false;
        }

        public PointF Map(double u, double v)
        {
            return new PointF((float)(A * u + B * v + C), (float)(D * u + E * v + F));
        }

        // Ajuste por mínimos cuadrados con N >= 3 puntos.
        public static bool Fit(IList<PointF> raw, IList<PointF> screen, out double[] xc, out double[] yc)
        {
            xc = yc = null;
            var m = new double[3, 3];
            var bx = new double[3];
            var by = new double[3];
            for (int i = 0; i < raw.Count; i++)
            {
                double[] r = { raw[i].X, raw[i].Y, 1 };
                for (int a = 0; a < 3; a++)
                {
                    for (int b = 0; b < 3; b++) m[a, b] += r[a] * r[b];
                    bx[a] += r[a] * screen[i].X;
                    by[a] += r[a] * screen[i].Y;
                }
            }
            xc = Solve3(m, bx);
            yc = Solve3(m, by);
            return xc != null && yc != null;
        }

        static double[] Solve3(double[,] m, double[] b)
        {
            double det = Det(m);
            if (Math.Abs(det) < 1e-12) return null;
            var res = new double[3];
            for (int col = 0; col < 3; col++)
            {
                var t = (double[,])m.Clone();
                for (int r = 0; r < 3; r++) t[r, col] = b[r];
                res[col] = Det(t) / det;
            }
            return res;
        }

        static double Det(double[,] m)
        {
            return m[0, 0] * (m[1, 1] * m[2, 2] - m[1, 2] * m[2, 1])
                 - m[0, 1] * (m[1, 0] * m[2, 2] - m[1, 2] * m[2, 0])
                 + m[0, 2] * (m[1, 0] * m[2, 1] - m[1, 1] * m[2, 0]);
        }

        // ---- Correcciones rápidas sin calibrar (se aplican sobre el monitor del tótem) ----
        public void FlipX()
        {
            // x' = L + R - x
            double s = 2 * Monitor.Left + Monitor.Width;
            A = -A; B = -B; C = s - C;
        }

        public void FlipY()
        {
            double s = 2 * Monitor.Top + Monitor.Height;
            D = -D; E = -E; F = s - F;
        }

        public void SwapXY()
        {
            // Normaliza al monitor, intercambia ejes y vuelve a píxeles.
            double L = Monitor.Left, T = Monitor.Top, W = Monitor.Width, H = Monitor.Height;
            double nA = (A) / W, nB = B / W, nC = (C - L) / W;
            double nD = (D) / H, nE = E / H, nF = (F - T) / H;
            A = nD * W; B = nE * W; C = nF * W + L;
            D = nA * H; E = nB * H; F = nC * H + T;
        }

        // ---- Guardar / cargar ----
        public void Save()
        {
            Directory.CreateDirectory(Folder);
            var ci = CultureInfo.InvariantCulture;
            var lines = new List<string>
            {
                "; TouchCal - configuración",
                "A=" + A.ToString("R", ci), "B=" + B.ToString("R", ci), "C=" + C.ToString("R", ci),
                "D=" + D.ToString("R", ci), "E=" + E.ToString("R", ci), "F=" + F.ToString("R", ci),
                "MonitorLeft=" + Monitor.Left, "MonitorTop=" + Monitor.Top,
                "MonitorWidth=" + Monitor.Width, "MonitorHeight=" + Monitor.Height,
                "Calibrated=" + (Calibrated ? 1 : 0),
                "Enabled=" + (Enabled ? 1 : 0),
                "OutputTouch=" + (OutputTouch ? 1 : 0),
                "CalibrateOnStart=" + (CalibrateOnStart ? 1 : 0),
                "CalibrationTimeout=" + CalibrationTimeout,
            };
            File.WriteAllLines(FilePath, lines.ToArray());
        }

        public static Config Load()
        {
            var c = new Config();
            if (!File.Exists(FilePath)) return c;
            var d = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            foreach (var line in File.ReadAllLines(FilePath))
            {
                int eq = line.IndexOf('=');
                if (eq > 0 && !line.StartsWith(";")) d[line.Substring(0, eq).Trim()] = line.Substring(eq + 1).Trim();
            }
            var ci = CultureInfo.InvariantCulture;
            Func<string, double, double> num = delegate(string k, double def)
            {
                string s; double v;
                return d.TryGetValue(k, out s) && double.TryParse(s, NumberStyles.Float, ci, out v) ? v : def;
            };
            c.A = num("A", c.A); c.B = num("B", c.B); c.C = num("C", c.C);
            c.D = num("D", c.D); c.E = num("E", c.E); c.F = num("F", c.F);
            c.Monitor = new Rectangle((int)num("MonitorLeft", c.Monitor.Left), (int)num("MonitorTop", c.Monitor.Top),
                                      (int)num("MonitorWidth", c.Monitor.Width), (int)num("MonitorHeight", c.Monitor.Height));
            c.Calibrated = num("Calibrated", 0) != 0;
            c.Enabled = num("Enabled", 1) != 0;
            c.OutputTouch = num("OutputTouch", 0) != 0;
            c.CalibrateOnStart = num("CalibrateOnStart", 0) != 0;
            c.CalibrationTimeout = (int)num("CalibrationTimeout", 30);
            return c;
        }
    }
}
