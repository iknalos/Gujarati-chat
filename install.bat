@echo off
REM GujaratiClaude — one-time install script for Windows.
REM
REM Prerequisites you must have installed yourself BEFORE running this:
REM   * Python 3.10 (other 3.x may work; 3.10 is the tested target)
REM   * Claude Code authenticated:  `claude auth status` should exit 0
REM   * (Optional but strongly recommended) NVIDIA GPU with CUDA 12.x drivers
REM
REM This script:
REM   1. Creates a venv at .\venv
REM   2. Installs torch with the CUDA 12.1 index (if no GPU, edit below)
REM   3. Installs the rest of requirements.txt
REM   4. Converts the vasista22 Gujarati Whisper to CTranslate2 format
REM   5. Downloads the IndicF5 weights from HuggingFace
REM   6. Reminds you to drop your trained openWakeWord "Claude" ONNX in models\
REM
REM Re-running is safe — each step is idempotent.

setlocal enabledelayedexpansion
cd /d "%~dp0"

echo === Step 1/5: Python venv ===
if not exist venv (
  python -m venv venv || goto :error
)
call venv\Scripts\activate.bat || goto :error
python -m pip install --upgrade pip wheel

echo === Step 2/5: PyTorch (CUDA 12.1) ===
REM If you have no NVIDIA GPU, change "cu121" to "cpu" below.
pip install torch --index-url https://download.pytorch.org/whl/cu121 || goto :error
pip install onnxruntime-gpu || pip install onnxruntime

echo === Step 3/5: Project dependencies ===
pip install -r requirements.txt || goto :error

echo === Step 4/5: Convert Whisper Gujarati to CTranslate2 ===
if not exist models\whisper-gujarati-ct2\model.bin (
  ct2-transformers-converter ^
    --model vasista22/whisper-gujarati-medium ^
    --output_dir models\whisper-gujarati-ct2 ^
    --copy_files tokenizer.json preprocessor_config.json ^
    --quantization int8_float16 || goto :error
) else (
  echo   already converted, skipping.
)

echo === Step 5/5: IndicF5 weights ===
if not exist models\indic_f5\config.json (
  python -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='ai4bharat/IndicF5', local_dir='models/indic_f5')" || goto :error
) else (
  echo   already downloaded, skipping.
)

echo.
echo ========================================================
echo Install complete. Two manual steps remain:
echo.
echo  1. Train a "Claude" wake word in the openWakeWord Colab
echo     notebook (about 1 hour, free tier) and save the resulting
echo     .onnx as:   models\claude_wakeword.onnx
echo     Until then, run `launch.bat --no-wake` and click "Wake".
echo.
echo  2. Drop a clean 5-10s Gujarati reference clip + transcript at:
echo        prompts\gu_reference.wav
echo        prompts\gu_reference.txt
echo     Voice character of TTS output is cloned from this clip.
echo ========================================================
goto :eof

:error
echo.
echo INSTALL FAILED at the step above. See error output for details.
exit /b 1
