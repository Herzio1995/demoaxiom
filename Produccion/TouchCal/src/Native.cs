using System;
using System.Runtime.InteropServices;

namespace TouchCal
{
    // Declaraciones de la API de Windows (user32 / hid.dll).
    internal static class Native
    {
        // ---------- Raw Input ----------
        public const int WM_INPUT = 0x00FF;
        public const int WM_HOTKEY = 0x0312;
        public const uint RIDEV_INPUTSINK = 0x00000100;
        public const uint RID_INPUT = 0x10000003;
        public const uint RID_HEADER = 0x10000005;
        public const uint RIDI_PREPARSEDDATA = 0x20000005;
        public const uint RIDI_DEVICENAME = 0x20000007;
        public const int RIM_TYPEHID = 2;

        [StructLayout(LayoutKind.Sequential)]
        public struct RAWINPUTDEVICE
        {
            public ushort usUsagePage;
            public ushort usUsage;
            public uint dwFlags;
            public IntPtr hwndTarget;
        }

        [StructLayout(LayoutKind.Sequential)]
        public struct RAWINPUTHEADER
        {
            public uint dwType;
            public uint dwSize;
            public IntPtr hDevice;
            public IntPtr wParam;
        }

        [DllImport("user32.dll", SetLastError = true)]
        public static extern bool RegisterRawInputDevices(RAWINPUTDEVICE[] devices, uint numDevices, uint cbSize);

        [DllImport("user32.dll", SetLastError = true)]
        public static extern uint GetRawInputData(IntPtr hRawInput, uint uiCommand, IntPtr pData, ref uint pcbSize, uint cbSizeHeader);

        [DllImport("user32.dll", SetLastError = true)]
        public static extern uint GetRawInputDeviceInfo(IntPtr hDevice, uint uiCommand, IntPtr pData, ref uint pcbSize);

        // ---------- HID parser ----------
        public const int HidP_Input = 0;
        public const int HIDP_STATUS_SUCCESS = 0x00110000;

        [DllImport("hid.dll")]
        public static extern int HidP_GetCaps(IntPtr preparsed, byte[] caps);

        [DllImport("hid.dll")]
        public static extern int HidP_GetValueCaps(int reportType, byte[] valueCaps, ref ushort length, IntPtr preparsed);

        [DllImport("hid.dll")]
        public static extern int HidP_GetButtonCaps(int reportType, byte[] buttonCaps, ref ushort length, IntPtr preparsed);

        [DllImport("hid.dll")]
        public static extern int HidP_GetUsageValue(int reportType, ushort usagePage, ushort linkCollection, ushort usage,
            out uint value, IntPtr preparsed, byte[] report, uint reportLength);

        [DllImport("hid.dll")]
        public static extern int HidP_GetUsages(int reportType, ushort usagePage, ushort linkCollection, ushort[] usageList,
            ref uint usageLength, IntPtr preparsed, byte[] report, uint reportLength);

        // ---------- Hook de mouse de bajo nivel ----------
        public const int WH_MOUSE_LL = 14;
        public delegate IntPtr LowLevelProc(int nCode, IntPtr wParam, IntPtr lParam);

        [StructLayout(LayoutKind.Sequential)]
        public struct MSLLHOOKSTRUCT
        {
            public int x;
            public int y;
            public uint mouseData;
            public uint flags;
            public uint time;
            public IntPtr dwExtraInfo;
        }

        [DllImport("user32.dll", SetLastError = true)]
        public static extern IntPtr SetWindowsHookEx(int idHook, LowLevelProc lpfn, IntPtr hMod, uint dwThreadId);

        [DllImport("user32.dll")]
        public static extern bool UnhookWindowsHookEx(IntPtr hhk);

        [DllImport("user32.dll")]
        public static extern IntPtr CallNextHookEx(IntPtr hhk, int nCode, IntPtr wParam, IntPtr lParam);

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
        public static extern IntPtr GetModuleHandle(string name);

