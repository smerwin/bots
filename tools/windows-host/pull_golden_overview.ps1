<#
.SYNOPSIS
  Pull Greta Gneiss's overview settings from the dmc-mpc-001 network share
  into this machine's local golden file, then (re)link a given set of local
  characters to it.

  Run this on each target machine (002, 003, 004).

  REFUSES TO RUN WHILE ANY EVE CLIENT IS UP. The golden file's bytes are
  rewritten in place, and in place means every hardlinked character at once --
  including one that is logged in and will write its own settings back over
  the top on logout. See eve_clients_running.ps1 for why there is no override.
  Stop the sessions and log the clients out first.

.PARAMETER ShareRoot
  Where the staged golden file lives. Defaults to the UNC path from
  SHARE_GOLDEN_SETTINGS_on_001.md.

.PARAMETER CharacterIds
  Local character ids to link to the refreshed golden file, in addition to
  refreshing it. Leave empty to only refresh the golden file's content
  without touching any links (e.g. on a machine where the group is already
  set up and only a content refresh is wanted).

.PARAMETER GoldenCharacterId
  Greta Gneiss's character id -- the same everywhere, since character ids are
  account-wide, not per-machine. Only the settings *file* is per-machine.
#>
param(
    [string]$ShareRoot = "\\dmc-mpc-001\EveGoldenSettings",
    [string]$GoldenCharacterId = "2121279055",
    [string[]]$CharacterIds = @(),
    [string]$SettingsDir = "$env:LOCALAPPDATA\CCP\EVE\c_eve_sharedcache_tq_tranquility\settings_Default"
)

. (Join-Path $PSScriptRoot "eve_clients_running.ps1")
Assert-NoRunningEveClients -Action "refresh the golden settings file"

$remoteFile = Join-Path $ShareRoot "core_char_$GoldenCharacterId.dat"
if (-not (Test-Path $remoteFile)) {
    Write-Error "Can't reach $remoteFile -- is the share up on dmc-mpc-001, and is this machine on the same network?"
    exit 1
}

$localGolden = Join-Path $SettingsDir "core_char_$GoldenCharacterId.dat"

# This MUST overwrite the existing file's content in place, not delete and
# recreate it at that path -- Copy-Item and Remove-Item+New-Item both create
# a fresh file object, which silently detaches this path from any hardlink
# group it was part of (every other linked character keeps the OLD content,
# and only this one path gets the new bytes -- exactly the bug this script
# exists to avoid). [IO.File]::WriteAllBytes opens with FileMode.Create,
# which truncates and rewrites the SAME inode when the target already
# exists, so every hardlinked name sees the update.
if (-not (Test-Path $localGolden)) {
    Write-Warning "$localGolden does not exist yet -- creating it fresh (no existing hardlink group to preserve)."
}
$bytes = [System.IO.File]::ReadAllBytes($remoteFile)
[System.IO.File]::WriteAllBytes($localGolden, $bytes)
Write-Host "refreshed local golden file ($($bytes.Length) bytes) from $remoteFile" -ForegroundColor Green

if ($CharacterIds.Count -gt 0) {
    & (Join-Path $PSScriptRoot "link_overview_to_golden.ps1") `
        -GoldenCharacterId $GoldenCharacterId -CharacterIds $CharacterIds -SettingsDir $SettingsDir
}
