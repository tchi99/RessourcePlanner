[CmdletBinding()]
param(
    [string]$Subject = "CN=RessourcePlanner Internal Code Signing",
    [int]$ValidityYears = 5,
    [string]$OutputDirectory = ".\signing-output",
    [switch]$CopyPfxBase64ToClipboard,
    [switch]$KeepInCertificateStore
)

$ErrorActionPreference = "Stop"

if ($ValidityYears -lt 1 -or $ValidityYears -gt 10) {
    throw "ValidityYears must be between 1 and 10."
}

$resolvedOutput = [IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Force -Path $resolvedOutput | Out-Null

$pfxPath = Join-Path $resolvedOutput "RessourcePlanner-Internal-CodeSigning.pfx"
$cerPath = Join-Path $resolvedOutput "RessourcePlanner-Internal-CodeSigning.cer"

if (Test-Path $pfxPath -or Test-Path $cerPath) {
    throw "Signing output already exists in $resolvedOutput. Move or delete the existing files before creating a new certificate."
}

Write-Host "Creating an internal self-signed Authenticode certificate..."
Write-Host "Subject: $Subject"
Write-Host "Validity: $ValidityYears year(s)"

$params = @{
    Subject = $Subject
    Type = "CodeSigning"
    CertStoreLocation = "Cert:\CurrentUser\My"
    HashAlgorithm = "SHA256"
    KeyAlgorithm = "RSA"
    KeyLength = 3072
    KeyExportPolicy = "Exportable"
    FriendlyName = "RessourcePlanner Internal Code Signing"
    NotAfter = (Get-Date).AddYears($ValidityYears)
}

$cert = New-SelfSignedCertificate @params
if ($null -eq $cert) {
    throw "Certificate creation failed."
}

try {
    $password = Read-Host "Choose a strong password for the PFX (this will become the GitHub CODE_SIGNING_PFX_PASSWORD secret)" -AsSecureString
    if ($null -eq $password) {
        throw "A PFX password is required."
    }

    Export-PfxCertificate -Cert $cert -FilePath $pfxPath -Password $password | Out-Null
    Export-Certificate -Cert $cert -FilePath $cerPath | Out-Null

    if ($CopyPfxBase64ToClipboard) {
        $base64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes($pfxPath))
        Set-Clipboard -Value $base64
        Write-Host "The PFX Base64 value has been copied to the clipboard."
    }

    Write-Host ""
    Write-Host "Certificate created successfully."
    Write-Host "Public certificate (.cer): $cerPath"
    Write-Host "Private certificate (.pfx): $pfxPath"
    Write-Host "Thumbprint: $($cert.Thumbprint)"
    Write-Host "Expires: $($cert.NotAfter)"
    Write-Host ""
    Write-Warning "The PFX contains the private signing key. Never commit it, email it, or put it in OneDrive/SharePoint."
    Write-Warning "After configuring the GitHub secret, store the PFX in a secure offline location or delete the working copy."
    if (-not $CopyPfxBase64ToClipboard) {
        Write-Host "To copy the PFX as Base64 later, run:"
        Write-Host "  [Convert]::ToBase64String([IO.File]::ReadAllBytes('$pfxPath')) | Set-Clipboard"
    }
}
finally {
    if (-not $KeepInCertificateStore -and $cert) {
        $storePath = "Cert:\CurrentUser\My\$($cert.Thumbprint)"
        if (Test-Path $storePath) {
            Remove-Item $storePath -Force
        }
    }
}
