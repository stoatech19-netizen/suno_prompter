' Runs run.bat with its console window fully hidden. Desktop/Start Menu
' shortcuts point here instead of at run.bat directly, because a shortcut
' whose target is a .bat file always flashes a console window the instant
' Explorer launches it - only a non-console host like wscript.exe (which
' runs this file) avoids that. run.bat itself still does the real work
' (update check, starting Python, opening the browser); this just keeps its
' window out of sight. The server shuts itself down on its own once the
' browser is closed (see app.py's /api/heartbeat), so there's nothing left
' for the user to close manually.
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
shell.Run "cmd /c """ & scriptDir & "\run.bat""", 0, False
