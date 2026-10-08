$ErrorActionPreference = 'Stop'
$repo = $PSScriptRoot
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    $env:Path = "$HOME\.local\bin;$env:Path"
}
$env:PYTHONPATH = "$repo$([IO.Path]::PathSeparator)$(Join-Path $repo 'src')"
$env:PYTHONUTF8 = '1'
& uv run --no-project --directory $repo --python '3.12' python -m installer @args
exit $LASTEXITCODE
