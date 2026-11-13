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
    # Run the package beside this file with `-m`. An inline `-c` program cannot be
    # used here: Windows PowerShell 5.1 drops the double quotes inside an argument
    # to a native program, which turned the module name into a bare identifier.
    $previousPath = $env:PYTHONPATH
    $env:PYTHONPATH = if ($previousPath) { $PSScriptRoot + [IO.Path]::PathSeparator + $previousPath } else { $PSScriptRoot }
    try {
        # -P keeps the current directory off the import path, so a folder named
        # mcforge in the caller's working directory cannot shadow this one.
        & $pythonCandidate -P -m mcforge @args
        $code = $LASTEXITCODE
    } finally {
        $env:PYTHONPATH = $previousPath
    }
    exit $code
}
throw 'Python 3.11+ is required. Set UABS_PYTHON to your existing Python executable; see README.md.'
