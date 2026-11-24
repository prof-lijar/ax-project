# A session holds one UI Automation element from one explicitly selected window.
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type 'using System; using System.Runtime.InteropServices;
public static class VoyagerDesktop {
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern IntPtr SetThreadDpiAwarenessContext(IntPtr context);
}'
$null = [VoyagerDesktop]::SetThreadDpiAwarenessContext([IntPtr](-4))
$ae = [System.Windows.Automation.AutomationElement]
$root = $null
$field = $null

function Get-EditorPattern($node) {
    $c = $node.Current
    if ($c.ProcessId -ne $targetPid -or $c.IsOffscreen -or $c.IsPassword -or
        !$c.IsEnabled -or !$c.IsKeyboardFocusable -or
        $c.ControlType -ne [System.Windows.Automation.ControlType]::Edit -or
        $c.ClassName -cnotmatch '^TextObjectTextArea(?:_QML(?:TYPE)?_[0-9]+)*$') { return }
    $pattern = $null
    if ($node.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern, [ref]$pattern) -and
        !$pattern.Current.IsReadOnly) { return $pattern }
}

function Get-Bounds($node) {
    $b = $node.Current.BoundingRectangle
    if ($b.IsEmpty -or $b.Width -le 0 -or $b.Height -le 0) { throw 'bounds' }
    return @([int][Math]::Floor($b.Left), [int][Math]::Floor($b.Top),
             [int][Math]::Ceiling($b.Right), [int][Math]::Ceiling($b.Bottom))
}

while ($null -ne ($line = [Console]::In.ReadLine())) {
    $reason = 'unavailable'
    try {
        $r = $line | ConvertFrom-Json
        $result = @{ok = $true}
        if ($r.op -eq 'locate') {
            $hwnd = [IntPtr][long]$r.hwnd
            $targetPid = [int]$r.pid
            $root = $ae::FromHandle($hwnd)
            if ($root.Current.ProcessId -ne $targetPid) { throw 'root' }
            $condition = [System.Windows.Automation.PropertyCondition]::new(
                $ae::ControlTypeProperty, [System.Windows.Automation.ControlType]::Edit)
            $edits = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, $condition)
            $found = @(
                foreach ($edit in $edits) {
                    if ($null -ne (Get-EditorPattern $edit)) { $edit }
                }
            )
            if ($found.Count -ne 1) {
                $reason = if ($found.Count -eq 0) { 'missing' } else { 'ambiguous' }
                throw 'selection'
            }
            $field = $found[0]
            $id = $field.GetRuntimeId() -join '.'
            $result.bounds = Get-Bounds $field
            $result.id = $id
        } else {
            if (!$field -or $root.Current.ProcessId -ne $targetPid -or
                [VoyagerDesktop]::GetForegroundWindow() -ne $hwnd) { $reason = 'window'; throw 'window' }
            $pattern = Get-EditorPattern $field
            if (!$pattern -or ($field.GetRuntimeId() -join '.') -ne $id) { throw 'field' }
            # A Qt process can host several chats. Keep the original element under the same root.
            $ancestor = $field
            for ($level = 0; $level -lt 64 -and $ancestor; $level++) {
                if ([System.Windows.Automation.Automation]::Compare($root, $ancestor)) { break }
                $ancestor = [System.Windows.Automation.TreeWalker]::RawViewWalker.GetParent($ancestor)
            }
            if (!$ancestor -or $level -eq 64) { $reason = 'window'; throw 'root changed' }
            $bounds = Get-Bounds $field
            if ($r.op -ne 'bounds' -and ($bounds -join ',') -ne ($r.bounds -join ',')) { $reason = 'moved'; throw 'bounds' }
            if ($r.op -eq 'focus') {
                $focused = $ae::FocusedElement
                if (!$focused -or ![System.Windows.Automation.Automation]::Compare($focused, $field)) {
                    $field.SetFocus()
                    for ($attempt = 0; $attempt -lt 12; $attempt++) {
                        $focused = $ae::FocusedElement
                        if ($focused -and [System.Windows.Automation.Automation]::Compare($focused, $field)) { break }
                        Start-Sleep -Milliseconds 50
                    }
                }
            }
            if ($r.op -notin 'observe','bounds') {
                $focused = $ae::FocusedElement
                if ([VoyagerDesktop]::GetForegroundWindow() -ne $hwnd -or !$focused -or ![System.Windows.Automation.Automation]::Compare($focused, $field)) {
                    $reason = 'focus'; throw 'focus'
                }
            }
            switch ($r.op) {
                'bounds' { $result.bounds = $bounds }
                'focus' {}
                'check' {}
                'write' { $pattern.SetValue([string]$r.text) }
                { $_ -in 'read','observe' } {
                    $value = $pattern.Current.Value
                    if ($value.Length -gt 4096) { $reason = 'length'; throw 'length' }
                    $result.text = [string]$value
                }
                default { throw 'unknown command' }
            }
        }
    } catch {
        # Never include provider exceptions, captions, or draft text in errors.
        $result = @{ok = $false; reason = $reason; line = [int]$_.InvocationInfo.ScriptLineNumber;
                    kind = $_.Exception.GetType().Name}
    }
    [Console]::WriteLine(($result | ConvertTo-Json -Compress))
}
