<#
.SYNOPSIS
    TrackGuard Hardware Attack Demonstration Runner
.DESCRIPTION
    Launches interactive or automated hardware attack injection against TrackGuard live backend.
.EXAMPLE
    .\demonstrate_hardware_attacks.ps1
    .\demonstrate_hardware_attacks.ps1 -Attack location_jump
    .\demonstrate_hardware_attacks.ps1 -DemoAll
#>

param(
    [string]$Attack,
    [switch]$DemoAll,
    [string]$ApiUrl = "http://localhost:5001"
)

$PythonExe = "C:\Users\rahul\anaconda3\python.exe"
$ScriptPath = Join-Path $PSScriptRoot "scripts\demonstrate_hardware_attacks.py"

if (-not (Test-Path $ScriptPath)) {
    $ScriptPath = Join-Path $PSScriptRoot "demonstrate_hardware_attacks.py"
}

if ($Attack) {
    & $PythonExe $ScriptPath --attack $Attack --api $ApiUrl
}
elseif ($DemoAll) {
    & $PythonExe $ScriptPath --demo-all --api $ApiUrl
}
else {
    & $PythonExe $ScriptPath --interactive --api $ApiUrl
}
