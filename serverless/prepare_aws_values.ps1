param(
  [string]$Region = "us-east-1",
  [string]$StageName = "dev",
  [string]$GroqParameterName = "/psysense/dev/GROQ_API_KEY",
  [string]$N8nInviteWebhookParameterName = "/psysense/dev/N8N_INVITE_WEBHOOK",
  [string]$N8nResultWebhookParameterName = "/psysense/dev/N8N_RESULT_WEBHOOK",
  [string]$RazorpayKeyIdParameterName = "/psysense/dev/RAZORPAY_KEY_ID",
  [string]$RazorpayKeySecretParameterName = "/psysense/dev/RAZORPAY_KEY_SECRET",
  [string]$FrontendUrl = "http://localhost:5173",
  [switch]$IncludeResultWebhook,
  [switch]$IncludeRazorpay,
  [switch]$SkipSecrets
)

$ErrorActionPreference = "Stop"

function Convert-SecureStringToPlainText {
  param([Parameter(Mandatory = $true)][SecureString]$Value)

  $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Value)
  try {
    return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
  }
  finally {
    if ($bstr -ne [IntPtr]::Zero) {
      [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
  }
}

function Put-SecureParameter {
  param(
    [Parameter(Mandatory = $true)][string]$Name,
    [Parameter(Mandatory = $true)][SecureString]$SecureValue
  )

  $plainValue = Convert-SecureStringToPlainText -Value $SecureValue
  try {
    py -3.10 -m awscli ssm put-parameter `
      --name $Name `
      --type SecureString `
      --value $plainValue `
      --overwrite `
      --region $Region | Out-Host
  }
  finally {
    $plainValue = $null
  }
}

Write-Host ""
Write-Host "PsySense AWS value preparation"
Write-Host "Region: $Region"
Write-Host "Stage:  $StageName"
Write-Host ""

if (-not $SkipSecrets) {
  Write-Host "These values are yours. Do not send them to CEO/admin."
  $groq = Read-Host "Paste GROQ_API_KEY for $GroqParameterName" -AsSecureString
  Put-SecureParameter -Name $GroqParameterName -SecureValue $groq

  $n8n = Read-Host "Paste N8N invite webhook for $N8nInviteWebhookParameterName" -AsSecureString
  Put-SecureParameter -Name $N8nInviteWebhookParameterName -SecureValue $n8n

  if ($IncludeResultWebhook) {
    $n8nResult = Read-Host "Paste N8N result webhook for $N8nResultWebhookParameterName" -AsSecureString
    Put-SecureParameter -Name $N8nResultWebhookParameterName -SecureValue $n8nResult
  }

  if ($IncludeRazorpay) {
    $razorpayKeyId = Read-Host "Paste Razorpay key id for $RazorpayKeyIdParameterName" -AsSecureString
    Put-SecureParameter -Name $RazorpayKeyIdParameterName -SecureValue $razorpayKeyId

    $razorpayKeySecret = Read-Host "Paste Razorpay key secret for $RazorpayKeySecretParameterName" -AsSecureString
    Put-SecureParameter -Name $RazorpayKeySecretParameterName -SecureValue $razorpayKeySecret
  }
}

Write-Host ""
Write-Host "Use these CloudFormation parameter values for the fresh deploy:"
Write-Host "StageName=$StageName"
Write-Host "GroqApiKeyParameterName=$GroqParameterName"
Write-Host "N8nInviteWebhookParameterName=$N8nInviteWebhookParameterName"
Write-Host "N8nResultWebhookParameterName=$N8nResultWebhookParameterName"
Write-Host "RazorpayKeyIdParameterName=$RazorpayKeyIdParameterName"
Write-Host "RazorpayKeySecretParameterName=$RazorpayKeySecretParameterName"
Write-Host "FrontendUrl=$FrontendUrl"
Write-Host ""
Write-Host "CEO/admin is only needed for IAM deployment permission and cleanup of the failed stack."
