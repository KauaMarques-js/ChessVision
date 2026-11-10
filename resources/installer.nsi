!include "MUI2.nsh"
!include "LogicLib.nsh"
Name "ChessVision Manager"
InstallDir "$LOCALAPPDATA\Programs\ChessVision Manager"
InstallDirRegKey HKCU "Software\ChessVisionManager" "InstallDir"
RequestExecutionLevel user
SetCompressor zlib
!ifndef MUI_ICON
!define MUI_ICON "${PROJECT_DIR}/resources/icon.ico"
!endif
!ifndef MUI_UNICON
!define MUI_UNICON "${PROJECT_DIR}/resources/icon.ico"
!endif
!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_RUN "$INSTDIR\ChessVision Manager.exe"
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "PortugueseBR"
Section "ChessVision Manager"
 SetShellVarContext current
 SetOutPath "$INSTDIR"
 File /r "${PROJECT_DIR}\release\win-unpacked\*"
 WriteUninstaller "$INSTDIR\Desinstalar.exe"
 CreateShortcut "$DESKTOP\ChessVision Manager.lnk" "$INSTDIR\ChessVision Manager.exe" "" "$INSTDIR\resources\icon.ico"
 CreateShortcut "$SMPROGRAMS\ChessVision Manager.lnk" "$INSTDIR\ChessVision Manager.exe" "" "$INSTDIR\resources\icon.ico"
 WriteRegStr HKCU "Software\ChessVisionManager" "InstallDir" "$INSTDIR"
 WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ChessVisionManager" "DisplayName" "ChessVision Manager"
 WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ChessVisionManager" "DisplayVersion" "${VERSION}"
 WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ChessVisionManager" "UninstallString" '$\"$INSTDIR\Desinstalar.exe$\"'
 WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ChessVisionManager" "DisplayIcon" "$INSTDIR\resources\icon.ico"
 WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ChessVisionManager" "NoModify" 1
 WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ChessVisionManager" "NoRepair" 1
SectionEnd
Section "Uninstall"
 SetShellVarContext current
 !include "${PROJECT_DIR}\resources\uninstall-files.nsh"
 Delete "$INSTDIR\Desinstalar.exe"
 RMDir "$INSTDIR"
 Delete "$DESKTOP\ChessVision Manager.lnk"
 Delete "$SMPROGRAMS\ChessVision Manager.lnk"
 DeleteRegKey HKCU "Software\ChessVisionManager"
 DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ChessVisionManager"
SectionEnd
