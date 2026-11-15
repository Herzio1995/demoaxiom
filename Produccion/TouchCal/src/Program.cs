using System;
using System.Diagnostics;
using System.Drawing;
using System.Text;
using System.Threading;
using System.Windows.Forms;
using Microsoft.Win32;

namespace TouchCal
{
    static class Program
    {
        const string MutexName = "Local\\TouchCal_Instance";
        public const string CalibrateEventName = "Local\\TouchCal_Calibrate";

        [STAThread]
        static void Main(string[] args)
        {
            bool wantCalibrate = false;
            foreach (var a in args)
            {
                string s = a.ToLowerInvariant().TrimStart('/', '-');
                if (s == "calibrar" || s == "calibrate") wantCalibrate = true;
            }

            bool created;
            using (var mutex = new Mutex(true, MutexName, out created))
            {
                if (!created)
                {
                    // Ya hay una instancia: le pedimos que calibre.
                    try
                    {
                        using (var ev = EventWaitHandle.OpenExisting(CalibrateEventName)) ev.Set();
                    }
                    catch { }
                    return;
                }

                Native.MakeDpiAware();
                Application.EnableVisualStyles();
                Application.SetCompatibleTextRenderingDefault(false);
                try
                {
                    Application.Run(new TrayApp(wantCalibrate));
                }
                catch (Exception ex)
                {
                    MessageBox.Show("TouchCal se detuvo por un error:\n\n" + ex.Message, "TouchCal", MessageBoxButtons.OK, MessageBoxIcon.Error);
                }
            }
        }
    }

    sealed class TrayApp : ApplicationContext
    {
        const string RunKey = @"Software\Microsoft\Windows\CurrentVersion\Run";
        const string TouchKey = @"Software\Microsoft\Wisp\Touch";
        const int HOTKEY_ID = 1;

        readonly Config config;
        readonly TouchReader reader;
        readonly Injector injector;
        readonly NotifyIcon tray;
        readonly EventWaitHandle calibrateEvent;
        readonly System.Windows.Forms.Timer eventPoll;
        CalibrationForm calibForm;
        DiagForm diagForm;

        ToolStripMenuItem miEnabled, miOutMouse, miOutTouch, miCalOnStart, miStartup, miExclusive, miMonitor;

        public TrayApp(bool calibrateNow)
        {
            config = Config.Load();
            FixMonitorIfMissing();

            reader = new TouchReader();
            reader.Touch += OnTouch;
            reader.HotKey += delegate { StartCalibration(); };
            Native.RegisterHotKey(reader.Handle, HOTKEY_ID, 0x0001 | 0x0002 /* Alt+Ctrl */, (uint)Keys.C);

            injector = new Injector();
            injector.ShouldBlockNativeTouch = delegate
            {
                return calibForm != null || (config.Enabled && !config.OutputTouch);
            };

            tray = new NotifyIcon { Icon = MakeIcon(), Text = "TouchCal", Visible = true };
            tray.ContextMenuStrip = BuildMenu();
            tray.DoubleClick += delegate { StartCalibration(); };

            // Otra instancia (p. ej. un acceso directo con /calibrar) puede pedir calibrar.
            calibrateEvent = new EventWaitHandle(false, EventResetMode.AutoReset, Program.CalibrateEventName);
            eventPoll = new System.Windows.Forms.Timer { Interval = 300 };
            eventPoll.Tick += delegate { if (calibrateEvent.WaitOne(0)) StartCalibration(); };
            eventPoll.Start();

            if (calibrateNow || config.CalibrateOnStart || !config.Calibrated)
            {
                var t = new System.Windows.Forms.Timer { Interval = 1500 };
                t.Tick += delegate { t.Stop(); t.Dispose(); StartCalibration(); };
                t.Start();
            }
            else
            {
                tray.ShowBalloonTip(3000, "TouchCal", "Corrección de touch activa. Doble clic en el ícono para calibrar.", ToolTipIcon.Info);
            }
        }

        // ---------------- Touch ----------------
        void OnTouch(TouchEvent ev)
        {
            if (calibForm != null) { calibForm.OnTouch(ev); return; }
            if (!config.Enabled) return;
            injector.Send(ev.Kind, config.Map(ev.U, ev.V), config.OutputTouch);
        }

