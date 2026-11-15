using System;
using System.Drawing;
using System.Runtime.InteropServices;
using System.Windows.Forms;

namespace TouchCal
{
    // - Hook de mouse: descarta los clics "falsos" que Windows genera desde el touch
    //   (con los ejes mal), para que no lleguen a las aplicaciones.
    // - Salida: vuelve a mandar el toque ya corregido, como mouse o como touch.
    public sealed class Injector : IDisposable
    {
        // Firma que Windows pone en dwExtraInfo de los eventos de mouse generados por touch.
        const long TOUCH_SIGNATURE_MASK = 0xFFFFFF80;
        const long TOUCH_SIGNATURE = 0xFF515780;
        static readonly IntPtr OUR_TAG = new IntPtr(0x54434C42); // "TCLB"

        readonly Native.LowLevelProc hookProc;
        IntPtr hook;
        bool down;
        bool touchReady, touchFailed;
        Point lastPt;
        readonly Timer keepAlive;

        public Func<bool> ShouldBlockNativeTouch = delegate { return false; };
        public int BlockedCount;

        public Injector()
        {
            hookProc = HookCallback; // mantener referencia para que el GC no lo recoja
            hook = Native.SetWindowsHookEx(Native.WH_MOUSE_LL, hookProc, Native.GetModuleHandle(null), 0);

            // El touch inyectado se cancela si no se actualiza; lo refrescamos mientras hay dedo.
            keepAlive = new Timer { Interval = 50 };
            keepAlive.Tick += delegate { if (down && touchReady && !touchFailed) InjectTouch(lastPt, Native.POINTER_FLAG_UPDATE | Native.POINTER_FLAG_INRANGE | Native.POINTER_FLAG_INCONTACT); };
            keepAlive.Start();
        }

        public bool HookInstalled { get { return hook != IntPtr.Zero; } }
        public bool TouchOutputFailed { get { return touchFailed; } }

        IntPtr HookCallback(int nCode, IntPtr wParam, IntPtr lParam)
        {
            if (nCode >= 0)
            {
                var info = (Native.MSLLHOOKSTRUCT)Marshal.PtrToStructure(lParam, typeof(Native.MSLLHOOKSTRUCT));
                long extra = info.dwExtraInfo.ToInt64() & 0xFFFFFFFF;
                if ((extra & TOUCH_SIGNATURE_MASK) == TOUCH_SIGNATURE && ShouldBlockNativeTouch())
                {
                    BlockedCount++;
                    return new IntPtr(1); // descartar
                }
            }
            return Native.CallNextHookEx(hook, nCode, wParam, lParam);
        }

        public void Send(TouchKind kind, PointF p, bool asTouch)
        {
            Rectangle vs = SystemInformation.VirtualScreen;
            var pt = new Point(
                Math.Max(vs.Left, Math.Min(vs.Right - 1, (int)Math.Round(p.X))),
                Math.Max(vs.Top, Math.Min(vs.Bottom - 1, (int)Math.Round(p.Y))));
            lastPt = pt;

            if (asTouch && !touchFailed)
            {
                uint flags;
                if (kind == TouchKind.Down) flags = Native.POINTER_FLAG_DOWN | Native.POINTER_FLAG_INRANGE | Native.POINTER_FLAG_INCONTACT;
                else if (kind == TouchKind.Move) flags = Native.POINTER_FLAG_UPDATE | Native.POINTER_FLAG_INRANGE | Native.POINTER_FLAG_INCONTACT;
                else flags = Native.POINTER_FLAG_UP;

                if (kind == TouchKind.Down || down)
                {
                    if (InjectTouch(pt, flags)) { down = kind != TouchKind.Up; return; }
                    touchFailed = true; // sin soporte: seguimos con mouse
                }
            }
            SendMouse(kind, pt, vs);
        }

        void SendMouse(TouchKind kind, Point pt, Rectangle vs)
        {
            var input = new Native.INPUT[1];
            input[0].type = Native.INPUT_MOUSE;
            input[0].mi.dx = (int)((pt.X - vs.Left) * 65535.0 / Math.Max(1, vs.Width - 1));
            input[0].mi.dy = (int)((pt.Y - vs.Top) * 65535.0 / Math.Max(1, vs.Height - 1));
            input[0].mi.dwExtraInfo = OUR_TAG;
            uint flags = Native.MOUSEEVENTF_MOVE | Native.MOUSEEVENTF_ABSOLUTE | Native.MOUSEEVENTF_VIRTUALDESK;
            if (kind == TouchKind.Down) flags |= Native.MOUSEEVENTF_LEFTDOWN;
            if (kind == TouchKind.Up && down) flags |= Native.MOUSEEVENTF_LEFTUP;
            input[0].mi.dwFlags = flags;
            Native.SendInput(1, input, Marshal.SizeOf(typeof(Native.INPUT)));
            down = kind != TouchKind.Up;
        }

        bool InjectTouch(Point pt, uint flags)
        {
            if (!touchReady)
            {
                try { touchReady = Native.InitializeTouchInjection(1, Native.TOUCH_FEEDBACK_DEFAULT); }
                catch (EntryPointNotFoundException) { touchReady = false; }
                if (!touchReady) return false;
            }
            var c = new Native.POINTER_TOUCH_INFO[1];
            c[0].pointerInfo.pointerType = Native.PT_TOUCH;
            c[0].pointerInfo.pointerId = 0;
            c[0].pointerInfo.pointerFlags = flags;
            c[0].pointerInfo.ptPixelLocation.x = pt.X;
            c[0].pointerInfo.ptPixelLocation.y = pt.Y;
            c[0].touchMask = Native.TOUCH_MASK_CONTACTAREA;
            c[0].rcContact.left = pt.X - 2; c[0].rcContact.right = pt.X + 2;
            c[0].rcContact.top = pt.Y - 2; c[0].rcContact.bottom = pt.Y + 2;
            return Native.InjectTouchInput(1, c);
        }

        // Suelta cualquier clic/toque pendiente (al desactivar o salir).
        public void ReleaseAll()
        {
            if (down) Send(TouchKind.Up, lastPt, touchReady && !touchFailed);
            down = false;
        }

        public void Dispose()
        {
            ReleaseAll();
            keepAlive.Stop();
            keepAlive.Dispose();
            if (hook != IntPtr.Zero) { Native.UnhookWindowsHookEx(hook); hook = IntPtr.Zero; }
        }
    }
}
