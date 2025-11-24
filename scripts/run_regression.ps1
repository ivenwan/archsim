# Simple regression runner for archsim examples
param(
    [int]$maxTicks = 200
)

Write-Host "Running regression suite with maxTicks=$maxTicks"

function Run-Cmd($name, $cmd) {
    Write-Host "---- $name ----"
    $proc = Start-Process -FilePath "pwsh" -ArgumentList "-Command", $cmd -NoNewWindow -Wait -PassThru -RedirectStandardOutput stdout.tmp -RedirectStandardError stderr.tmp
    $out = Get-Content stdout.tmp
    $err = Get-Content stderr.tmp
    if ($proc.ExitCode -ne 0) {
        Write-Host "FAILED ($name) exit=$($proc.ExitCode)"
        if ($err) { Write-Host $err }
        exit $proc.ExitCode
    }
    if ($err) { Write-Host $err }
    Write-Host $out
    Remove-Item stdout.tmp, stderr.tmp -ErrorAction SilentlyContinue
}

Run-Cmd "built-in" "python -m archsim --max-ticks $maxTicks"
Run-Cmd "channel_modes_compare" "python -m archsim examples/channel_modes_compare.py --max-ticks $maxTicks"
Run-Cmd "semaphore_triggers" "python -m archsim examples/semaphore_triggers.py --max-ticks $maxTicks"

Write-Host "Regression completed successfully."
