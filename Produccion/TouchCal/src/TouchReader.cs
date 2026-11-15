using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;
using System.Windows.Forms;

namespace TouchCal
{
    public enum TouchKind { Down, Move, Up }

    public struct TouchEvent
    {
        public TouchKind Kind;
        public double U;   // coordenada X cruda normalizada 0..1 (tal como la manda el sensor)
        public double V;   // coordenada Y cruda normalizada 0..1
    }

    // Lee el touch screen directamente del HID (Raw Input), sin pasar por el
    // mapeo de Windows. Así la calibración funciona aunque Windows tenga los ejes mal.
    public sealed class TouchReader : NativeWindow, IDisposable
    {
        const ushort PAGE_GENERIC = 0x01, USAGE_X = 0x30, USAGE_Y = 0x31;
        const ushort PAGE_DIGITIZER = 0x0D, USAGE_TOUCHSCREEN = 0x04, USAGE_TIP = 0x42,
                     USAGE_CONTACT_ID = 0x51, USAGE_CONTACT_COUNT = 0x54;

        class Finger
        {
            public ushort Link;
            public int XMin, XMax, YMin, YMax;
            public bool HasTip, HasId;
        }

        class Device
        {
            public IntPtr Preparsed;
            public string Name;
            public List<Finger> Fingers = new List<Finger>();
            public bool HasContactCount;
            public bool Valid;
        }

        readonly Dictionary<IntPtr, Device> devices = new Dictionary<IntPtr, Device>();
        readonly ushort[] usageBuf = new ushort[128];
        readonly Timer watchdog;

        IntPtr lockedDevice = IntPtr.Zero;
        long lockedId = -1;
        double lastU, lastV;
        int lastSeenTick;

        public event Action<TouchEvent> Touch;
        public event Action<Message> HotKey;

        public string LastRaw = "(sin datos todavía)";
        public int ReportCount;

        public TouchReader()
        {
            CreateHandle(new CreateParams { Caption = "TouchCalReader" });

            var rid = new Native.RAWINPUTDEVICE[1];
            rid[0].usUsagePage = PAGE_DIGITIZER;
            rid[0].usUsage = USAGE_TOUCHSCREEN;
            rid[0].dwFlags = Native.RIDEV_INPUTSINK;
            rid[0].hwndTarget = Handle;
            if (!Native.RegisterRawInputDevices(rid, 1, (uint)Marshal.SizeOf(typeof(Native.RAWINPUTDEVICE))))
                throw new InvalidOperationException("No se pudo registrar Raw Input (error " + Marshal.GetLastWin32Error() + ").");

            // Si un dispositivo deja de reportar sin mandar "dedo arriba", se suelta solo.
            watchdog = new Timer { Interval = 200 };
            watchdog.Tick += delegate
            {
                if (lockedId >= 0 && unchecked(Environment.TickCount - lastSeenTick) > 2000)
                    Release();
            };
            watchdog.Start();
        }

        public IEnumerable<string> DeviceNames
        {
            get { foreach (var d in devices.Values) yield return (d.Valid ? "" : "[sin X/Y] ") + d.Name; }
        }

        protected override void WndProc(ref Message m)
        {
            if (m.Msg == Native.WM_INPUT)
            {
                try { ProcessInput(m.LParam); } catch { }
            }
            else if (m.Msg == Native.WM_HOTKEY)
            {
                if (HotKey != null) HotKey(m);
            }
            base.WndProc(ref m);
        }

        void ProcessInput(IntPtr hRaw)
        {
            uint headerSize = (uint)Marshal.SizeOf(typeof(Native.RAWINPUTHEADER));
            uint size = 0;
            Native.GetRawInputData(hRaw, Native.RID_INPUT, IntPtr.Zero, ref size, headerSize);
            if (size == 0) return;

            IntPtr buf = Marshal.AllocHGlobal((int)size);
            try
            {
                if (Native.GetRawInputData(hRaw, Native.RID_INPUT, buf, ref size, headerSize) != size) return;
                var header = (Native.RAWINPUTHEADER)Marshal.PtrToStructure(buf, typeof(Native.RAWINPUTHEADER));
                if (header.dwType != Native.RIM_TYPEHID) return;

                Device dev = GetDevice(header.hDevice);
                if (dev == null || !dev.Valid) return;

                int offset = (int)headerSize;
                int sizeHid = Marshal.ReadInt32(buf, offset);
                int count = Marshal.ReadInt32(buf, offset + 4);
                int dataStart = offset + 8;

                var report = new byte[sizeHid];
                for (int i = 0; i < count; i++)
                {
                    Marshal.Copy(IntPtr.Add(buf, dataStart + i * sizeHid), report, 0, sizeHid);
                    ParseReport(header.hDevice, dev, report);
                }
            }
            finally { Marshal.FreeHGlobal(buf); }
        }

