# Portable CLI launcher. Reuses the shared Python; never changes PATH or AI config.
# Arguments are forwarded as data. Output/logging belong to the selected command.
$ErrorActionPreference = 'Stop'
$pythonCandidates = @($env:UABS_PYTHON)
foreach ($pythonBase in @((Join-Path $env:LOCALAPPDATA 'Python'), (Join-Path $env:USERPROFILE 'AppData\Local\Python'))) {
    if (Test-Path -LiteralPath $pythonBase -PathType Container) {
        $pythonCandidates += Get-ChildItem -LiteralPath $pythonBase -Directory -Filter 'pythoncore-*' |
            Sort-Object Name -Descending | ForEach-Object { Join-Path $_.FullName 'python.exe' }
    }
}
$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
if ($pythonCommand) { $pythonCandidates += $pythonCommand.Source }
foreach ($pythonCandidate in ($pythonCandidates | Where-Object { $_ } | Select-Object -Unique)) {
    if (-not (Test-Path -LiteralPath $pythonCandidate -PathType Leaf)) { continue }
    try {
        & $pythonCandidate -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)' 2>$null
        if ($LASTEXITCODE -ne 0) { continue }
    } catch { continue }
    & $pythonCandidate -c 'import sys,runpy; sys.path.insert(0,sys.argv.pop(1)); runpy.run_module("mcforge",run_name="__main__")' $PSScriptRoot @args
    exit $LASTEXITCODE
}
throw 'Python 3.11+ is required. Set UABS_PYTHON to your existing Python executable; see README.md.'
