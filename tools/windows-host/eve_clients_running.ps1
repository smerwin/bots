<#
.SYNOPSIS
  Refuse to rewrite shared settings files while any EVE client is running.
  Dot-source this; it defines the check rather than performing it.

  The hardlink group these scripts build means one file is every member's
  file. Rewriting it is therefore not a per-character operation and cannot be
  made safe by excluding the character being worked on: refreshing the golden
  file's bytes while ANY member is logged in pushes new content underneath
  that live client, and the client writes its own settings back on logout --
  so the operator's freshly pulled golden is then overwritten for the whole
  group by whichever character happened to be flying. That is the exact
  failure the linking is meant to prevent, arriving silently and group-wide.

  This is a hard refusal with no override switch, deliberately. The damage is
  invisible at the time (the pull reports success, the bytes really were
  written) and only shows up as every linked character quietly holding the
  wrong layout later. The documented way past it is to stop the sessions --
  `stop_bots.ps1`, then log the clients out -- not a flag.

  DELIBERATELY BROADER THAN eve_mem.py's LOOKUP. That one filters to
  `*bin64*exefile.exe` because it has to pick the single right process to
  attach to, and FINDINGS.md notes a 32-bit `bin/exefile.exe` exists as well.
  A guard that refuses must not narrow the same way: any client at all can
  hold a character loaded, so anything named `exefile` counts here.
#>

function Get-RunningEveClients {
    Get-Process exefile -ErrorAction SilentlyContinue |
        ForEach-Object {
            # MainWindowTitle is `EVE - <character>` once a character is in,
            # and empty while the client is still at the character select.
            # Report the pid either way; an unnamed client is still a client.
            $title = $_.MainWindowTitle
            if (-not $title) {
                $title = "(no character loaded yet)"
            }
            [PSCustomObject]@{ Id = $_.Id; Title = $title }
        }
}

function Assert-NoRunningEveClients {
    param([Parameter(Mandatory = $true)][string]$Action)

    $clients = @(Get-RunningEveClients)
    if ($clients.Count -eq 0) {
        return
    }

    Write-Host "REFUSING to $Action -- $($clients.Count) EVE client(s) running:" -ForegroundColor Red
    $clients | ForEach-Object { Write-Host "  pid $($_.Id)  $($_.Title)" -ForegroundColor Red }
    Write-Error ("These files are shared by every linked character, so this cannot be done " +
                 "around a running client. Stop the bot sessions (stop_bots.ps1) and log the " +
                 "clients out, then run this again.")
    exit 1
}
