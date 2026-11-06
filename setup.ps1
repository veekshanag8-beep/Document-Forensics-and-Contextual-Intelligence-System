# One-time setup on Windows (PowerShell):  powershell -ExecutionPolicy Bypass -File setup.ps1
$ErrorActionPreference = "Stop"
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# onnxruntime needs a recent Visual C++ runtime. Machines with an old system runtime crash on import,
# so ship the runtime DLLs next to onnxruntime inside the venv (no system-wide changes).
.\.venv\Scripts\python.exe -m pip install msvc-runtime
$venv = (Resolve-Path .\.venv).Path
$capi = "$venv\Lib\site-packages\onnxruntime\capi"
$base = & .\.venv\Scripts\python.exe -c "import sys;print(sys.base_prefix)"
Copy-Item "$venv\*140*.dll" $capi -ErrorAction SilentlyContinue
Copy-Item "$base\vcruntime140*.dll" $capi -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -c "import app; import onnxruntime; print('onnxruntime OK')"

# Demonstration dataset (genuine + manipulated synthetic documents, with ground truth)
.\.venv\Scripts\python.exe -m datagen.generate
Write-Host "Setup complete. Start with: .\run.ps1"