        void StartCalibration()
        {
            if (calibForm != null) { calibForm.Activate(); return; }
            injector.ReleaseAll();
            FixMonitorIfMissing();

            calibForm = new CalibrationForm(config.Monitor, config.CalibrationTimeout);
            calibForm.FormClosed += delegate
            {
                var f = calibForm;
                calibForm = null;
                if (f.DialogResult == DialogResult.OK && f.ResultX != null)
                {
                    config.A = f.ResultX[0]; config.B = f.ResultX[1]; config.C = f.ResultX[2];
                    config.D = f.ResultY[0]; config.E = f.ResultY[1]; config.F = f.ResultY[2];
                    config.Calibrated = true;
                    config.Enabled = true;
                    SaveAndRefresh();
                    tray.ShowBalloonTip(2500, "TouchCal", "Calibración guardada.", ToolTipIcon.Info);
                }
                f.Dispose();
            };
            calibForm.Show();
        }

        void FixMonitorIfMissing()
        {
            foreach (var s in Screen.AllScreens)
                if (s.Bounds == config.Monitor) return;
            // El monitor guardado ya no existe (cambió resolución u orientación): usar el principal.
            config.ResetToMonitor(Screen.PrimaryScreen.Bounds);
        }

        // ---------------- Menú ----------------
        ContextMenuStrip BuildMenu()
        {
            var menu = new ContextMenuStrip();
            menu.Items.Add(new ToolStripMenuItem("Calibrar ahora", null, delegate { StartCalibration(); }) { ShortcutKeyDisplayString = "Ctrl+Alt+C", Font = new Font(menu.Font, FontStyle.Bold) });

            miEnabled = new ToolStripMenuItem("Corrección activa", null, delegate
            {
                config.Enabled = !config.Enabled;
                injector.ReleaseAll();
                SaveAndRefresh();
            });
            menu.Items.Add(miEnabled);
            menu.Items.Add(new ToolStripSeparator());

            var quick = new ToolStripMenuItem("Corrección rápida");
            quick.DropDownItems.Add("Invertir eje X (izquierda ↔ derecha)", null, delegate { config.FlipX(); SaveAndRefresh(); });
            quick.DropDownItems.Add("Invertir eje Y (arriba ↔ abajo)", null, delegate { config.FlipY(); SaveAndRefresh(); });
            quick.DropDownItems.Add("Intercambiar ejes X ↔ Y", null, delegate { config.SwapXY(); SaveAndRefresh(); });
            quick.DropDownItems.Add(new ToolStripSeparator());
            quick.DropDownItems.Add("Quitar calibración (mapeo directo)", null, delegate { config.ResetToMonitor(config.Monitor); SaveAndRefresh(); });
            menu.Items.Add(quick);

            miMonitor = new ToolStripMenuItem("Monitor del tótem");
            miMonitor.DropDownOpening += delegate { FillMonitorMenu(); };
            miMonitor.DropDownItems.Add("(cargando)");
            menu.Items.Add(miMonitor);

            var output = new ToolStripMenuItem("Enviar toques como");
            miOutMouse = new ToolStripMenuItem("Mouse (compatible con todo)", null, delegate { config.OutputTouch = false; injector.ReleaseAll(); SaveAndRefresh(); });
            miOutTouch = new ToolStripMenuItem("Touch (permite deslizar/scroll; usar con modo exclusivo)", null, delegate { config.OutputTouch = true; injector.ReleaseAll(); SaveAndRefresh(); });
            output.DropDownItems.Add(miOutMouse);
            output.DropDownItems.Add(miOutTouch);
            menu.Items.Add(output);

            menu.Items.Add(new ToolStripSeparator());
            miCalOnStart = new ToolStripMenuItem("Calibrar cada vez que inicia", null, delegate { config.CalibrateOnStart = !config.CalibrateOnStart; SaveAndRefresh(); });
            miStartup = new ToolStripMenuItem("Iniciar con Windows", null, delegate { SetStartup(!IsStartup()); RefreshMenu(); });
            miExclusive = new ToolStripMenuItem("Modo exclusivo (desactivar touch de Windows)…", null, delegate { ToggleExclusive(); });
            menu.Items.Add(miCalOnStart);
            menu.Items.Add(miStartup);
            menu.Items.Add(miExclusive);

            menu.Items.Add(new ToolStripSeparator());
            menu.Items.Add("Diagnóstico…", null, delegate { ShowDiag(); });
            menu.Items.Add("Abrir carpeta de configuración", null, delegate
            {
                System.IO.Directory.CreateDirectory(Config.Folder);
                Process.Start("explorer.exe", Config.Folder);
            });
            menu.Items.Add("Salir", null, delegate { ExitThread(); });

            menu.Opening += delegate { RefreshMenu(); };
            RefreshMenu();
            return menu;
        }

