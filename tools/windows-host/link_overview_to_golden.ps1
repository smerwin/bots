<#
.SYNOPSIS
  Hard-link this machine's core_char_<id>.dat settings files for a set of
  characters to one "golden" character's file, so they all share one
  physical file on disk (real Windows/NTFS hard links via
  New-Item -ItemType HardLink, not a copy and not a symlink).

  This is the mechanism already in informal use on this machine -- three
  files (Greta Gneiss, Sonya Spodumain, Cathy Crokite) were already found
  sharing one inode before this script existed. This just makes the same
  operation repeatable and extends it to named others.

.PARAMETER GoldenCharacterId
  The character whose core_char_<id>.dat is the source of truth. Every other
  id in -CharacterIds ends up pointing at the exact same file.

.PARAMETER CharacterIds
  The character ids to (re)link to the golden file. The golden id itself is
  silently skipped if included.

.PARAMETER SettingsDir
  Defaults to this account's live settings_Default folder.

.PARAMETER WhatIf
  Standard ShouldProcess support -- pass -WhatIf to see what would happen
  with nothing touched.

  SAFETY, AND ITS LIMIT: this refuses to touch a file the exclusive-open
  probe below can prove is locked. Verified NOT to catch the common case,
  though -- a character actively logged in and flying right now (confirmed
  live against Olivia Ochre mid-session on 2026-08-25) still opened clean,
  because the client evidently does not hold this file open continuously
  for the life of the session. So this check catches a narrower window than
  "a client has this character loaded" and must not be trusted as the only
  guard: the caller is still responsible for excluding any character whose
  client is currently running, by id, explicitly.
#>
param(
    [Parameter(Mandatory=$true)][string]$GoldenCharacterId,
    [Parameter(Mandatory=$true)][string[]]$CharacterIds,
    [string]$SettingsDir = "$env:LOCALAPPDATA\CCP\EVE\c_eve_sharedcache_tq_tranquility\settings_Default",
    [switch]$WhatIf
)

$goldenPath = Join-Path $SettingsDir "core_char_$GoldenCharacterId.dat"
if (-not (Test-Path $goldenPath)) {
    Write-Error "Golden file not found: $goldenPath"
    exit 1
}

function Test-FileIsOpenElsewhere($path) {
    try {
        $stream = [System.IO.File]::Open($path, 'Open', 'ReadWrite', 'None')
        $stream.Close()
        return $false
    } catch {
        return $true
    }
}

foreach ($id in $CharacterIds) {
    if ($id -eq $GoldenCharacterId) {
        Write-Host "skip $id -- this is the golden character itself" -ForegroundColor DarkGray
        continue
    }

    $target = Join-Path $SettingsDir "core_char_$id.dat"
    if (-not (Test-Path $target)) {
        Write-Warning "skip $id -- no existing file at $target (character never logged in on this machine?)"
        continue
    }

    # Already the same file? fsutil's own hardlink listing is unreliable in
    # this environment (verified: reported 1 link on files independently
    # confirmed via `ls -la` link counts to be linked 4 ways) -- compare by
    # file index/volume instead, which is what NTFS actually keys identity on.
    $goldenId = (fsutil file queryfileid $goldenPath 2>$null)
    $targetId = (fsutil file queryfileid $target 2>$null)
    if ($goldenId -and $targetId -and ($goldenId -eq $targetId)) {
        Write-Host "ok   $id -- already linked to the golden file" -ForegroundColor DarkGray
        continue
    }

    if (Test-FileIsOpenElsewhere $target) {
        Write-Warning "REFUSING $id -- $target is open (a running client has it locked). Log that character out, or stop its bot session, before relinking it."
        continue
    }

    if ($WhatIf) {
        Write-Host "would link $id -> golden ($GoldenCharacterId)" -ForegroundColor Yellow
        continue
    }

    Remove-Item -LiteralPath $target -Force
    New-Item -ItemType HardLink -Path $target -Target $goldenPath | Out-Null
    Write-Host "linked $id -> golden ($GoldenCharacterId)" -ForegroundColor Green
}
