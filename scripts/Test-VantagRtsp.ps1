param(
    [string]$NvrAddress = '192.168.1.102',
    [int]$Port = 554,
    [string]$Channel = '101',
    [System.Management.Automation.PSCredential]$Credential,
    [string]$ReportPath = (Join-Path $PSScriptRoot 'Vantag-RTSP-result.txt')
)

$ErrorActionPreference = 'Stop'
$report = New-Object 'System.Collections.Generic.List[string]'

function Write-Result([string]$Text) {
    $report.Add($Text)
    Write-Host $Text
}

function Get-Md5([string]$Text) {
    $md5 = [System.Security.Cryptography.MD5]::Create()
    try {
        return ([System.BitConverter]::ToString($md5.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($Text)))).Replace('-', '').ToLowerInvariant()
    }
    finally { $md5.Dispose() }
}

function Invoke-RtspDescribe([string]$Uri, [string]$Authorization, [int]$Sequence) {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $connect = $client.ConnectAsync($NvrAddress, $Port)
        if (-not $connect.Wait(5000)) { throw 'TCP connection timed out.' }
        $stream = $client.GetStream()
        $stream.ReadTimeout = 5000
        $stream.WriteTimeout = 5000
        $request = "DESCRIBE $Uri RTSP/1.0`r`nCSeq: $Sequence`r`nAccept: application/sdp`r`n"
        if ($Authorization) { $request += "Authorization: $Authorization`r`n" }
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($request + "`r`n")
        $stream.Write($bytes, 0, $bytes.Length)
        $response = New-Object System.IO.MemoryStream
        try {
            $buffer = New-Object byte[] 4096
            $deadline = [DateTime]::UtcNow.AddSeconds(8)
            do {
                $remaining = [int]($deadline - [DateTime]::UtcNow).TotalMilliseconds
                if ($remaining -le 0) { throw 'RTSP response timed out.' }
                $stream.ReadTimeout = [Math]::Min(5000, $remaining)
                $read = $stream.Read($buffer, 0, $buffer.Length)
                if ($read -eq 0) { break }
                $response.Write($buffer, 0, $read)
                if ($response.Length -gt 65536) { throw 'RTSP response exceeds diagnostic size limit.' }
                $text = [System.Text.Encoding]::UTF8.GetString($response.ToArray())
                $boundary = $text.IndexOf("`r`n`r`n", [StringComparison]::Ordinal)
                if ($boundary -ge 0) {
                    $headers = $text.Substring(0, $boundary)
                    $bodyLength = 0
                    if ($headers -match '(?im)^Content-Length:\s*(\d+)') { $bodyLength = [int]$Matches[1] }
                    $headerLength = [System.Text.Encoding]::UTF8.GetByteCount($text.Substring(0, $boundary + 4))
                    if ($response.Length -ge $headerLength + $bodyLength) { break }
                }
            } while ($true)
            $text = [System.Text.Encoding]::UTF8.GetString($response.ToArray())
            if ($text -notmatch '^RTSP/\d\.\d\s+(\d{3})') { throw 'No valid RTSP response received.' }
            return @{ Code = [int]$Matches[1]; Text = $text }
        }
        finally { $response.Dispose() }
    }
    finally { $client.Dispose() }
}

