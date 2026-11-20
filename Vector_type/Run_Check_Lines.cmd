@echo off
setlocal
cd /d "%~dp0"
title Sprite Projection Line Checker

rem Override SPRITE_TOOL_PYTHON if MSYS2 is installed elsewhere.
if not defined SPRITE_TOOL_PYTHON set "SPRITE_TOOL_PYTHON=C:\MSYS2\mingw64\bin\python.exe"

if not exist "%SPRITE_TOOL_PYTHON%" goto :python_missing
"%SPRITE_TOOL_PYTHON%" -c "from PIL import Image; print('Pillow ready')" >nul 2>nul
if errorlevel 1 goto :pillow_missing

:menu
cls
echo ==========================================
echo   Sprite Projection Line Checker
echo ==========================================
echo File history: FILE_LIST.txt
echo 1. Full check - process check\ PNGs and generate asset projections
echo 2. Choose another PNG
echo 3. Make sprite template
echo 4. Return All - restore checked files and delete error files
echo 5. Make vector / head option (Vector.py)
echo 0. Exit
echo.
choice /c 123450 /n /m "Select an option: "
if errorlevel 6 goto :end
if errorlevel 5 goto :make_vector_head
if errorlevel 4 goto :return_all
if errorlevel 3 goto :make_template
if errorlevel 2 goto :custom
goto :run_batch

:cancel_selection
echo.
echo Configuration canceled. Returning to menu...
timeout /t 1 /nobreak >nul
goto :menu

:run_batch
"%SPRITE_TOOL_PYTHON%" "%~dp0check_lines.py" --batch --check-dir "%~dp0check" --checked-dir "%~dp0checked" --errors-dir "%~dp0errors"
set "CHECK_EXIT_CODE=%ERRORLEVEL%"
if not "%CHECK_EXIT_CODE%"=="0" (
    echo.
    echo Full check stopped with code %CHECK_EXIT_CODE%; asset generation was skipped.
    pause
    goto :menu
)
echo.
echo Generating asset projections from checked PNG files...
"%SPRITE_TOOL_PYTHON%" "%~dp0Vector_assets.py"
set "ASSET_VECTOR_EXIT_CODE=%ERRORLEVEL%"
if not "%ASSET_VECTOR_EXIT_CODE%"=="0" echo Asset projection stopped with code %ASSET_VECTOR_EXIT_CODE%. See the Python messages above.
echo.
pause
goto :menu

:make_template
"%SPRITE_TOOL_PYTHON%" "%~dp0check_lines.py" --make-template
set "TEMPLATE_EXIT_CODE=%ERRORLEVEL%"
if "%TEMPLATE_EXIT_CODE%"=="10" goto :cancel_selection
if not "%TEMPLATE_EXIT_CODE%"=="0" echo Template creation stopped with code %TEMPLATE_EXIT_CODE%.
echo.
pause
goto :menu

:make_vector_head
set "SPRITE_SIZE_INPUT="
set /p "SPRITE_SIZE_INPUT=Sprite size in pixels (16-512; Enter=128; C=cancel): "
if /i "%SPRITE_SIZE_INPUT%"=="C" goto :cancel_selection
if not defined SPRITE_SIZE_INPUT set "SPRITE_SIZE_INPUT=128"
set "VECTOR_COLS_INPUT="
set /p "VECTOR_COLS_INPUT=Columns (1-100; Enter=5; total cells <=100; C=cancel): "
if /i "%VECTOR_COLS_INPUT%"=="C" goto :cancel_selection
if not defined VECTOR_COLS_INPUT set "VECTOR_COLS_INPUT=5"
set "VECTOR_ROWS_INPUT="
set /p "VECTOR_ROWS_INPUT=Rows (1-100; Enter=5; total cells <=100; C=cancel): "
if /i "%VECTOR_ROWS_INPUT%"=="C" goto :cancel_selection
if not defined VECTOR_ROWS_INPUT set "VECTOR_ROWS_INPUT=5"
"%SPRITE_TOOL_PYTHON%" "%~dp0Vector.py" --size "%SPRITE_SIZE_INPUT%" --cols "%VECTOR_COLS_INPUT%" --rows "%VECTOR_ROWS_INPUT%"
set "VECTOR_HEAD_EXIT_CODE=%ERRORLEVEL%"
if not "%VECTOR_HEAD_EXIT_CODE%"=="0" echo Vector head generation stopped with code %VECTOR_HEAD_EXIT_CODE%.
echo.
pause
goto :menu

:return_all
"%SPRITE_TOOL_PYTHON%" "%~dp0check_lines.py" --return-all --check-dir "%~dp0check" --checked-dir "%~dp0checked" --errors-dir "%~dp0errors"
set "RETURN_ALL_EXIT_CODE=%ERRORLEVEL%"
if "%RETURN_ALL_EXIT_CODE%"=="10" goto :cancel_selection
if not "%RETURN_ALL_EXIT_CODE%"=="0" echo Return All stopped with code %RETURN_ALL_EXIT_CODE%.
echo.
pause
goto :menu

:custom
set "INPUT_PATH="
set /p "INPUT_PATH=PNG path (relative or absolute; C=cancel; no quotes): "
if /i "%INPUT_PATH%"=="C" goto :cancel_selection
if not defined INPUT_PATH goto :menu

:run
if not exist "%INPUT_PATH%" (
    echo.
    echo File not found: %INPUT_PATH%
    pause
    goto :menu
)
set "OUTPUT_PATH="
set /p "OUTPUT_PATH=Output path (Enter uses automatic name; C=cancel): "
if /i "%OUTPUT_PATH%"=="C" goto :cancel_selection
echo.
if defined OUTPUT_PATH (
    "%SPRITE_TOOL_PYTHON%" "%~dp0check_lines.py" "%INPUT_PATH%" --output "%OUTPUT_PATH%"
) else (
    "%SPRITE_TOOL_PYTHON%" "%~dp0check_lines.py" "%INPUT_PATH%"
)
echo.
pause
goto :menu

:python_missing
echo Python was not found at:
echo %SPRITE_TOOL_PYTHON%
echo Set SPRITE_TOOL_PYTHON to your MSYS2 mingw64 Python path and try again.
pause
goto :end

:pillow_missing
echo Pillow is unavailable in:
echo %SPRITE_TOOL_PYTHON%
echo Install Pillow for this MSYS2 Python, then try again.
pause

:end
endlocal
