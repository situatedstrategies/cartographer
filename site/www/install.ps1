# Cartographer installer for Windows · https://codecartographer.dev
#
#   irm https://codecartographer.dev/install.ps1 | iex
#   & ([scriptblock]::Create((irm https://codecartographer.dev/install.ps1))) -All -Auto
#
# What it does: downloads Cartographer into ~\.cartographer\app, writes a `cartographer` command into
# ~\.local\bin (added to your PATH), and puts /wrap, /replay, /complete and /cartographer-setup into
# Claude Code (~\.claude\skills). Nothing runs in the background unless you pass -Auto.
# Needs: Python 3.9 or newer (winget install Python.Python.3.12, or python.org with "Add to PATH" ticked).
param([switch]$All, [switch]$Auto, [switch]$Manual)
$ErrorActionPreference = "Stop"
$site = if ($env:CARTOGRAPHER_SITE) { $env:CARTOGRAPHER_SITE } else { "https://codecartographer.dev" }

function Test-Python($exe, $flags) {
  try { $out = & $exe @flags -c "import sys; print(sys.version_info >= (3, 9))" 2>$null; return ("$out" -match "True") } catch { return $false }
}
$pyExe = $null; $pyFlags = @()
foreach ($c in @(@("py", @("-3")), @("python", @()), @("python3", @()))) {
  if (Test-Python $c[0] $c[1]) { $pyExe = $c[0]; $pyFlags = $c[1]; break }
}
if (-not $pyExe) {
  Write-Host ""
  Write-Host "Python 3.9 or newer is required and was not found." -ForegroundColor Yellow
  Write-Host "Install it with:   winget install Python.Python.3.12"
  Write-Host "(or from python.org, ticking 'Add python.exe to PATH'), open a new PowerShell, and run this again."
  exit 1
}

$tmp = Join-Path ([IO.Path]::GetTempPath()) ("cartographer-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $tmp | Out-Null
try {
  Write-Host ""; Write-Host "Downloading Cartographer" -ForegroundColor Cyan
  if ($env:CARTOGRAPHER_ZIP) { Expand-Archive -Path $env:CARTOGRAPHER_ZIP -DestinationPath $tmp }
  else {
    Invoke-WebRequest -Uri "$site/cartographer.zip" -OutFile (Join-Path $tmp "cartographer.zip")
    Expand-Archive -Path (Join-Path $tmp "cartographer.zip") -DestinationPath $tmp
  }
  $src = Join-Path $tmp "cartographer"
  if (-not (Test-Path (Join-Path $src "bin\cartographer"))) { throw "the download did not contain Cartographer (no bin\cartographer)" }

  $agents = if ($All) { "all" } else { "claude-code" }
  $extra = @(); if ($Auto) { $extra += "--auto" }; if ($Manual) { $extra += "--manual" }
  Write-Host ""; Write-Host "Installing into ~\.cartographer\app and Claude Code" -ForegroundColor Cyan
  & $pyExe @pyFlags (Join-Path $src "bin\cartographer") install --agent $agents @extra
  if ($LASTEXITCODE -ne 0) { throw "install exited with code $LASTEXITCODE" }

  $bin = Join-Path $HOME ".local\bin"
  $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
  if (-not (($userPath -split ";") -contains $bin)) {
    [Environment]::SetEnvironmentVariable("Path", (($userPath.TrimEnd(";")) + ";" + $bin), "User")
    $env:Path += ";" + $bin
    Write-Host "Added $bin to your PATH. Open a new terminal for it to apply everywhere."
  }
} finally {
  Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
}

Write-Host ""; Write-Host "Done. Next:" -ForegroundColor Green
Write-Host "  cartographer serve --open     # your dashboard: profile, sessions, maps (this machine only)"
Write-Host "  /wrap                         # in Claude Code, at the end of a session"
Write-Host "  cartographer doctor           # what is installed and where"
Write-Host ""
