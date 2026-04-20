# Vantag - Stop all services
pm2 stop all
Write-Host "All Vantag services stopped." -ForegroundColor Yellow
Write-Host "Docker containers left running (stop manually with: docker stop vantag-postgres vantag-mosquitto)" -ForegroundColor DarkGray