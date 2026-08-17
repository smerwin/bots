# Stop every bot host, and prove it.
#
# `pkill -f botlab_host.py` does NOT work here: Git Bash cannot see native
# Windows processes or their command lines, so it matches nothing, exits 1 and
# looks like success. Seven hosts accumulated that way in one session -- one per
# "restart" -- all driving the same mouse, which CLAUDE.md calls chaos.
$hosts = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq 'python.exe' -and $_.CommandLine -like '*botlab_host.py*'
}
Write-Output "hosts found: $(($hosts | Measure-Object).Count)"
$hosts | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 3
foreach ($n in 'node','tree_walker') {
    Get-Process $n -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
}
$left = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq 'python.exe' -and $_.CommandLine -like '*botlab_host.py*'
}
$n = ($left | Measure-Object).Count
if ($n -gt 0) {
    Write-Output "STILL RUNNING: $n -- do NOT start another"
    exit 1
}
Write-Output "all stopped"
