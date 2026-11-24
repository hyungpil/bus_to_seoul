# 매일 15:55에 수집기를 띄우는 Windows 작업 스케줄러 작업을 등록한다.
# 수집기는 16:00~19:00 수집 + 이후 최대 2시간 추적, --minutes 300 으로 스스로 종료.
# 실행 중에는 PC가 절전에 들어가지 않도록 수집기가 직접 막는다(화면은 꺼져도 됨).
# 실행: powershell -ExecutionPolicy Bypass -File .\register_task.ps1
# 삭제: Unregister-ScheduledTask -TaskName BusToSeoul-Collector -Confirm:$false
$py   = "C:\Users\skplanet\AppData\Local\Programs\Python\Python311\pythonw.exe"  # 콘솔 창 없이 실행
$root = $PSScriptRoot
$action  = New-ScheduledTaskAction -Execute $py -Argument "-m bus_to_seoul collect --minutes 300" -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -Daily -At "15:55"
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -WakeToRun `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 6)
Register-ScheduledTask -TaskName "BusToSeoul-Collector" -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
Write-Host "등록 완료: BusToSeoul-Collector (매일 15:55, 로그: $root\logs\collector.log)"
