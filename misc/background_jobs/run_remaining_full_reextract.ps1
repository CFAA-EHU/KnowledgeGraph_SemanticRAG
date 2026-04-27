$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $repoRoot

$timestamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
$logDir = Join-Path $repoRoot "logs\full_reextract"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logPath = Join-Path $logDir "run_$timestamp.log"

function Write-Log {
    param([string]$Message)
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    $line | Tee-Object -FilePath $logPath -Append
}

function Resolve-LegacyMistralKey {
    $legacyExtractor = Join-Path $repoRoot "src\2_extraction\llm_extractor.py"
    if (-not (Test-Path $legacyExtractor)) {
        throw "No existe el extractor legacy en $legacyExtractor"
    }
    $legacyText = Get-Content -Path $legacyExtractor -Raw -Encoding UTF8
    $match = [regex]::Match($legacyText, 'api_key\s*=\s*"([^"]+)"')
    if (-not $match.Success) {
        throw "No se encontro una API key legacy reutilizable en $legacyExtractor"
    }
    return $match.Groups[1].Value
}

function Run-Stage {
    param(
        [string]$Label,
        [string[]]$Arguments
    )

    Write-Log "START $Label"
    Write-Log ("CMD python " + ($Arguments -join " "))
    & python @Arguments 2>&1 | Tee-Object -FilePath $logPath -Append
    if ($LASTEXITCODE -ne 0) {
        throw "Fallo la fase $Label con codigo $LASTEXITCODE"
    }
    Write-Log "END $Label"
}

$env:MISTRAL_API_KEY = Resolve-LegacyMistralKey
$env:MISTRAL_MODEL = "mistral-medium-latest"
$env:MISTRAL_MODEL_FALLBACKS = "open-mistral-nemo,mistral-small-latest"

Write-Log "Inicio de reextraccion larga restante"
Write-Log "Repo root: $repoRoot"
Write-Log "Log path: $logPath"

Run-Stage -Label "installation_manual_abox_extractor_force_stale" -Arguments @(
    "src\6_extraction\abox_extractor.py",
    "--mode", "force-stale",
    "--retry-profile", "micro-batch-recovery",
    "--abox-input", "data\processed\installation_manual_abox_input.json",
    "--manifest-path", "data\processed\installation_manual_abox_generation_manifest.json",
    "--output-dir", "data\processed\installation_manual_abox_graphs",
    "--debug-dir", "data\processed\installation_manual_abox_debug"
)

Run-Stage -Label "man_8070_err_abox_extractor_force_all" -Arguments @(
    "src\6_extraction\abox_extractor.py",
    "--mode", "force-all",
    "--retry-profile", "micro-batch-recovery",
    "--abox-input", "data\processed\man_8070_err_abox_input.json",
    "--manifest-path", "data\processed\man_8070_err_abox_generation_manifest.json",
    "--output-dir", "data\processed\man_8070_err_abox_graphs",
    "--debug-dir", "data\processed\man_8070_err_abox_debug"
)

Run-Stage -Label "runtime_clean_rebuild_resume_compatible" -Arguments @(
    "run_runtime_clean_rebuild.py",
    "--mode", "resume-compatible",
    "--retry-profile", "micro-batch-recovery"
)

Write-Log "Reextraccion restante completada"
