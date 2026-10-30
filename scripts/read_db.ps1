<#
Read a SQLite database from PowerShell, with no Python involved.

    scripts\read_db.ps1 -Path "$env:LOCALAPPDATA\Ocura\ocura.db" -Sql "SELECT count(*) AS n FROM events"

Opens the file read-only through Windows' own winsqlite3.dll. This exists
because a venv on Microsoft Store Python sees %LOCALAPPDATA% redirected into
its package, and reports the documented path while reading a different file.
Only a reader outside that process can say where the data really is. See
"Tooling gotchas" in docs/architecture.md.
#>
param(
    [Parameter(Mandatory)][string]$Path,
    [Parameter(Mandatory)][string]$Sql
)
if (-not ('WinSqlite' -as [type])) {
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class WinSqlite {
    [DllImport("winsqlite3.dll", CharSet = CharSet.Ansi)]
    public static extern int sqlite3_open_v2(byte[] filename, out IntPtr db, int flags, IntPtr vfs);
    [DllImport("winsqlite3.dll")] public static extern int sqlite3_close(IntPtr db);
    [DllImport("winsqlite3.dll")] public static extern int sqlite3_prepare_v2(IntPtr db, byte[] sql, int n, out IntPtr stmt, IntPtr tail);
    [DllImport("winsqlite3.dll")] public static extern int sqlite3_step(IntPtr stmt);
    [DllImport("winsqlite3.dll")] public static extern int sqlite3_finalize(IntPtr stmt);
    [DllImport("winsqlite3.dll")] public static extern int sqlite3_column_count(IntPtr stmt);
    [DllImport("winsqlite3.dll")] public static extern IntPtr sqlite3_column_name(IntPtr stmt, int i);
    [DllImport("winsqlite3.dll")] public static extern IntPtr sqlite3_column_text(IntPtr stmt, int i);
    [DllImport("winsqlite3.dll")] public static extern IntPtr sqlite3_errmsg(IntPtr db);
}
'@
}
function Utf8Z([string]$s) { [Text.Encoding]::UTF8.GetBytes($s + [char]0) }
function FromUtf8([IntPtr]$p) {
    if ($p -eq [IntPtr]::Zero) { return $null }
    $len = 0; while ([Runtime.InteropServices.Marshal]::ReadByte($p, $len) -ne 0) { $len++ }
    $buf = New-Object byte[] $len
    [Runtime.InteropServices.Marshal]::Copy($p, $buf, 0, $len)
    [Text.Encoding]::UTF8.GetString($buf)
}
$db = [IntPtr]::Zero
$rc = [WinSqlite]::sqlite3_open_v2((Utf8Z $Path), [ref]$db, 1, [IntPtr]::Zero)  # SQLITE_OPEN_READONLY
if ($rc -ne 0) { throw "open failed ($rc): $(FromUtf8 ([WinSqlite]::sqlite3_errmsg($db)))" }
try {
    $stmt = [IntPtr]::Zero
    $rc = [WinSqlite]::sqlite3_prepare_v2($db, (Utf8Z $Sql), -1, [ref]$stmt, [IntPtr]::Zero)
    if ($rc -ne 0) { throw "prepare failed ($rc): $(FromUtf8 ([WinSqlite]::sqlite3_errmsg($db)))" }
    $n = [WinSqlite]::sqlite3_column_count($stmt)
    while (($rc = [WinSqlite]::sqlite3_step($stmt)) -eq 100) {  # SQLITE_ROW
        $row = [ordered]@{}
        for ($i = 0; $i -lt $n; $i++) {
            $row[(FromUtf8 ([WinSqlite]::sqlite3_column_name($stmt, $i)))] = FromUtf8 ([WinSqlite]::sqlite3_column_text($stmt, $i))
        }
        [pscustomobject]$row
    }
    if ($rc -ne 101) { throw "step failed ($rc): $(FromUtf8 ([WinSqlite]::sqlite3_errmsg($db)))" }
    [void][WinSqlite]::sqlite3_finalize($stmt)
} finally { [void][WinSqlite]::sqlite3_close($db) }