        void FillMonitorMenu()
        {
            miMonitor.DropDownItems.Clear();
            int i = 1;
            foreach (var s in Screen.AllScreens)
            {
                var scr = s;
                string name = string.Format("Monitor {0}: {1}x{2} en ({3},{4}){5}", i++, s.Bounds.Width, s.Bounds.Height,
                    s.Bounds.Left, s.Bounds.Top, s.Primary ? " — principal" : "");
                var item = new ToolStripMenuItem(name, null, delegate
                {
                    if (scr.Bounds == config.Monitor) return;
                    config.ResetToMonitor(scr.Bounds);
                    SaveAndRefresh();
                    StartCalibration();
                });
                item.Checked = s.Bounds == config.Monitor;
                miMonitor.DropDownItems.Add(item);
            }
        }

        void RefreshMenu()
        {
            miEnabled.Checked = config.Enabled;
            miOutMouse.Checked = !config.OutputTouch;
            miOutTouch.Checked = config.OutputTouch;
            miCalOnStart.Checked = config.CalibrateOnStart;
            miStartup.Checked = IsStartup();
            miExclusive.Checked = IsExclusive();
            tray.Text = config.Enabled ? (config.Calibrated ? "TouchCal — calibrado" : "TouchCal — sin calibrar") : "TouchCal — corrección apagada";
        }

        void SaveAndRefresh()
        {
            try { config.Save(); }
            catch (Exception ex) { MessageBox.Show("No se pudo guardar la configuración:\n" + ex.Message, "TouchCal"); }
            if (tray != null && tray.ContextMenuStrip != null) RefreshMenu();
        }

        // ---------------- Inicio con Windows ----------------
        static bool IsStartup()
        {
            using (var k = Registry.CurrentUser.OpenSubKey(RunKey))
                return k != null && k.GetValue("TouchCal") != null;
        }

        static void SetStartup(bool on)
        {
            using (var k = Registry.CurrentUser.CreateSubKey(RunKey))
            {
                if (on) k.SetValue("TouchCal", "\"" + Application.ExecutablePath + "\"");
                else k.DeleteValue("TouchCal", false);
            }
        }

        // ---------------- Modo exclusivo (TouchGate) ----------------
        // TouchGate=0 hace que Windows deje de interpretar el touch; TouchCal lo sigue
        // leyendo en crudo y es el único que genera los toques (como hace UPDD).
        public static bool IsExclusive()
        {
            using (var k = Registry.CurrentUser.OpenSubKey(TouchKey))
            {
                object v = k == null ? null : k.GetValue("TouchGate");
                return v is int && (int)v == 0;
            }
        }

        void ToggleExclusive()
        {
            bool turnOn = !IsExclusive();
            string msg = turnOn
                ? "Esto desactiva el touch nativo de Windows. Desde ese momento el touch solo funcionará mientras TouchCal esté abierto (activa también \"Iniciar con Windows\").\n\n" +
                  "Ventaja: ningún programa recibe los toques invertidos, y puedes usar la salida \"Touch\" para deslizar.\n\n" +
                  "Requiere cerrar sesión o reiniciar para aplicarse. ¿Activar?"
                : "Esto vuelve a activar el touch nativo de Windows. Requiere cerrar sesión o reiniciar. ¿Continuar?";
            if (MessageBox.Show(msg, "TouchCal — Modo exclusivo", MessageBoxButtons.YesNo, MessageBoxIcon.Warning) != DialogResult.Yes) return;

            int value = turnOn ? 0 : 1;
            using (var k = Registry.CurrentUser.CreateSubKey(TouchKey)) k.SetValue("TouchGate", value, RegistryValueKind.DWord);
            try
            {
                using (var k = Registry.LocalMachine.CreateSubKey(TouchKey)) k.SetValue("TouchGate", value, RegistryValueKind.DWord);
            }
            catch { /* sin permisos de administrador: con HKCU suele bastar */ }

            if (turnOn && !IsStartup()) SetStartup(true);
            RefreshMenu();
            MessageBox.Show("Listo. Cierra sesión o reinicia Windows para que se aplique.", "TouchCal");
        }

