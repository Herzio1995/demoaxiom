@echo off
rem Compila TouchCal.exe con el compilador de C# que ya trae Windows (.NET Framework 4.x).
setlocal
cd /d "%~dp0"
set CSC=%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe
if not exist "%CSC%" set CSC=%WINDIR%\Microsoft.NET\Framework\v4.0.30319\csc.exe
if not exist "%CSC%" (
  echo No se encontro csc.exe de .NET Framework 4.
  exit /b 1
)
"%CSC%" /nologo /target:winexe /platform:anycpu /optimize+ /out:TouchCal.exe ^
  /r:System.dll /r:System.Drawing.dll /r:System.Windows.Forms.dll ^
  src\*.cs
if errorlevel 1 (
  echo.
  echo *** Error de compilacion ***
  exit /b 1
)
echo Listo: %~dp0TouchCal.exe
