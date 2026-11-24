param(
    [Parameter(Mandatory=$true)]
    [string]$RemoteUrl
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Test-Path .git)) {
    git init -b main
}
git add -A
git commit -m "Lab 5: Thread-safe Bounded Priority Queue C4 (Variant 24)" --allow-empty
git remote remove origin 2>$null
git remote add origin $RemoteUrl
git branch -M main
git push -u origin main
