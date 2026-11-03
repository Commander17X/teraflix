# SPDX-License-Identifier: GPL-2.0-only
# Read-only NVIDIA device report for Windows. This script does not load a
# driver, write registers, or change boot configuration.
$ErrorActionPreference = "Continue"

$known = @{
    "2786" = "AD104 GeForce RTX 4070 (teraflix family-supported on Linux)"
    "2709" = "AD103 GeForce RTX 4070 (teraflix family-supported on Linux)"
    "2782" = "AD104 GeForce RTX 4070 Ti"
    "24B0" = "GA104GL RTX A4000 (already full-rate; not a teraflix target)"
}

Write-Output "teraflix Windows status (read-only)"
$devices = Get-CimInstance Win32_PnPEntity | Where-Object {
    $_.PNPDeviceID -match "PCI\\VEN_10DE"
}
if (-not $devices) {
    Write-Output "No NVIDIA PCI device reported by Win32_PnPEntity."
    exit 0
}
foreach ($device in $devices) {
    $id = $device.PNPDeviceID
    if ($id -match "DEV_([0-9A-F]{4})") {
        $dev = $Matches[1].ToUpper()
        $note = $known[$dev]
        if (-not $note) { $note = "not in the short Windows report; see tools/teraflix.py list" }
        Write-Output ("{0}  DEV_{1}  {2}" -f $device.Name, $dev, $note)
    } else {
        Write-Output $device.Name
    }
}
Write-Output "No change was made. The Windows unlock, if you use one, is the separate UEFI port described in windows/README.md."
exit 0