        // ---------- SendInput (mouse) ----------
        public const uint INPUT_MOUSE = 0;
        public const uint MOUSEEVENTF_MOVE = 0x0001;
        public const uint MOUSEEVENTF_LEFTDOWN = 0x0002;
        public const uint MOUSEEVENTF_LEFTUP = 0x0004;
        public const uint MOUSEEVENTF_VIRTUALDESK = 0x4000;
        public const uint MOUSEEVENTF_ABSOLUTE = 0x8000;

        [StructLayout(LayoutKind.Sequential)]
        public struct MOUSEINPUT
        {
            public int dx;
            public int dy;
            public uint mouseData;
            public uint dwFlags;
            public uint time;
            public IntPtr dwExtraInfo;
        }

        [StructLayout(LayoutKind.Sequential)]
        public struct INPUT
        {
            public uint type;
            public MOUSEINPUT mi;
        }

        [DllImport("user32.dll", SetLastError = true)]
        public static extern uint SendInput(uint nInputs, INPUT[] inputs, int cbSize);

        // ---------- Inyección de touch ----------
        public const uint PT_TOUCH = 2;
        public const uint TOUCH_FEEDBACK_DEFAULT = 1;
        public const uint POINTER_FLAG_INRANGE = 0x00000002;
        public const uint POINTER_FLAG_INCONTACT = 0x00000004;
        public const uint POINTER_FLAG_DOWN = 0x00010000;
        public const uint POINTER_FLAG_UPDATE = 0x00020000;
        public const uint POINTER_FLAG_UP = 0x00040000;
        public const uint TOUCH_MASK_CONTACTAREA = 0x00000001;

        [StructLayout(LayoutKind.Sequential)]
        public struct POINT { public int x; public int y; }

        [StructLayout(LayoutKind.Sequential)]
        public struct RECT { public int left; public int top; public int right; public int bottom; }

        [StructLayout(LayoutKind.Sequential)]
        public struct POINTER_INFO
        {
            public uint pointerType;
            public uint pointerId;
            public uint frameId;
            public uint pointerFlags;
            public IntPtr sourceDevice;
            public IntPtr hwndTarget;
            public POINT ptPixelLocation;
            public POINT ptHimetricLocation;
            public POINT ptPixelLocationRaw;
            public POINT ptHimetricLocationRaw;
            public uint dwTime;
            public uint historyCount;
            public int InputData;
            public uint dwKeyStates;
            public ulong PerformanceCount;
            public int ButtonChangeType;
        }

        [StructLayout(LayoutKind.Sequential)]
        public struct POINTER_TOUCH_INFO
        {
            public POINTER_INFO pointerInfo;
            public uint touchFlags;
            public uint touchMask;
            public RECT rcContact;
            public RECT rcContactRaw;
            public uint orientation;
            public uint pressure;
        }

        [DllImport("user32.dll", SetLastError = true)]
        public static extern bool InitializeTouchInjection(uint maxCount, uint dwMode);

        [DllImport("user32.dll", SetLastError = true)]
        public static extern bool InjectTouchInput(uint count, POINTER_TOUCH_INFO[] contacts);

        // ---------- Varios ----------
        [DllImport("user32.dll")]
        public static extern bool RegisterHotKey(IntPtr hWnd, int id, uint fsModifiers, uint vk);

        [DllImport("user32.dll")]
        public static extern bool UnregisterHotKey(IntPtr hWnd, int id);

        [DllImport("user32.dll")]
        public static extern bool SetProcessDPIAware();

        [DllImport("user32.dll")]
        public static extern bool SetProcessDpiAwarenessContext(IntPtr value);

        // Coordenadas en píxeles físicos en todos los monitores (Per-Monitor V2).
        public static void MakeDpiAware()
        {
            try
            {
                if (SetProcessDpiAwarenessContext(new IntPtr(-4))) return;
            }
            catch (EntryPointNotFoundException) { }
            try { SetProcessDPIAware(); } catch { }
        }
    }
}
