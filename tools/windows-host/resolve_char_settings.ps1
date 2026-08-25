<#
.SYNOPSIS
  List this machine's core_char_<id>.dat settings files with the pilot name
  and corporation each id resolves to, via ESI's public (unauthenticated)
  endpoints only.

  No credentials touched -- this hits https://esi.evetech.net/latest/... directly,
  the same public lookups anyone could do in a browser:
    /characters/{id}/            -> name, corporation_id
    /universe/ids/ (POST names)  -> resolve a corporation name to its id
  It exists so an operator (or a script) can tell which numbered settings file
  belongs to which character, and which corp that character is in, without
  opening the client or reading anything out of the Windows Credential Manager.

.PARAMETER SettingsDir
  Defaults to this account's live settings_Default folder.

.PARAMETER CorporationName
  If given, only rows whose corporation matches (case-insensitive, exact name)
  are printed, and CorpMatch is true/false on every row either way.
#>
param(
    [string]$SettingsDir = "$env:LOCALAPPDATA\CCP\EVE\c_eve_sharedcache_tq_tranquility\settings_Default",
    [string]$CorporationName
)

$files = Get-ChildItem -Path $SettingsDir -Filter "core_char_*.dat" |
    Where-Object { $_.BaseName -match '^core_char_(\d+)$' }

if (-not $files) {
    Write-Error "No numeric core_char_<id>.dat files found under $SettingsDir"
    exit 1
}

$targetCorpId = $null
if ($CorporationName) {
    # ConvertTo-Json on a single-element array collapses it to a bare scalar via
    # the pipeline, which ESI's endpoint rejects -- build the JSON body by hand
    # instead of fighting that.
    $body = '[' + (($CorporationName -replace '"', '\"') | ForEach-Object { '"' + $_ + '"' }) + ']'
    $idResp = Invoke-RestMethod -Uri "https://esi.evetech.net/latest/universe/ids/?datasource=tranquility&language=en" `
        -Method Post -ContentType "application/json" -Body $body -TimeoutSec 10
    if ($idResp.corporations -and $idResp.corporations.Count -gt 0) {
        $targetCorpId = $idResp.corporations[0].id
        Write-Host "Resolved corporation '$CorporationName' -> id $targetCorpId" -ForegroundColor Cyan
    } else {
        Write-Error "ESI did not resolve a corporation named '$CorporationName' -- check spelling/capitalization."
        exit 1
    }
}

$rows = foreach ($f in $files) {
    $id = [regex]::Match($f.BaseName, '^core_char_(\d+)$').Groups[1].Value
    $name = $null
    $corpId = $null
    $corpName = $null
    try {
        $resp = Invoke-RestMethod -Uri "https://esi.evetech.net/latest/characters/$id/?datasource=tranquility" -Method Get -TimeoutSec 10
        $name = $resp.name
        $corpId = $resp.corporation_id
        try {
            $corpResp = Invoke-RestMethod -Uri "https://esi.evetech.net/latest/corporations/$corpId/?datasource=tranquility" -Method Get -TimeoutSec 10
            $corpName = $corpResp.name
        } catch {
            $corpName = "(corp lookup failed)"
        }
    } catch {
        $name = "(ESI lookup failed: $($_.Exception.Message))"
    }
    [PSCustomObject]@{
        CharacterId  = $id
        Name         = $name
        Corporation  = $corpName
        CorpMatch    = if ($targetCorpId) { $corpId -eq $targetCorpId } else { $null }
        File         = $f.Name
        FullPath     = $f.FullName
        LastWriteUtc = $f.LastWriteTimeUtc
    }
}

$out = $rows | Sort-Object Name
if ($targetCorpId) {
    $out | Where-Object { $_.CorpMatch } | Format-Table -AutoSize
} else {
    $out | Format-Table -AutoSize
}
