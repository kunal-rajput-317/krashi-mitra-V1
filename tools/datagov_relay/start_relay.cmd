@echo off
rem Starts the data.gov.in relay and its Cloudflare tunnel (relay.krashimitra.in),
rem each in its own minimised window. Double-click after a PC restart; see
rem README.md, "Permanent tunnel on the PC".
rem Each window restarts its program if it exits, so a tunnel started before the
rem network is up (right after boot) reconnects by itself instead of staying
rem down until someone notices the mandi fetch failing with HTTP 530.
if "%~1"=="relay" goto relay
if "%~1"=="tunnel" goto tunnel
start "data.gov.in relay" /min "%~f0" relay
start "relay tunnel" /min "%~f0" tunnel
exit /b

:relay
cd /d "%~dp0\..\.."
python tools\datagov_relay\local_relay.py
timeout /t 15 /nobreak >nul
goto relay

:tunnel
"%USERPROFILE%\cloudflared\cloudflared.exe" tunnel --no-autoupdate run krashimitra-relay
timeout /t 15 /nobreak >nul
goto tunnel
