@echo off
chcp 65001 >nul
set PYTHONUTF8=1
echo.
echo === ACF EXE Build ===
pip install -r requirements.txt -q
python -m PyInstaller --onefile --windowed --name ACFPredictor --hidden-import tkinter --hidden-import tkinter.ttk --hidden-import tkinter.scrolledtext --hidden-import sklearn.utils._cython_blas --hidden-import sklearn.neighbors._partition_nodes --hidden-import sklearn.tree._utils --hidden-import sklearn.tree._criterion --hidden-import sklearn.tree._splitter --hidden-import scipy.special._comb --hidden-import scipy.linalg.blas --hidden-import scipy.linalg.lapack --hidden-import matplotlib --hidden-import matplotlib.backends.backend_agg --hidden-import matplotlib.backends.backend_tkagg --collect-all sklearn --collect-all scipy --collect-all xgboost --collect-all matplotlib main_gui.py
if errorlevel 1 ( echo Build FAILED & pause & exit /b 1 )
echo.
echo BUILD COMPLETE: dist\ACFPredictor.exe
pause