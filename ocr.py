"""Screenshot OCR via the built-in Windows OCR engine (PowerShell/WinRT).

No third-party dependencies: the raw BGRA pixels are handed to
Windows.Media.Ocr through a small PowerShell helper script. Requires the
Windows OCR language pack for the target language (Settings > Time &
Language > Language).
"""

import os
import subprocess
import sys
import tempfile

_POWERSHELL = os.path.join(
    os.environ.get("SystemRoot", r"C:\Windows"),
    "System32",
    "WindowsPowerShell",
    "v1.0",
    "powershell.exe",
)

_PS_SCRIPT = r"""
param(
    [Parameter(Mandatory=$true)][string]$RawPath,
    [Parameter(Mandatory=$true)][int]$Width,
    [Parameter(Mandatory=$true)][int]$Height,
    [Parameter(Mandatory=$true)][string]$OutPath
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Runtime.WindowsRuntime

$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.SoftwareBitmap, Windows.Graphics.Imaging, ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapPixelFormat, Windows.Graphics.Imaging, ContentType=WindowsRuntime]

function Await($op, $resultType) {
    $m = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
        $_.Name -eq "AsTask" -and $_.IsGenericMethodDefinition -and
        $_.GetParameters().Count -eq 1 -and
        $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
    } | Select-Object -First 1
    if ($null -eq $m) { throw "AsTask(IAsyncOperation<T>) helper not found" }
    $task = $m.MakeGenericMethod($resultType).Invoke($null, @($op))
    $task.Wait()
    if ($task.IsFaulted) { throw $task.Exception }
    return $task.Result
}

try {
    $bytes = [System.IO.File]::ReadAllBytes($RawPath)
    $expected = [int64]$Width * [int64]$Height * 4
    if ($bytes.Length -lt $expected) {
        throw "raw size $($bytes.Length) < expected $expected"
    }
    $buffer = [System.Runtime.InteropServices.WindowsRuntime.WindowsRuntimeBufferExtensions]::AsBuffer($bytes)

    $bitmap = [Windows.Graphics.Imaging.SoftwareBitmap]::new(
        [Windows.Graphics.Imaging.BitmapPixelFormat]::Bgra8, $Width, $Height)
    $bitmap.CopyFromBuffer($buffer)

    $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
    if ($null -eq $engine) {
        [System.IO.File]::WriteAllText($OutPath, "")
        exit 3
    }
    $result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
    $text = ""
    if ($null -ne $result) { $text = $result.Text }
    [System.IO.File]::WriteAllText($OutPath, $text)
    exit 0
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}
"""


class OcrError(Exception):
    pass


def available() -> bool:
    return sys.platform == "win32" and os.path.isfile(_POWERSHELL)


def _script_path() -> str:
    path = os.path.join(tempfile.gettempdir(), "textmate_ai_ocr.ps1")
    try:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(_PS_SCRIPT)
        return path
    except OSError:
        fd, alt = tempfile.mkstemp(prefix="textmate_ocr_", suffix=".ps1")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(_PS_SCRIPT)
        return alt


def _mkstemp(suffix=".raw"):
    return tempfile.mkstemp(prefix="textmate_ocr_", suffix=suffix)


def recognize(image, timeout: float = 60.0) -> str:
    """Run Windows OCR on a PIL image and return the recognized text."""
    if not available():
        raise OcrError("OCR needs Windows with PowerShell available.")
    try:
        rgba = image.convert("RGBA")
    except Exception as exc:
        raise OcrError(f"cannot convert image: {exc}") from exc
    data = bytearray(rgba.tobytes())
    # RGBA -> BGRA byte order for SoftwareBitmap(Bgra8)
    data[0::4], data[2::4] = data[2::4], data[0::4]
    width, height = rgba.size
    if width < 1 or height < 1:
        raise OcrError("empty image region")

    raw_fd, raw_path = _mkstemp(suffix=".raw")
    out_fd, out_path = _mkstemp(suffix=".txt")
    os.close(out_fd)
    try:
        with os.fdopen(raw_fd, "wb") as fh:
            fh.write(data)
        proc = subprocess.run(
            [
                _POWERSHELL,
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                _script_path(),
                "-RawPath",
                raw_path,
                "-Width",
                str(width),
                "-Height",
                str(height),
                "-OutPath",
                out_path,
            ],
            capture_output=True,
            timeout=timeout,
        )
        text = ""
        if os.path.isfile(out_path):
            with open(out_path, "r", encoding="utf-8-sig", errors="replace") as fh:
                text = fh.read()
        if proc.returncode == 3:
            raise OcrError(
                "No OCR language installed. Add one in Windows Settings â†’ "
                "Time & Language â†’ Language (e.g. English)."
            )
        if proc.returncode != 0:
            detail = (proc.stderr or b"").decode("utf-8", "replace").strip()
            raise OcrError(detail or f"OCR failed (exit {proc.returncode})")
        return text.strip()
    except subprocess.TimeoutExpired as exc:
        raise OcrError("OCR timed out") from exc
    finally:
        for path in (raw_path, out_path):
            try:
                os.remove(path)
            except OSError:
                pass
