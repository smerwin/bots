@echo off
REM Build tree_walker.exe with MSVC.
REM
REM The macOS twin is one clang line in CLAUDE.md; this is the same idea with
REM vcvarsall in front of it, because cl.exe needs its environment set up and
REM the Build Tools do not put it on PATH.
REM
REM /O2 matters here rather than being habit: the whole reason this program
REM exists is that the Python walker's cost is interpreter overhead, so a debug
REM build would give back much of what it is meant to win.

setlocal

REM Known Build Tools locations, newest first. Deliberately a plain list rather
REM than a vswhere query: vswhere lives under a path containing "(x86)", and
REM getting that through cmd's parser reliably is more trouble than it is worth
REM for a two-line lookup that this list already answers.
set VCVARS=C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvarsall.bat
if exist "%VCVARS%" goto :found
set VCVARS=C:\Program Files\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvarsall.bat
if exist "%VCVARS%" goto :found
set VCVARS=C:\Program Files (x86)\Microsoft Visual Studio\2019\BuildTools\VC\Auxiliary\Build\vcvarsall.bat
if exist "%VCVARS%" goto :found
set VCVARS=C:\Program Files (x86)\Microsoft Visual Studio\2019\Community\VC\Auxiliary\Build\vcvarsall.bat
if exist "%VCVARS%" goto :found

:nocompiler
echo Could not find vcvarsall.bat. Install the VS Build Tools with the C++ workload:
echo   winget install Microsoft.VisualStudio.2022.BuildTools
echo The host runs without this -- it falls back to the Python walker, ~8.7x slower.
exit /b 1

:found
call "%VCVARS%" x64 >nul || exit /b 1

REM _CRT_SECURE_NO_WARNINGS: this uses strncpy with explicit bounds throughout,
REM and the _s variants are not portable back to the macOS file this mirrors.
cl /nologo /O2 /W3 /DNDEBUG /D_CRT_SECURE_NO_WARNINGS ^
   "%~dp0tree_walker.c" /Fe:"%~dp0tree_walker.exe" /Fo:"%~dp0tree_walker.obj" ^
   kernel32.lib || exit /b 1

del "%~dp0tree_walker.obj" >nul 2>&1
echo built %~dp0tree_walker.exe
