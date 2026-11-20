@echo off
if not defined SPRITE_TOOL_PYTHON set "SPRITE_TOOL_PYTHON=C:\MSYS2\mingw64\bin\python.exe"
"%SPRITE_TOOL_PYTHON%" "%~dp0cross_axis_stage.py" "%~dp0..\arm_vector_test\checked\Arm.png" --output "%~dp0Arm_stage_04_center_cross.png"
if errorlevel 1 pause
