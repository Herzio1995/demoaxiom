# TouchCal — calibrador de touch para el tótem

Programa tipo UPDD: lee el touch **en crudo** (directo del sensor, sin el mapeo de Windows),
le aplica tu calibración y vuelve a mandar el toque ya corregido. Corrige ejes invertidos,
ejes intercambiados (pantalla girada), desplazamiento y escala.

No necesita instalación: es un solo `TouchCal.exe` (usa .NET Framework 4.8, que ya viene en Windows 10/11).

## Uso rápido

1. Copia `TouchCal.exe` a la PC del tótem (por ejemplo a `C:\TouchCal\`). Mejor fuera de Google Drive.
2. Ábrelo. La primera vez aparece la pantalla de calibración:
   - Toca el centro de cada una de las 4 cruces y levanta el dedo.
   - Luego desliza el dedo: el punto azul debe quedar justo bajo tu dedo.
   - Toca **Aceptar** (o **Repetir** si no quedó bien).
3. Queda un ícono azul en la bandeja (junto al reloj). Clic derecho para el menú:
   - **Calibrar ahora** (también doble clic en el ícono o `Ctrl+Alt+C`).
   - **Calibrar cada vez que inicia**: ideal si cada vez que armas el tótem cambia la orientación.
   - **Iniciar con Windows**.
   - **Corrección rápida**: invertir X, invertir Y o intercambiar ejes sin calibrar.
   - **Monitor del tótem**: si la PC tiene varios monitores, elige el del tótem.
   - **Diagnóstico**: muestra si se detecta el touch y los valores crudos.

Para un acceso directo "Calibrar touch" en el escritorio, crea uno que apunte a:

```
"C:\TouchCal\TouchCal.exe" /calibrar
```

Si TouchCal ya está abierto, el acceso directo solo abre la calibración.

La pantalla de calibración se cancela sola a los 30 s si nadie toca (se queda la calibración anterior),
así el tótem no se queda trabado si arranca sin nadie enfrente.

## Cómo evita los toques "dobles"

Windows sigue recibiendo el touch con los ejes mal. TouchCal tiene dos niveles:

| Modo | Qué hace | Cuándo usar |
|---|---|---|
| **Normal** (por defecto) | Bloquea los clics que Windows genera desde el touch y manda el clic corregido como **mouse**. | Apps que funcionan con mouse (la mayoría de apps de escritorio, Unity, etc.). |
| **Modo exclusivo** (menú) | Apaga el touch nativo de Windows (`TouchGate=0`). Solo TouchCal genera toques. Requiere cerrar sesión o reiniciar. | Si la app es **touch-aware** (Chrome/Edge en kiosko, apps UWP) y sigue recibiendo toques invertidos, o si quieres usar la salida **Touch** para deslizar y hacer scroll. |

En modo exclusivo el touch **solo funciona mientras TouchCal está abierto**, por eso se activa
también "Iniciar con Windows". Para volver a la normalidad, desmarca el modo exclusivo en el menú y reinicia.

**Enviar toques como → Touch** manda toques reales (sirve para deslizar y hacer scroll en navegadores).
Úsalo junto con el modo exclusivo. Si Windows no permite inyectar touch, TouchCal pasa a mouse solo.

## Limitaciones

- Maneja **un dedo** a la vez (como UPDD en modo mouse). No hay pinch/zoom multitáctil.
- Sirve para touch screens que Windows reconoce como **"Pantalla táctil compatible con HID"**.
  Si tu marco touch se presenta como mouse, en Diagnóstico no saldrá ningún touch screen.
- Las pantallas de inicio de sesión/UAC de Windows no pasan por TouchCal.

## Archivos

- `src/` — código fuente C#.
- `build.bat` — compila `TouchCal.exe` (doble clic).
- Configuración guardada en `%APPDATA%\TouchCal\touchcal.ini`.
