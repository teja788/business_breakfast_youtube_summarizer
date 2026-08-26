# Daily Business Breakfast update via Claude Code (no ANTHROPIC_API_KEY needed).
# The scheduled coding agent performs translation/analysis directly after the
# script fetches transcripts. Run by Windows Task Scheduler. Logs to logs\daily_<date>.log.

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repo

# Make sure ANTHROPIC_API_KEY is NOT set for this process, so nothing tries the
# API path. Claude Code authenticates with your logged-in subscription instead.
Remove-Item Env:\ANTHROPIC_API_KEY -ErrorAction SilentlyContinue

$logDir = Join-Path $repo "logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
$stamp = Get-Date -Format "yyyy-MM-dd_HHmmss"
$log = Join-Path $logDir "daily_$stamp.log"

$prompt = "Read RUNBOOK_daily.md in this repo and follow every step exactly. " +
          "You are unattended: never ask questions and never wait for an API key. " +
          "Use bb_summarizer.py's transcript-only mode as specified; perform " +
          "translation and analysis yourself. Process new episodes end to end, run the four " +
          "post-processing scripts, then commit and push (git push origin " +
          "HEAD:main - never force)."

"=== Business Breakfast daily run: $stamp ===" | Tee-Object -FilePath $log

& claude -p $prompt `
    --permission-mode bypassPermissions `
    --dangerously-skip-permissions `
    --model opus 2>&1 | Tee-Object -FilePath $log -Append

"=== exit code: $LASTEXITCODE ===" | Tee-Object -FilePath $log -Append