        // ---------------- Diagnóstico ----------------
        void ShowDiag()
        {
            if (diagForm != null && !diagForm.IsDisposed) { diagForm.Activate(); return; }
            diagForm = new DiagForm(delegate
            {
                var sb = new StringBuilder();
                sb.AppendLine("Touch screens detectados (Raw Input):");
                bool any = false;
                foreach (var n in reader.DeviceNames) { sb.AppendLine("  " + n); any = true; }
                if (!any) sb.AppendLine("  (ninguno todavía — toca la pantalla)");
                sb.AppendLine();
                sb.AppendLine("Reportes recibidos: " + reader.ReportCount);
                sb.AppendLine("Último dato crudo: " + reader.LastRaw);
                sb.AppendLine();
                sb.AppendLine("Calibrado: " + (config.Calibrated ? "sí" : "no") + "    Corrección: " + (config.Enabled ? "activa" : "apagada"));
                sb.AppendLine("Salida: " + (config.OutputTouch ? (injector.TouchOutputFailed ? "touch (falló, usando mouse)" : "touch") : "mouse"));
                sb.AppendLine("Hook de mouse: " + (injector.HookInstalled ? "instalado" : "NO instalado") + "    Clics nativos bloqueados: " + injector.BlockedCount);
                sb.AppendLine("Modo exclusivo (TouchGate=0): " + (IsExclusive() ? "sí" : "no"));
                sb.AppendLine("Monitor del tótem: " + config.Monitor);
                sb.AppendLine(string.Format(System.Globalization.CultureInfo.InvariantCulture,
                    "Transformación: x = {0:0.##}·u + {1:0.##}·v + {2:0.##}   y = {3:0.##}·u + {4:0.##}·v + {5:0.##}",
                    config.A, config.B, config.C, config.D, config.E, config.F));
                sb.AppendLine();
                sb.AppendLine("Pantallas:");
                foreach (var s in Screen.AllScreens) sb.AppendLine("  " + s.DeviceName + "  " + s.Bounds + (s.Primary ? "  (principal)" : ""));
                return sb.ToString();
            });
            diagForm.Show();
        }

        static Icon MakeIcon()
        {
            using (var bmp = new Bitmap(32, 32))
            {
                using (var g = Graphics.FromImage(bmp))
                {
                    g.SmoothingMode = System.Drawing.Drawing2D.SmoothingMode.AntiAlias;
                    g.Clear(Color.Transparent);
                    g.FillEllipse(new SolidBrush(Color.FromArgb(0, 120, 215)), 1, 1, 30, 30);
                    using (var pen = new Pen(Color.White, 3))
                    {
                        g.DrawLine(pen, 16, 5, 16, 27);
                        g.DrawLine(pen, 5, 16, 27, 16);
                        g.DrawEllipse(pen, 10, 10, 12, 12);
                    }
                }
                return Icon.FromHandle(bmp.GetHicon());
            }
        }

        protected override void ExitThreadCore()
        {
            eventPoll.Stop();
            if (calibForm != null) calibForm.Close();
            Native.UnregisterHotKey(reader.Handle, HOTKEY_ID);
            injector.Dispose();
            reader.Dispose();
            tray.Visible = false;
            tray.Dispose();
            calibrateEvent.Dispose();
            base.ExitThreadCore();
        }
    }

    sealed class DiagForm : Form
    {
        public DiagForm(Func<string> getText)
        {
            Text = "TouchCal — Diagnóstico";
            Width = 820; Height = 520;
            StartPosition = FormStartPosition.CenterScreen;
            TopMost = true;
            var box = new TextBox
            {
                Multiline = true, ReadOnly = true, Dock = DockStyle.Fill,
                Font = new Font("Consolas", 10), ScrollBars = ScrollBars.Both, WordWrap = false
            };
            Controls.Add(box);
            var t = new System.Windows.Forms.Timer { Interval = 200 };
            t.Tick += delegate { string s = getText(); if (box.Text != s) box.Text = s; };
            t.Start();
            FormClosed += delegate { t.Stop(); t.Dispose(); };
        }
    }
}
