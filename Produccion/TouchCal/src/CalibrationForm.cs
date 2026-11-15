using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Windows.Forms;

namespace TouchCal
{
    // Pantalla completa: el usuario toca 4 objetivos y luego prueba el resultado.
    public sealed class CalibrationForm : Form
    {
        const double INSET = 0.12; // los objetivos van al 12% del borde

        readonly Rectangle monitor;
        readonly int timeoutSec;
        readonly PointF[] targets;      // en coordenadas del formulario
        readonly List<PointF> rawPoints = new List<PointF>();
        readonly List<PointF> samples = new List<PointF>();
        readonly Timer timer;
        readonly float scale;

        int step;                       // 0..3 objetivos, 4 = prueba
        bool touching;
        int lastActivity = Environment.TickCount;
        string message = "";
        int messageUntil;
        PointF? cursor;                 // punto corregido en modo prueba
        readonly List<PointF> trail = new List<PointF>();
        Rectangle btnOk, btnRetry;

        public double[] ResultX, ResultY; // coeficientes resultantes

        public CalibrationForm(Rectangle monitor, int timeoutSec)
        {
            this.monitor = monitor;
            this.timeoutSec = Math.Max(5, timeoutSec);
            scale = Math.Max(1f, monitor.Height / 1080f * 1.0f);
            if (monitor.Width < monitor.Height) scale = Math.Max(1f, monitor.Width / 1080f);

            FormBorderStyle = FormBorderStyle.None;
            StartPosition = FormStartPosition.Manual;
            Bounds = monitor;
            TopMost = true;
            ShowInTaskbar = false;
            BackColor = Color.FromArgb(18, 18, 22);
            DoubleBuffered = true;
            KeyPreview = true;
            Text = "TouchCal - Calibración";

            float w = monitor.Width, h = monitor.Height;
            targets = new[]
            {
                new PointF((float)(w * INSET), (float)(h * INSET)),             // arriba izquierda
                new PointF((float)(w * (1 - INSET)), (float)(h * INSET)),       // arriba derecha
                new PointF((float)(w * (1 - INSET)), (float)(h * (1 - INSET))), // abajo derecha
                new PointF((float)(w * INSET), (float)(h * (1 - INSET))),       // abajo izquierda
            };

            int bw = (int)(260 * scale), bh = (int)(110 * scale), gap = (int)(40 * scale);
            int by = (int)(h * 0.62);
            btnOk = new Rectangle((int)(w / 2) - bw - gap / 2, by, bw, bh);
            btnRetry = new Rectangle((int)(w / 2) + gap / 2, by, bw, bh);

            timer = new Timer { Interval = 250 };
            timer.Tick += delegate { CheckTimeout(); Invalidate(); };
            timer.Start();
        }

        protected override void OnShown(EventArgs e)
        {
            base.OnShown(e);
            Activate();
            Cursor.Hide();
        }

        protected override void OnFormClosed(FormClosedEventArgs e)
        {
            timer.Stop();
            Cursor.Show();
            base.OnFormClosed(e);
        }

        protected override void OnKeyDown(KeyEventArgs e)
        {
            if (e.KeyCode == Keys.Escape) { DialogResult = DialogResult.Cancel; Close(); }
            else if (e.KeyCode == Keys.R) Restart();
            else if (e.KeyCode == Keys.Enter && step == 4) Accept();
            base.OnKeyDown(e);
        }

        int SecondsLeft
        {
            get { return timeoutSec - unchecked(Environment.TickCount - lastActivity) / 1000; }
        }

        void CheckTimeout()
        {
            if (touching || SecondsLeft > 0) return;
            if (step == 4) Accept();   // ya calibrado y nadie tocó: se acepta
            else { DialogResult = DialogResult.Cancel; Close(); } // se conserva la calibración anterior
        }

        void Restart()
        {
            step = 0;
            rawPoints.Clear();
            samples.Clear();
            cursor = null;
            trail.Clear();
            lastActivity = Environment.TickCount;
            Invalidate();
        }

        void Accept()
        {
            if (ResultX == null) return;
            DialogResult = DialogResult.OK;
            Close();
        }

        void Flash(string text)
        {
            message = text;
            messageUntil = Environment.TickCount + 2500;
        }

