# Embeds the deck's fonts (Inter, Consolas, Segoe UI) in Mirsad_Deck.pptx through PowerPoint, so the
# slides keep their layout on a computer without those fonts. Needs Windows, PowerPoint, and Inter
# installed. Run after build_pptx.cjs:  powershell -File deck\tools\embed_fonts.ps1
$deck = Join-Path $PSScriptRoot "..\Mirsad_Deck.pptx" | Resolve-Path
$tmp = Join-Path $env:TEMP "Mirsad_Deck_embedded.pptx"
$pp = New-Object -ComObject PowerPoint.Application
try {
    $p = $pp.Presentations.Open($deck.Path, $true, $false, $false)
    $p.SaveAs($tmp, 24, -1)  # 24 = ppSaveAsOpenXMLPresentation, -1 = embed TrueType fonts
    $p.Close()
} finally {
    $pp.Quit()
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($pp) | Out-Null
}
Move-Item -Force $tmp $deck.Path
"Embedded fonts in $($deck.Path) ($((Get-Item $deck.Path).Length) bytes)"
