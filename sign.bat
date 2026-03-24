@echo off
setlocal

REM Usage:
REM   sign.bat [TARGET_EXE]
REM Example:
REM   sign.bat dist\KKBOX_Discord_RPC.exe

set "SCRIPT_DIR=%~dp0"
set "SIGNTOOL_PATH=%SCRIPT_DIR%SignTool-10.0.26100.14-x86\signtool.exe"
set "DEFAULT_TARGET=%SCRIPT_DIR%dist\KKBOX_Discord_RPC.exe"
set "TARGET=%~1"
if "%TARGET%"=="" set "TARGET=%DEFAULT_TARGET%"

if not exist "%SIGNTOOL_PATH%" (
	echo [ERROR] signtool not found: "%SIGNTOOL_PATH%"
	exit /b 1
)

if not exist "%TARGET%" (
	echo [ERROR] Target file not found: "%TARGET%"
	exit /b 1
)

echo Signing "%TARGET%" ...
"%SIGNTOOL_PATH%" sign /a /t http://timestamp.sectigo.com /fd SHA256 /v "%TARGET%"

if errorlevel 1 (
	echo [ERROR] Signing failed.
	exit /b 1
)

echo [OK] Signed successfully: "%TARGET%"
endlocal
exit /b 0
