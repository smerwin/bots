# Run this on dmc-mpc-001, in an elevated PowerShell — not from another machine

Creates a narrow share exposing *only* a staging copy of Greta Gneiss's
overview settings file, rather than the whole live `settings_Default` folder
(which also holds other characters' and the account's own `.dat`/cache data —
no reason to put that on the network).

```powershell
$staging = "C:\EveGoldenSettings"
New-Item -ItemType Directory -Path $staging -Force | Out-Null

$src = "$env:LOCALAPPDATA\CCP\EVE\c_eve_sharedcache_tq_tranquility\settings_Default\core_char_2121279055.dat"
Copy-Item -LiteralPath $src -Destination (Join-Path $staging "core_char_2121279055.dat") -Force

New-SmbShare -Name "EveGoldenSettings" -Path $staging -ReadAccess "Everyone" -ErrorAction SilentlyContinue
Grant-SmbShareAccess -Name "EveGoldenSettings" -AccountName "Everyone" -AccessRight Read -Force
```

Re-run just the `Copy-Item` line any time Greta's overview changes on this
machine and you want to push a refresh — the share stays pointed at the same
staging folder, so nothing else needs to change.

**Log Greta out before you copy.** The client holds its overview in memory and
writes `core_char_*.dat` back on logout, so a copy taken mid-session stages
whatever the file held at last logout, not the layout you just finished
arranging. This is the manual half of the same rule
`eve_clients_running.ps1` enforces for the scripts on the receiving machines —
there is nothing here to enforce it for you.

To stop sharing when you're done:

```powershell
Remove-SmbShare -Name "EveGoldenSettings" -Force
```

Confirm the target machines (002, 003, 004) can actually reach it — from one
of them:

```powershell
Test-Path "\\dmc-mpc-001\EveGoldenSettings\core_char_2121279055.dat"
```
