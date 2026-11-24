# Local launcher: prefer the installed Python; fall back to Codex's bundled 3.12.
$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
$videoPython = if ($pythonCommand -and $pythonCommand.Source -notlike '*Microsoft\WindowsApps*') { $pythonCommand.Source } else { $null }
if (-not $videoPython) {
    $candidate = Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
    if (Test-Path -LiteralPath $candidate) { $videoPython = $candidate }
}
if (-not $videoPython) { throw 'Python 3.12 is required. Install it or restore the Codex runtime.' }
& $videoPython -X utf8 (Join-Path $PSScriptRoot 'video.py') @args
exit $LASTEXITCODE