        // Lo llama la aplicación con cada evento de touch crudo.
        public void OnTouch(TouchEvent ev)
        {
            lastActivity = Environment.TickCount;
            var raw = new PointF((float)ev.U, (float)ev.V);

            if (step < 4)
            {
                if (ev.Kind == TouchKind.Down) { touching = true; samples.Clear(); }
                if (!touching) return;
                samples.Add(raw);
                if (ev.Kind == TouchKind.Up)
                {
                    touching = false;
                    AcceptTargetSample();
                }
            }
            else
            {
                PointF scr = MapRaw(raw);
                var local = new PointF(scr.X - monitor.Left, scr.Y - monitor.Top);
                if (ev.Kind == TouchKind.Down) { touching = true; trail.Clear(); }
                cursor = local;
                if (touching) { trail.Add(local); if (trail.Count > 400) trail.RemoveAt(0); }
                if (ev.Kind == TouchKind.Up)
                {
                    touching = false;
                    var p = Point.Round(local);
                    if (btnOk.Contains(p)) Accept();
                    else if (btnRetry.Contains(p)) Restart();
                }
            }
            Invalidate();
        }

        void AcceptTargetSample()
        {
            if (samples.Count == 0) return;
            // Promedio ignorando las primeras muestras (el dedo se asienta).
            int skip = samples.Count > 6 ? samples.Count / 3 : 0;
            double su = 0, sv = 0; int n = 0;
            for (int i = skip; i < samples.Count; i++) { su += samples[i].X; sv += samples[i].Y; n++; }
            var p = new PointF((float)(su / n), (float)(sv / n));

            foreach (var q in rawPoints)
            {
                double dx = p.X - q.X, dy = p.Y - q.Y;
                if (Math.Sqrt(dx * dx + dy * dy) < 0.08)
                {
                    Flash("Ese toque quedó muy cerca del anterior. Toca el objetivo nuevo.");
                    return;
                }
            }

            rawPoints.Add(p);
            step++;
            if (step == 4) Compute();
        }

        void Compute()
        {
            var scr = new List<PointF>();
            foreach (var t in targets) scr.Add(new PointF(t.X + monitor.Left, t.Y + monitor.Top));

            double[] xc, yc;
            if (!Config.Fit(rawPoints, scr, out xc, out yc))
            {
                Flash("No se pudo calcular. Repitamos la calibración.");
                Restart();
                return;
            }

            // Comprobar que los 4 toques son coherentes entre sí.
            double maxErr = 0, diag = Math.Sqrt((double)monitor.Width * monitor.Width + (double)monitor.Height * monitor.Height);
            for (int i = 0; i < 4; i++)
            {
                double x = xc[0] * rawPoints[i].X + xc[1] * rawPoints[i].Y + xc[2];
                double y = yc[0] * rawPoints[i].X + yc[1] * rawPoints[i].Y + yc[2];
                maxErr = Math.Max(maxErr, Math.Sqrt((x - scr[i].X) * (x - scr[i].X) + (y - scr[i].Y) * (y - scr[i].Y)));
            }
            if (maxErr > diag * 0.06)
            {
                Restart();
                Flash("Los toques no fueron precisos. Repitamos (toca justo en el centro de cada cruz).");
                return;
            }

            ResultX = xc;
            ResultY = yc;
        }

        PointF MapRaw(PointF r)
        {
            return new PointF((float)(ResultX[0] * r.X + ResultX[1] * r.Y + ResultX[2]),
                              (float)(ResultY[0] * r.X + ResultY[1] * r.Y + ResultY[2]));
        }