try {
    if ($NvrAddress -notmatch '^[a-zA-Z0-9.-]+$' -or $Channel -notmatch '^\d+$' -or $Port -lt 1 -or $Port -gt 65535) {
        throw 'Invalid NVR address, port or numeric channel.'
    }
    if (-not $Credential) {
        $Credential = Get-Credential -UserName 'admin' -Message 'Enter the ORIGINAL NVR password. Type # literally; do not replace it with %23.'
    }
    if (-not $Credential) { throw 'Credentials were not supplied.' }
    $uri = "rtsp://${NvrAddress}:${Port}/Streaming/Channels/$Channel"
    Write-Result "Vantag RTSP diagnostic: $NvrAddress port $Port channel $Channel"
    Write-Result 'No password or authentication headers are saved in this report.'
    $first = Invoke-RtspDescribe $uri '' 1
    Write-Result "Without credentials: RTSP $($first.Code)"
    $result = $first
    if ($first.Code -eq 401) {
        $challenge = [regex]::Match($first.Text, '(?im)^WWW-Authenticate:\s*Digest\s+([^\r\n]+)')
        if (-not $challenge.Success) { throw 'NVR did not offer Digest authentication; no password was sent.' }
        $fields = @{}
        foreach ($match in [regex]::Matches($challenge.Groups[1].Value, '(\w+)\s*=\s*(?:"([^"]*)"|([^,\s]+))')) {
            $value = $match.Groups[3].Value
            if ($match.Groups[2].Success) { $value = $match.Groups[2].Value }
            $fields[$match.Groups[1].Value] = $value
        }
        $algorithm = 'MD5'
        if ($fields.ContainsKey('algorithm')) { $algorithm = $fields['algorithm'].ToUpperInvariant() }
        Write-Result "Authentication offered: Digest $algorithm"
        if ($algorithm -notin @('MD5', 'MD5-SESS')) { throw 'This diagnostic supports MD5 and MD5-sess only; no password was sent.' }
        if (-not $fields['realm'] -or -not $fields['nonce']) { throw 'Incomplete Digest challenge; no password was sent.' }
        $username = $Credential.UserName
        if ($username -match '["\r\n\\]') { throw 'Username contains characters unsupported by this diagnostic.' }
        $realm = $fields['realm']
        $nonce = $fields['nonce']
        $cnonce = [Guid]::NewGuid().ToString('N')
        $password = $Credential.GetNetworkCredential().Password
        $ha1 = Get-Md5 ("{0}:{1}:{2}" -f $username, $realm, $password)
        $password = $null
        if ($algorithm -eq 'MD5-SESS') { $ha1 = Get-Md5 ("{0}:{1}:{2}" -f $ha1, $nonce, $cnonce) }
        $ha2 = Get-Md5 ("DESCRIBE:$uri")
        $qop = $fields['qop']
        if ($qop) {
            if ('auth' -notin ($qop.Split(',') | ForEach-Object { $_.Trim().ToLowerInvariant() })) {
                throw 'NVR requires an unsupported Digest qop; no authenticated request was sent.'
            }
            $digest = Get-Md5 ("{0}:{1}:00000001:{2}:auth:{3}" -f $ha1, $nonce, $cnonce, $ha2)
        }
        else { $digest = Get-Md5 ("{0}:{1}:{2}" -f $ha1, $nonce, $ha2) }
        $authorization = 'Digest username="{0}", realm="{1}", nonce="{2}", uri="{3}", response="{4}", algorithm={5}' -f $username, $realm, $nonce, $uri, $digest, $algorithm
        if ($qop) { $authorization += ', qop=auth, nc=00000001, cnonce="{0}"' -f $cnonce }
        elseif ($algorithm -eq 'MD5-SESS') { $authorization += ', cnonce="{0}"' -f $cnonce }
        if ($fields['opaque']) { $authorization += ', opaque="{0}"' -f $fields['opaque'] }
        $result = Invoke-RtspDescribe $uri $authorization 2
        Write-Result "With supplied credentials: RTSP $($result.Code)"
    }
    switch ($result.Code) {
        200 { Write-Result 'PASS: NVR returned a stream description. This confirms DESCRIBE access, not video playback. Next investigate SETUP/transport, stream encryption and decoder compatibility.' }
        401 { Write-Result 'REJECTED: authenticated request was rejected. Check the NVR username/password, account lockout, RTSP rights and authentication policy. Do not keep retrying.' }
        403 { Write-Result 'DENIED: check remote live-view permission, account restrictions and NVR security policy.' }
        404 { Write-Result 'NOT FOUND: check that this NVR channel exists and is enabled. Restrictions may also hide a channel.' }
        default { Write-Result "NVR returned RTSP $($result.Code). Further interpretation is required." }
    }
}
catch {
    Write-Result ("Diagnostic stopped: {0}" -f $_.Exception.Message)
    exit 1
}
finally {
    $password = $null
    $authorization = $null
    $ha1 = $null
    try {
        $report | Set-Content -LiteralPath $ReportPath -Encoding UTF8
        Write-Host "Safe result saved to: $ReportPath"
    }
    catch { Write-Host 'Could not save the report; share the displayed result instead.' }
}
