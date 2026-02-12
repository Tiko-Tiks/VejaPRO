param(
    [string]$Branch = "",
    [string]$RepoUrl = "",
    [string]$SshHost = "administrator@10.10.50.178",
    [string]$KeyPath = "$env:USERPROFILE\.ssh\vejapro_ed25519",
    [string]$PythonPath = "/home/administrator/.venv/bin/python",
    [switch]$KeepWorkdir,
    [switch]$ShowRemoteScript
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not $Branch) {
    $Branch = (git rev-parse --abbrev-ref HEAD).Trim()
}

if (-not $RepoUrl) {
    $RepoUrl = (git remote get-url origin).Trim()
}

$keepValue = if ($KeepWorkdir) { "1" } else { "0" }
$branchSafe = $Branch.Replace("'", "'""'""'")
$repoSafe = $RepoUrl.Replace("'", "'""'""'")
$pythonSafe = $PythonPath.Replace("'", "'""'""'")
$keepSafe = $keepValue.Replace("'", "'""'""'")

$remoteTemplate = @'
set -euo pipefail

branch='__BRANCH__'
repo_url='__REPO__'
python_bin='__PYTHON__'
keep_workdir='__KEEP__'

workdir="$(mktemp -d /tmp/veja-ci-check-XXXXXX)"
echo "Using workdir: $workdir"
echo "Branch: $branch"
git clone --depth 1 --branch "$branch" "$repo_url" "$workdir"
cd "$workdir"

# CI-like environment from .github/workflows/ci.yml
export PYTHONPATH=backend
export DATABASE_URL=sqlite:////tmp/veja_api_test.db
export ENVIRONMENT=test
export SECRET_KEY='ci-test-secret-key-32chars-long!!'
export SUPABASE_URL='https://fake.supabase.co'
export SUPABASE_KEY='fake-supabase-key-for-ci'
export SUPABASE_JWT_SECRET='testsecret_testsecret_testsecret_test'
export ALLOW_INSECURE_WEBHOOKS=true
export ENABLE_MANUAL_PAYMENTS=true
export ENABLE_STRIPE=false
export ENABLE_TWILIO=true
export ENABLE_MARKETING_MODULE=true
export ENABLE_CALL_ASSISTANT=true
export ENABLE_CALENDAR=true
export ENABLE_SCHEDULE_ENGINE=true
export ENABLE_NOTIFICATION_OUTBOX=true
export ENABLE_WHATSAPP_PING=true
export ENABLE_VISION_AI=false
export ENABLE_FINANCE_LEDGER=true
export ENABLE_FINANCE_AI_INGEST=true
export ENABLE_FINANCE_AUTO_RULES=true
export ENABLE_FINANCE_METRICS=true
export ENABLE_EMAIL_INTAKE=true
export ENABLE_AI_INTENT=true
export ENABLE_AI_VISION=false
export ENABLE_AI_FINANCE_EXTRACT=false
export ENABLE_AI_OVERRIDES=false
export AI_INTENT_PROVIDER=mock
export AI_ALLOWED_PROVIDERS=mock
export ENABLE_AI_SUMMARY=false
export ENABLE_AI_CONVERSATION_EXTRACT=true
export ENABLE_EMAIL_WEBHOOK=true
export ENABLE_AI_EMAIL_SENTIMENT=true
export ENABLE_EMAIL_AUTO_REPLY=true
export ENABLE_EMAIL_AUTO_OFFER=false
export ENABLE_RECURRING_JOBS=false
export DASHBOARD_SSE_MAX_CONNECTIONS=5
export ADMIN_TOKEN_ENDPOINT_ENABLED=true
export ADMIN_IP_ALLOWLIST=''
export RATE_LIMIT_API_ENABLED=false
export PII_REDACTION_ENABLED=true
export TWILIO_ACCOUNT_SID=AC_ci_test_sid
export TWILIO_AUTH_TOKEN=ci_test_auth_token
export TWILIO_FROM_NUMBER=+15005550006
export SMTP_HOST=smtp.test.local
export SMTP_PORT=587
export SMTP_USER=ci@test.local
export SMTP_PASSWORD=ci-test-password
export SMTP_FROM_EMAIL=ci@test.local
export TEST_AUTH_ROLE=ADMIN

"$python_bin" - <<'PY'
from app.core.dependencies import engine
from app.models.project import Base

Base.metadata.drop_all(engine)
Base.metadata.create_all(engine)
print("DB reset OK")
PY

"$python_bin" -m pytest backend/tests -q

if [ "$keep_workdir" = "1" ]; then
  echo "Keeping workdir: $workdir"
else
  rm -rf "$workdir"
  echo "Removed workdir: $workdir"
fi
'@

$remoteScript = $remoteTemplate.Replace("__BRANCH__", $branchSafe)
$remoteScript = $remoteScript.Replace("__REPO__", $repoSafe)
$remoteScript = $remoteScript.Replace("__PYTHON__", $pythonSafe)
$remoteScript = $remoteScript.Replace("__KEEP__", $keepSafe)
$remoteScript = $remoteScript.Replace("`r", "")

if ($ShowRemoteScript) {
    Write-Output $remoteScript
    exit 0
}

$sshCommand = "bash -lc ""cat | sed 's/\r$//' | bash -s"""
$remoteScript | ssh -i $KeyPath $SshHost $sshCommand
exit $LASTEXITCODE