        Device GetDevice(IntPtr hDevice)
        {
            Device dev;
            if (devices.TryGetValue(hDevice, out dev)) return dev;

            dev = new Device();
            devices[hDevice] = dev;
            dev.Name = GetDeviceName(hDevice);

            uint size = 0;
            Native.GetRawInputDeviceInfo(hDevice, Native.RIDI_PREPARSEDDATA, IntPtr.Zero, ref size);
            if (size == 0) return dev;
            dev.Preparsed = Marshal.AllocHGlobal((int)size);
            if (Native.GetRawInputDeviceInfo(hDevice, Native.RIDI_PREPARSEDDATA, dev.Preparsed, ref size) == unchecked((uint)-1))
                return dev;

            var caps = new byte[64];
            if (Native.HidP_GetCaps(dev.Preparsed, caps) != Native.HIDP_STATUS_SUCCESS) return dev;
            ushort numButtonCaps = BitConverter.ToUInt16(caps, 46);
            ushort numValueCaps = BitConverter.ToUInt16(caps, 48);

            // Valores (X, Y, Contact ID, Contact Count). HIDP_VALUE_CAPS = 72 bytes.
            var fingers = new Dictionary<ushort, Finger>();
            if (numValueCaps > 0)
            {
                var vcaps = new byte[72 * numValueCaps];
                ushort n = numValueCaps;
                if (Native.HidP_GetValueCaps(Native.HidP_Input, vcaps, ref n, dev.Preparsed) == Native.HIDP_STATUS_SUCCESS)
                {
                    for (int i = 0; i < n; i++)
                    {
                        int o = i * 72;
                        ushort page = BitConverter.ToUInt16(vcaps, o);
                        ushort link = BitConverter.ToUInt16(vcaps, o + 6);
                        bool isRange = vcaps[o + 12] != 0;
                        ushort bitSize = BitConverter.ToUInt16(vcaps, o + 18);
                        int lmin = BitConverter.ToInt32(vcaps, o + 40);
                        int lmax = BitConverter.ToInt32(vcaps, o + 44);
                        ushort umin = BitConverter.ToUInt16(vcaps, o + 56);
                        ushort umax = isRange ? BitConverter.ToUInt16(vcaps, o + 58) : umin;

                        // Algunos descriptores declaran el máximo con signo por error.
                        if (lmax <= lmin && bitSize > 0 && bitSize < 32) { lmin = 0; lmax = (1 << bitSize) - 1; }

                        Finger f;
                        if (!fingers.TryGetValue(link, out f)) { f = new Finger { Link = link, XMax = -1, YMax = -1 }; fingers[link] = f; }

                        for (int u = umin; u <= umax; u++)
                        {
                            if (page == PAGE_GENERIC && u == USAGE_X) { f.XMin = lmin; f.XMax = lmax; }
                            else if (page == PAGE_GENERIC && u == USAGE_Y) { f.YMin = lmin; f.YMax = lmax; }
                            else if (page == PAGE_DIGITIZER && u == USAGE_CONTACT_ID) f.HasId = true;
                            else if (page == PAGE_DIGITIZER && u == USAGE_CONTACT_COUNT) dev.HasContactCount = true;
                        }
                    }
                }
            }

            // Botones (Tip Switch = dedo tocando). HIDP_BUTTON_CAPS = 72 bytes.
            if (numButtonCaps > 0)
            {
                var bcaps = new byte[72 * numButtonCaps];
                ushort n = numButtonCaps;
                if (Native.HidP_GetButtonCaps(Native.HidP_Input, bcaps, ref n, dev.Preparsed) == Native.HIDP_STATUS_SUCCESS)
                {
                    for (int i = 0; i < n; i++)
                    {
                        int o = i * 72;
                        ushort page = BitConverter.ToUInt16(bcaps, o);
                        ushort link = BitConverter.ToUInt16(bcaps, o + 6);
                        bool isRange = bcaps[o + 12] != 0;
                        ushort umin = BitConverter.ToUInt16(bcaps, o + 56);
                        ushort umax = isRange ? BitConverter.ToUInt16(bcaps, o + 58) : umin;
                        Finger f;
                        if (page == PAGE_DIGITIZER && USAGE_TIP >= umin && USAGE_TIP <= umax && fingers.TryGetValue(link, out f))
                            f.HasTip = true;
                    }
                }
            }

            foreach (var f in fingers.Values)
                if (f.XMax > f.XMin && f.YMax > f.YMin) dev.Fingers.Add(f);
            dev.Fingers.Sort(delegate(Finger a, Finger b) { return a.Link.CompareTo(b.Link); });
            dev.Valid = dev.Fingers.Count > 0;
            return dev;
        }

