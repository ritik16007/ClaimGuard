$deadline = (Get-Date).AddSeconds(120)
while ((Get-Date) -lt $deadline) {
    try {
        Invoke-RestMethod -Uri 'http://127.0.0.1:5000/api/status' -TimeoutSec 2 | Out-Null
        Write-Host 'ClaimGuard is responding.'
        exit 0
    }
    catch {
        Write-Host '.' -NoNewline
        Start-Sleep -Seconds 2
    }
}
Write-Host ''
Write-Host 'Timed out waiting for ClaimGuard. Check the server window for its error.'
exit 1
