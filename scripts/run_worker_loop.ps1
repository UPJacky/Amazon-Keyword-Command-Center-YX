param(
    [Parameter(Mandatory = $true)]
    [string]$QueueRoot,

    [Parameter(Mandatory = $true)]
    [string]$StorageRoot,

    [double]$PollInterval = 1.0,
    [double]$MaxBackoff = 30.0,
    [double]$HeartbeatInterval = 30.0,
    [int]$MaxCycles
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot

if ($env:KWCC_PYTHON -and (Test-Path -LiteralPath $env:KWCC_PYTHON -PathType Leaf)) {
    $Python = $env:KWCC_PYTHON
} else {
    $bundled = 'C:\Users\Jacky\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
    if (Test-Path -LiteralPath $bundled -PathType Leaf) {
        $Python = $bundled
    } else {
        $Python = 'python'
    }
}

$Arguments = @(
    (Join-Path $PSScriptRoot 'run_worker_loop.py'),
    '--queue-root', $QueueRoot,
    '--storage-root', $StorageRoot,
    '--poll-interval', $PollInterval,
    '--max-backoff', $MaxBackoff,
    '--heartbeat-interval', $HeartbeatInterval
)
if ($PSBoundParameters.ContainsKey('MaxCycles')) {
    $Arguments += @('--max-cycles', $MaxCycles)
}

Push-Location $ProjectRoot
try {
    & $Python @Arguments
    $ExitCode = $LASTEXITCODE
    if ($null -eq $ExitCode) {
        $ExitCode = 0
    }
    exit $ExitCode
} catch {
    [ordered]@{
        cycles = 0
        processed = 0
        failed = 0
        empty_cycles = 0
        errors = 1
        recovered = 0
        stopped = $false
        reason = 'unexpected_supervisor_exception'
        exception_type = $_.Exception.GetType().Name
        error = $_.Exception.Message
    } | ConvertTo-Json
    exit 1
} finally {
    Pop-Location
}
