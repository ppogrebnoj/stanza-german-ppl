#Requires -Version 5.1
function Invoke-Step_powershell {
    param([object]$Ctx)
    if (Get-Command pwsh -ErrorAction SilentlyContinue) {
        return New-StepResult -Id 'powershell' -Status SKIP -Detail 'pwsh already in PATH'
    }
    #Bootstrap запускается из Windows PowerShell 5.1 специально, чтобы не было
    #замкнутого круга «pwsh ставит pwsh». PowerShell 7 нужен только CI/рекомендован
    #для интерактивной работы; на успешный чистый прогон он не влияет.
    return New-StepResult -Id 'powershell' -Status SKIP -Detail 'pwsh not installed; this run uses Windows PowerShell 5.1 (PowerShell 7 optional)' -Warnings @('pwsh отсутствует; установка продолжается на Windows PowerShell 5.1')
}
