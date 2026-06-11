' RetailVantag_EdgeAgent.vbs
' Double-click this file to start the Vantag Edge Agent with no visible
' command-prompt window.  The agent will appear only in the system tray.
'
' You can also create a Windows Startup shortcut to this .vbs file so the
' agent starts automatically when you log in.

Option Explicit

Dim shell, scriptDir, exePath
Set shell = CreateObject("WScript.Shell")

' Locate the .exe next to this .vbs file
scriptDir = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\"))
exePath   = scriptDir & "RetailVantag_EdgeAgent.exe"

If Not CreateObject("Scripting.FileSystemObject").FileExists(exePath) Then
    MsgBox "Cannot find " & exePath & Chr(13) & _
           "Place this .vbs file in the same folder as RetailVantag_EdgeAgent.exe.", _
           vbCritical, "Vantag Edge Agent"
    WScript.Quit 1
End If

' Run with window hidden (0 = hidden, False = don't wait)
shell.Run Chr(34) & exePath & Chr(34), 0, False

WScript.Quit 0
