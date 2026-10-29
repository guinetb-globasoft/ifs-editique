<#
    Lance l'application en local : venv, dépendances, Chromium, serveur.

        .\demarrer.ps1               # http://localhost:8000
        .\demarrer.ps1 -Port 8010    # autre port (à déclarer aussi dans IFS_OIDC_REDIRECT_URI)
        .\demarrer.ps1 -Rechargement # redémarre à chaque modification du code
#>
param(
    [int]$Port = 8000,
    [switch]$Rechargement
)

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'

if (-not (Test-Path $python)) {
    Write-Host 'Création de l''environnement virtuel...' -ForegroundColor Cyan
    py -3.12 -m venv .venv
}

Write-Host 'Vérification des dépendances...' -ForegroundColor Cyan
& $python -m pip install --quiet --upgrade pip
& $python -m pip install --quiet -r requirements.txt
# Sans effet si le Chromium de Playwright 1.58 est déjà là (tests-automatisés-IFS l'installe aussi).
& $python -m playwright install chromium

if (-not (Test-Path '.env')) {
    Copy-Item '.env.example' '.env'
    Write-Warning '.env créé depuis .env.example — renseignez le client Keycloak avant de générer un document.'
}

Write-Host ''
# L'hôte affiché doit être celui de IFS_OIDC_REDIRECT_URI : le cookie de session
# ne passe pas de localhost à 127.0.0.1, et le retour du realm échouerait.
Write-Host "Éditiques disponibles sur http://localhost:$Port" -ForegroundColor Green
Write-Host "Aperçu sans IFS : .venv\Scripts\python.exe outils\apercu.py"
Write-Host 'Ctrl+C pour arrêter.'
Write-Host ''

$arguments = @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', $Port)
if ($Rechargement) { $arguments += '--reload' }

& $python @arguments
