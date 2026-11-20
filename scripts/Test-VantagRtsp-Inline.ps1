function Test-VantagRtsp {
    param([string]$NvrAddress='192.168.1.102', [int]$Port=554,
          [System.Management.Automation.PSCredential]$Credential,
          [string]$ReportPath)
    $ErrorActionPreference = 'Stop'
    function Get-Digest([string]$Value) {
        $hash = [Security.Cryptography.MD5]::Create()
        try { ([BitConverter]::ToString($hash.ComputeHash([Text.Encoding]::UTF8.GetBytes($Value)))).Replace('-','').ToLowerInvariant() }
        finally { $hash.Dispose() }
    }
    function Read-Description([string]$Authorization) {
        $client = New-Object Net.Sockets.TcpClient
        try {
            if (-not $client.ConnectAsync($NvrAddress,$Port).Wait(5000)) { throw 'Connection timed out' }
            $stream = $client.GetStream()
            $stream.ReadTimeout=5000; $stream.WriteTimeout=5000
            $request="DESCRIBE $uri RTSP/1.0`r`nCSeq: 1`r`nAccept: application/sdp`r`n"
            if ($Authorization) { $request += "Authorization: $Authorization`r`n" }
            $bytes=[Text.Encoding]::UTF8.GetBytes($request+"`r`n")
            $stream.Write($bytes,0,$bytes.Length)
            $buffer=New-Object byte[] 4096
            $reply=''
            $deadline=[DateTime]::UtcNow.AddSeconds(8)
            while (-not $reply.Contains("`r`n`r`n")) {
                $remaining=[int]($deadline-[DateTime]::UtcNow).TotalMilliseconds
                if ($remaining -le 0) { throw 'RTSP response timed out' }
                $stream.ReadTimeout=[Math]::Min(5000,$remaining)
                $count=$stream.Read($buffer,0,$buffer.Length)
                if ($count -eq 0) { break }
                $reply += [Text.Encoding]::UTF8.GetString($buffer,0,$count)
                if ($reply.Length -gt 65536) { throw 'Response too large' }
            }
            if ($reply -notmatch '^RTSP/\d\.\d\s+\d{3}') { throw 'No valid RTSP response' }
            $reply
        }
        finally { $client.Dispose() }
    }
    try {
        if ($NvrAddress -notmatch '^[a-zA-Z0-9.-]+$') { throw 'Invalid NVR address' }
        if (-not $Credential) { $Credential=Get-Credential -UserName admin -Message 'Enter ORIGINAL NVR password; type # literally, not %23' }
        if (-not $Credential) { throw 'No credentials supplied' }
        $uri="rtsp://${NvrAddress}:${Port}/Streaming/Channels/101"
        $reply=Read-Description ''
        if ($reply -match '^RTSP/\d\.\d\s+401') {
            $challenge=[regex]::Match($reply,'(?im)^WWW-Authenticate:\s*Digest\s+([^\r\n]+)')
            if (-not $challenge.Success) { throw 'NVR did not offer Digest; no password sent' }
            $fields=@{}
            foreach ($entry in [regex]::Matches($challenge.Groups[1].Value,'(\w+)\s*=\s*(?:"([^"]*)"|([^,\s]+))')) {
                $value=$entry.Groups[3].Value
                if ($entry.Groups[2].Success) { $value=$entry.Groups[2].Value }
                $fields[$entry.Groups[1].Value]=$value
            }
            $algorithm='MD5'
            if ($fields['algorithm']) { $algorithm=$fields['algorithm'].ToUpperInvariant() }
            if ($algorithm -notin @('MD5','MD5-SESS')) { throw 'Unsupported Digest algorithm; no password sent' }
            if (-not $fields['realm'] -or -not $fields['nonce']) { throw 'Incomplete Digest challenge' }
            if ($Credential.UserName -match '["\r\n\\]') { throw 'Unsupported username characters' }
            $cnonce=[Guid]::NewGuid().ToString('N')
            $ha1=Get-Digest ('{0}:{1}:{2}' -f $Credential.UserName,$fields['realm'],$Credential.GetNetworkCredential().Password)
            if ($algorithm -eq 'MD5-SESS') { $ha1=Get-Digest ('{0}:{1}:{2}' -f $ha1,$fields['nonce'],$cnonce) }
            $ha2=Get-Digest "DESCRIBE:$uri"
            if ($fields['qop']) {
                if ('auth' -notin ($fields['qop'].Split(',') | ForEach-Object { $_.Trim().ToLowerInvariant() })) { throw 'Unsupported Digest qop' }
                $digest=Get-Digest ('{0}:{1}:00000001:{2}:auth:{3}' -f $ha1,$fields['nonce'],$cnonce,$ha2)
            } else { $digest=Get-Digest ('{0}:{1}:{2}' -f $ha1,$fields['nonce'],$ha2) }
            $auth='Digest username="{0}", realm="{1}", nonce="{2}", uri="{3}", response="{4}", algorithm={5}' -f $Credential.UserName,$fields['realm'],$fields['nonce'],$uri,$digest,$algorithm
            if ($fields['qop']) { $auth += ', qop=auth, nc=00000001, cnonce="{0}"' -f $cnonce }
            elseif ($algorithm -eq 'MD5-SESS') { $auth += ', cnonce="{0}"' -f $cnonce }
            if ($fields['opaque']) { $auth += ', opaque="{0}"' -f $fields['opaque'] }
            $reply=Read-Description $auth
            $code=[regex]::Match($reply,'^RTSP/\d\.\d\s+(\d{3})').Groups[1].Value
            $result="With supplied credentials: RTSP $code"
        } else { $result='Without credentials: '+($reply -split "`r`n")[0] }
        Write-Host $result
        if ($ReportPath) { $result | Set-Content -LiteralPath $ReportPath -Encoding UTF8 }
    }
    catch { Write-Host ('Diagnostic stopped: '+$_.Exception.Message) }
    finally { $auth=$null; $ha1=$null; $Credential=$null }
}