        static string GetDeviceName(IntPtr hDevice)
        {
            uint size = 0;
            Native.GetRawInputDeviceInfo(hDevice, Native.RIDI_DEVICENAME, IntPtr.Zero, ref size);
            if (size == 0) return "?";
            IntPtr p = Marshal.AllocHGlobal((int)size * 2 + 2);
            try
            {
                Native.GetRawInputDeviceInfo(hDevice, Native.RIDI_DEVICENAME, p, ref size);
                return Marshal.PtrToStringUni(p);
            }
            finally { Marshal.FreeHGlobal(p); }
        }

        void ParseReport(IntPtr hDevice, Device dev, byte[] report)
        {
            ReportCount++;
            uint len = (uint)report.Length;
            int valid = dev.Fingers.Count;
            if (dev.HasContactCount)
            {
                uint cc;
                if (Native.HidP_GetUsageValue(Native.HidP_Input, PAGE_DIGITIZER, 0, USAGE_CONTACT_COUNT, out cc, dev.Preparsed, report, len) == Native.HIDP_STATUS_SUCCESS)
                    valid = Math.Min(valid, cc > 0 ? (int)cc : 1);
            }

            for (int i = 0; i < valid; i++)
            {
                Finger f = dev.Fingers[i];
                uint x, y;
                if (Native.HidP_GetUsageValue(Native.HidP_Input, PAGE_GENERIC, f.Link, USAGE_X, out x, dev.Preparsed, report, len) != Native.HIDP_STATUS_SUCCESS) continue;
                if (Native.HidP_GetUsageValue(Native.HidP_Input, PAGE_GENERIC, f.Link, USAGE_Y, out y, dev.Preparsed, report, len) != Native.HIDP_STATUS_SUCCESS) continue;

                bool tip = true;
                if (f.HasTip)
                {
                    tip = false;
                    uint n = (uint)usageBuf.Length;
                    if (Native.HidP_GetUsages(Native.HidP_Input, PAGE_DIGITIZER, f.Link, usageBuf, ref n, dev.Preparsed, report, len) == Native.HIDP_STATUS_SUCCESS)
                        for (int k = 0; k < n; k++) if (usageBuf[k] == USAGE_TIP) { tip = true; break; }
                }

                long id = f.Link;
                if (f.HasId)
                {
                    uint cid;
                    if (Native.HidP_GetUsageValue(Native.HidP_Input, PAGE_DIGITIZER, f.Link, USAGE_CONTACT_ID, out cid, dev.Preparsed, report, len) == Native.HIDP_STATUS_SUCCESS)
                        id = cid;
                }

                double u = ((double)x - f.XMin) / (f.XMax - f.XMin);
                double v = ((double)y - f.YMin) / (f.YMax - f.YMin);

                LastRaw = string.Format("X={0} ({1}..{2})  Y={3} ({4}..{5})  tocando={6}  id={7}",
                    x, f.XMin, f.XMax, y, f.YMin, f.YMax, tip ? "sí" : "no", id);

                // Seguimos solo al primer dedo que toca (modo un solo toque, como un mouse).
                if (lockedId < 0)
                {
                    if (tip)
                    {
                        lockedId = id; lockedDevice = hDevice;
                        Emit(TouchKind.Down, u, v);
                    }
                }
                else if (id == lockedId && hDevice == lockedDevice)
                {
                    if (tip) Emit(TouchKind.Move, u, v);
                    else { lastU = u; lastV = v; Release(); }
                }
            }
        }

        void Emit(TouchKind kind, double u, double v)
        {
            lastU = u; lastV = v;
            lastSeenTick = Environment.TickCount;
            if (Touch != null) Touch(new TouchEvent { Kind = kind, U = u, V = v });
        }

        void Release()
        {
            lockedId = -1;
            lockedDevice = IntPtr.Zero;
            if (Touch != null) Touch(new TouchEvent { Kind = TouchKind.Up, U = lastU, V = lastV });
        }

        public void Dispose()
        {
            watchdog.Stop();
            watchdog.Dispose();
            foreach (var d in devices.Values)
                if (d.Preparsed != IntPtr.Zero) Marshal.FreeHGlobal(d.Preparsed);
            devices.Clear();
            DestroyHandle();
        }
    }
}