        // ---------------- Dibujo ----------------
        protected override void OnPaint(PaintEventArgs e)
        {
            var g = e.Graphics;
            g.SmoothingMode = SmoothingMode.AntiAlias;
            g.TextRenderingHint = System.Drawing.Text.TextRenderingHint.AntiAliasGridFit;

            using (var title = new Font("Segoe UI", 26 * scale, FontStyle.Bold, GraphicsUnit.Pixel))
            using (var body = new Font("Segoe UI", 20 * scale, GraphicsUnit.Pixel))
            using (var small = new Font("Segoe UI", 15 * scale, GraphicsUnit.Pixel))
            {
                var center = new StringFormat { Alignment = StringAlignment.Center, LineAlignment = StringAlignment.Center };
                var textRect = new RectangleF(ClientSize.Width * 0.2f, ClientSize.Height * 0.32f, ClientSize.Width * 0.6f, ClientSize.Height * 0.22f);

                if (step < 4)
                {
                    for (int i = 0; i < 4; i++)
                    {
                        if (i < step) DrawDone(g, targets[i]);
                        else if (i == step) DrawTarget(g, targets[i], touching);
                    }
                    g.DrawString("Calibración de touch", title, Brushes.White, new RectangleF(textRect.X, textRect.Y, textRect.Width, 60 * scale), center);
                    g.DrawString("Toca el centro de la cruz y levanta el dedo  (" + (step + 1) + " de 4)",
                        body, Brushes.Gainsboro, new RectangleF(textRect.X, textRect.Y + 60 * scale, textRect.Width, 80 * scale), center);
                }
                else
                {
                    g.DrawString("Prueba la calibración", title, Brushes.White, new RectangleF(textRect.X, textRect.Y, textRect.Width, 60 * scale), center);
                    g.DrawString("Desliza el dedo: el punto debe quedar justo bajo tu dedo.", body, Brushes.Gainsboro,
                        new RectangleF(textRect.X, textRect.Y + 60 * scale, textRect.Width, 80 * scale), center);
                    DrawButton(g, btnOk, "Aceptar", Color.FromArgb(46, 160, 67), body);
                    DrawButton(g, btnRetry, "Repetir", Color.FromArgb(90, 90, 100), body);

                    if (trail.Count > 1)
                        using (var pen = new Pen(Color.FromArgb(120, 0, 180, 255), 3 * scale)) g.DrawLines(pen, trail.ToArray());
                    if (cursor.HasValue)
                    {
                        float r = 14 * scale;
                        var c = cursor.Value;
                        g.FillEllipse(Brushes.DeepSkyBlue, c.X - r, c.Y - r, 2 * r, 2 * r);
                        g.DrawEllipse(Pens.White, c.X - r, c.Y - r, 2 * r, 2 * r);
                    }
                }

                int left = Math.Max(0, SecondsLeft);
                string foot = step < 4
                    ? "Sin tocar, se cancela en " + left + " s y se mantiene la calibración anterior.   Esc = cancelar   R = reiniciar"
                    : "Sin tocar, se acepta en " + left + " s.   Enter = aceptar   R = repetir   Esc = cancelar";
                g.DrawString(foot, small, Brushes.Gray, new RectangleF(0, ClientSize.Height - 50 * scale, ClientSize.Width, 40 * scale), center);

                if (message.Length > 0 && unchecked(Environment.TickCount - messageUntil) < 0)
                    g.DrawString(message, body, Brushes.Orange, new RectangleF(textRect.X, textRect.Bottom, textRect.Width, 80 * scale), center);
            }
        }

        void DrawTarget(Graphics g, PointF p, bool active)
        {
            float len = 40 * scale, r = 18 * scale;
            Color col = active ? Color.Orange : Color.White;
            using (var pen = new Pen(col, 3 * scale))
            {
                g.DrawLine(pen, p.X - len, p.Y, p.X + len, p.Y);
                g.DrawLine(pen, p.X, p.Y - len, p.X, p.Y + len);
                g.DrawEllipse(pen, p.X - r, p.Y - r, 2 * r, 2 * r);
            }
            // Pulso para llamar la atención
            float pulse = (Environment.TickCount % 1000) / 1000f;
            float pr = r + pulse * 30 * scale;
            using (var pen = new Pen(Color.FromArgb((int)(150 * (1 - pulse)), col), 2 * scale))
                g.DrawEllipse(pen, p.X - pr, p.Y - pr, 2 * pr, 2 * pr);
        }

        void DrawDone(Graphics g, PointF p)
        {
            float r = 10 * scale;
            g.FillEllipse(Brushes.SeaGreen, p.X - r, p.Y - r, 2 * r, 2 * r);
        }

        void DrawButton(Graphics g, Rectangle r, string text, Color color, Font font)
        {
            using (var b = new SolidBrush(color)) g.FillRectangle(b, r);
            var sf = new StringFormat { Alignment = StringAlignment.Center, LineAlignment = StringAlignment.Center };
            g.DrawString(text, font, Brushes.White, r, sf);
        }
    }
}
