# Step 1: ARP Ping Sweep
Write-Host "=== Scanning 192.168.1.0/24 for live hosts ===" -ForegroundColor Cyan
$liveHosts = @()
1..254 | ForEach-Object {
    $ip = "192.168.1.$_"
    if (Test-Connection -ComputerName $ip -Count 1 -Quiet -TimeoutSeconds 1) {
        Write-Host "ALIVE: $ip" -ForegroundColor Green
        $liveHosts += $ip
    }
}

Write-Host "`n=== Found $($liveHosts.Count) live hosts ===" -ForegroundColor Cyan
Write-Host ($liveHosts -join ", ")

# Step 2: Port probe for camera ports
Write-Host "`n=== Probing camera ports on live hosts ===" -ForegroundColor Cyan
$cameraPorts = @(554, 80, 8080, 8000, 37777, 34567)
$cameraHosts = @()

foreach ($ip in $liveHosts) {
    $openPorts = @()
    foreach ($port in $cameraPorts) {
        $conn = Test-NetConnection -ComputerName $ip -Port $port -WarningAction SilentlyContinue -ErrorAction SilentlyContinue
        if ($conn.TcpTestSucceeded) {
            $openPorts += $port
            Write-Host "  $ip : $port OPEN" -ForegroundColor Yellow
        }
    }
    if ($openPorts -contains 554 -or $openPorts -contains 37777 -or $openPorts -contains 34567) {
        $cameraHosts += [PSCustomObject]@{ IP = $ip; Ports = $openPorts -join "," }
        Write-Host "  >> CAMERA CANDIDATE: $ip (ports: $($openPorts -join ','))" -ForegroundColor Magenta
    }
}

Write-Host "`n=== CAMERA CANDIDATES ===" -ForegroundColor Cyan
$cameraHosts | Format-Table -AutoSize

# Save results for next step
$cameraHosts | ConvertTo-Json | Out-File "D:\AI Algo\Collaterals\Profiles\Retail Nazar\camera_scan_results.json"
Write-Host "Results saved to camera_scan_results.json" -ForegroundColor Green
