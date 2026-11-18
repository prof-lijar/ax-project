# Read-only Windows UI Automation probe. No screenshots, clipboard, clicks, or keystrokes.
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$stage = 'providers'
try {
    # Explicitly initialize the standard Win32 control proxies in the PowerShell host.
    Add-Type -AssemblyName UIAutomationClientsideProviders
    $providers = [AppDomain]::CurrentDomain.GetAssemblies() | Where-Object { $_.GetName().Name -eq 'UIAutomationClientsideProviders' } | Select-Object -First 1
    [System.Windows.Automation.ClientSettings]::RegisterClientSideProviderAssembly($providers.GetName())
    $stage = 'input'
    $request = [Console]::In.ReadToEnd() | ConvertFrom-Json
    $stage = 'root'
    $root = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr][long]$request.hwnd)
    if ($null -eq $root -or $root.Current.ProcessId -ne $request.pid) { throw 'wrong target' }
    $region = $request.region
    $stage = 'descendants'
    $all = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
    if ($all.Count -gt 1000) { throw 'too many controls' }
    $candidates = @()
    $diagnostics = @()
    foreach ($node in $all) {
        $stage = 'control metadata'
        $c = $node.Current
        if ($c.ProcessId -ne $request.pid -or $c.IsOffscreen -or $c.IsPassword) { continue }
        $b = $c.BoundingRectangle
        # Only sizeable transcript panes wholly inside the selected message area.
        if ($b.Width -lt $region.width * 0.4 -or $b.Height -lt $region.height * 0.25) { continue }
        if ($b.Left -lt $region.left -or $b.Top -lt $region.top -or $b.Right -gt ($region.left + $region.width) -or $b.Bottom -gt ($region.top + $region.height)) { continue }
        $type = $c.ControlType.ProgrammaticName
        $diagnostics += "$type/$($c.ClassName)"
        $stage = 'patterns'
        $value = $null
        $hasValue = $node.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern, [ref]$value)
        # Never read a writable editor (composer/search), even if it overlaps the region.
        if ($hasValue -and -not $value.Current.IsReadOnly) { continue }
        $textPattern = $null
        $hasText = $node.TryGetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern, [ref]$textPattern)
        if ($c.ControlType -eq [System.Windows.Automation.ControlType]::Edit -and -not $hasValue) {
            if (-not $hasText) { continue }
            $readOnly = $textPattern.DocumentRange.GetAttributeValue([System.Windows.Automation.TextPattern]::IsReadOnlyAttribute)
            if ($readOnly -isnot [bool] -or -not $readOnly) { continue }
        }
        $text = $null
        $source = ''
        $stage = 'read text'
        if ($hasText) {
            $range = $textPattern.DocumentRange
            $text = $range.GetText(32001)
            if ($text.Length -gt 32000) {
                $range.MoveEndpointByRange([System.Windows.Automation.TextPatternRangeEndpoint]::Start, $range, [System.Windows.Automation.TextPatternRangeEndpoint]::End)
                $null = $range.MoveEndpointByUnit([System.Windows.Automation.TextPatternRangeEndpoint]::Start, [System.Windows.Automation.TextUnit]::Character, -32000)
                $text = $range.GetText(32000)
                $newline = $text.IndexOf("`n")
                if ($newline -ge 0) { $text = $text.Substring($newline + 1) }
            }
            $source = 'Windows TextPattern'
        } elseif ($hasValue -and $value.Current.IsReadOnly) {
            $text = $value.Current.Value
            $source = 'Windows read-only ValuePattern'
        } elseif ($c.ControlType -eq [System.Windows.Automation.ControlType]::List -or $c.ControlType -eq [System.Windows.Automation.ControlType]::Document) {
            $rows = $node.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
            if ($rows.Count -gt 1000) { throw 'too many rows' }
            $names = @()
            foreach ($row in $rows) {
                $r = $row.Current
                if ($r.ProcessId -ne $request.pid -or $r.IsOffscreen -or $r.IsPassword) { continue }
                if ($r.ControlType -eq [System.Windows.Automation.ControlType]::Text -and $r.Name) {
                    $names += $r.Name
                }
            }
            if ($names.Count -gt 0) {
                $text = $names -join "`n"
                $source = 'Windows accessible transcript text'
            }
        }
        if ($null -ne $text) {
            if ($text.Length -gt 32000) {
                $text = $text.Substring($text.Length - 32000)
                $newline = $text.IndexOf("`n")
                if ($newline -ge 0) { $text = $text.Substring($newline + 1) }
            }
            $candidates += @{text=$text; source=$source; key=($node.GetRuntimeId() -join '.'); area=($b.Width * $b.Height); rect=@($b.Left,$b.Top,$b.Right,$b.Bottom)}
        }
    }
    $stage = 'select transcript'
    # Prefer the encompassing transcript if a provider also exposes its nested text panes.
    $candidates = @($candidates | Sort-Object area -Descending)
    if ($candidates.Count -gt 0) {
        $chosen = $candidates[0]
        foreach ($candidate in $candidates | Select-Object -Skip 1) {
            if ($candidate.rect[0] -lt $chosen.rect[0] -or $candidate.rect[1] -lt $chosen.rect[1] -or $candidate.rect[2] -gt $chosen.rect[2] -or $candidate.rect[3] -gt $chosen.rect[3]) { throw 'ambiguous transcript panes' }
        }
        @{ok=$true; text=$chosen.text; source=$chosen.source; key=$chosen.key} | ConvertTo-Json -Compress
    } else {
        # Metadata only; no captions, participant names, or message text in diagnostics.
        @{ok=$false; reason='unsupported'; controls=@($diagnostics | Select-Object -First 12)} | ConvertTo-Json -Compress
    }
} catch {
    @{ok=$false; reason='unavailable'; stage=$stage; error_type=$_.Exception.GetType().Name; error_id=$_.FullyQualifiedErrorId} | ConvertTo-Json -Compress
}
