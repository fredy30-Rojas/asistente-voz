# Groq Coder launcher
# Start local server and open app

$port = 8766
$url = "http://localhost:$port/groq-coder.html"

# Check if server already running
$serverRunning = netstat -an | Select-String "LISTENING" | Select-String ":$port"
if (-not $serverRunning) {
    Start-Process python -ArgumentList "-c", "import http.server,os; os.chdir('C:/Users/Fredy'); s=http.server.HTTPServer(('localhost',$port),http.server.SimpleHTTPRequestHandler); s.serve_forever()" -WindowStyle Hidden
    Start-Sleep -Seconds 1
}

# Open Chrome in app mode with separate profile for taskbar icon
Start-Process "C:\Program Files\Google\Chrome\Application\chrome.exe" "--user-data-dir=`"$env:USERPROFILE\ai-coder-profile`" --app=$url"
