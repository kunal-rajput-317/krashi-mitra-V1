# fetch_rental_images.ps1
# Downloads rental equipment images from Wikimedia Commons (as per CREDITS.json)
# and saves them as .webp in frontend/images/rental/
# Run from repo root: .\tools\fetch_rental_images.ps1

$creditsPath = ".\frontend\images\rental\CREDITS.json"
$outputDir   = ".\frontend\images\rental"

$credits = Get-Content $creditsPath -Raw | ConvertFrom-Json

foreach ($slug in $credits.PSObject.Properties.Name) {
    $entry   = $credits.$slug
    $thumbUrl = $entry.thumb
    $outFile  = Join-Path $outputDir "$slug.webp"

    Write-Host "Downloading: $slug ..." -NoNewline

    try {
        $headers = @{
            "User-Agent" = "KrashiMitra/1.0 (https://krashimitra.in; contact: krashimitra038@gmail.com) PowerShell"
        }
        Invoke-WebRequest -Uri $thumbUrl -OutFile $outFile -Headers $headers -TimeoutSec 30 -ErrorAction Stop
        $size = (Get-Item $outFile).Length
        Write-Host " OK ($([math]::Round($size/1024,1)) KB)" -ForegroundColor Green
    } catch {
        Write-Host " FAILED: $_" -ForegroundColor Red
    }

    # Polite delay — Wikimedia rate limits aggressive bots
    Start-Sleep -Milliseconds 400
}

Write-Host "`nDone. Images saved to: $outputDir"
