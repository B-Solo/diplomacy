<#!
.SYNOPSIS
Builds the editor-ready Classic Diplomacy base map from map_red.svg.

.DESCRIPTION
The source SVG uses labelled Inkscape layers.  This keeps only the province
outlines, assigns the editor's `territory-` IDs, and deliberately omits every
label, supply-centre marker, power name, and unit marker.
#>

param(
    [string]$Source = 'C:\Users\Ben\Downloads\map_red.svg',
    [string]$Output = (Join-Path $PSScriptRoot '..\maps\classic\map.svg')
)

$ErrorActionPreference = 'Stop'

$ids = @{
    'Eastern Mediterranean Sea' = 'eastern-mediterranean'; 'Mid Atlantic Ocean' = 'mid-atlantic';
    'Barents Sea' = 'barents-sea'; 'Norwegian Sea' = 'norwegian-sea'; 'North Atlantic Ocean' = 'north-atlantic';
    'West Mediterreanan' = 'western-mediterranean'; 'Aegean Sea' = 'aegean-sea'; 'Tyrhennian Sea' = 'tyrrhenian-sea';
    'Gulf of Lyon' = 'gulf-of-lyon'; 'Adriatic Sea' = 'adriatic-sea'; 'Helgoland' = 'helgoland-bight';
    'Skagerak' = 'skagerrak'; 'North Sea' = 'north-sea'; 'Black Sea' = 'black-sea';
    'English Channel' = 'english-channel'; 'Irish sea' = 'irish-sea'; 'Baltic Sea' = 'baltic-sea';
    'Gulf of Botnia' = 'gulf-of-bothnia'; 'Ionian Sea' = 'ionian-sea';
    'Syria' = 'syria'; 'Smyrna' = 'smyrna'; 'Constantinople' = 'constantinople'; 'Ankera' = 'ankara'; 'Armenia' = 'armenia';
    'Apulia' = 'apulia'; 'Piedmont' = 'piedmont'; 'Tuscany' = 'tuscany'; 'Napoli' = 'naples'; 'Rome' = 'rome'; 'Venice' = 'venice';
    'Galacia' = 'galicia'; 'Vienna' = 'vienna'; 'Bohemia' = 'bohemia'; 'Trieste' = 'trieste'; 'Tyrolia' = 'tyrolia'; 'Budapest' = 'budapest';
    'Marseille' = 'marseilles'; 'Picardy' = 'picardy'; 'Brest' = 'brest'; 'Gascogny' = 'gascony'; 'Paris' = 'paris'; 'Burgundy' = 'burgundy';
    'Silesia' = 'silesia'; 'Munich' = 'munich'; 'Ruhr' = 'ruhr'; 'Berlin' = 'berlin'; 'Kiel' = 'kiel'; 'Prussia' = 'prussia';
    'Moscow' = 'moscow'; 'Sevastopol' = 'sevastopol'; 'Saint Petersburg' = 'saint-petersburg'; 'Ukraine' = 'ukraine'; 'Warsaw' = 'warsaw'; 'Livonia' = 'livonia';
    'Liverpool' = 'liverpool'; 'Edinburgh' = 'edinburgh'; 'London' = 'london'; 'Wales' = 'wales'; 'York' = 'yorkshire'; 'Ireland' = 'ireland'; 'Clyde' = 'clyde';
    'Tunis' = 'tunis'; 'Serbia' = 'serbia'; 'Greece' = 'greece'; 'Albania' = 'albania'; 'Bulgaria' = 'bulgaria'; 'Portugal' = 'portugal';
    'Spain' = 'spain'; 'Romania' = 'rumania'; 'Belgium' = 'belgium'; 'Holland' = 'holland'; 'Danmark' = 'denmark';
    'Finland' = 'finland'; 'Norway' = 'norway'; 'Sweden' = 'sweden'; 'North Africa' = 'north-africa'
}

$doc = [xml](Get-Content -Raw -LiteralPath $Source)
$namespaces = New-Object System.Xml.XmlNamespaceManager($doc.NameTable)
$namespaces.AddNamespace('svg', 'http://www.w3.org/2000/svg')
$namespaces.AddNamespace('ink', 'http://www.inkscape.org/namespaces/inkscape')
$provinceLayer = $doc.SelectSingleNode('//*[@id="g4738"]', $namespaces)
if ($null -eq $provinceLayer) { throw 'Could not find the source Provinces layer.' }
$sourceRoot = $doc.SelectSingleNode('//*[@id="g7772"]', $namespaces)
$border = $doc.SelectSingleNode('//*[@id="Selection-6"]', $namespaces)
if ($null -eq $sourceRoot -or $null -eq $border) {
    throw 'Could not find the source map transform or its single border path.'
}

$paths = @{}
foreach ($path in $provinceLayer.SelectNodes('.//svg:path', $namespaces)) {
    $label = $path.GetAttribute('label', 'http://www.inkscape.org/namespaces/inkscape')
    if ($ids.ContainsKey($label)) { $paths[$ids[$label]] = $path.GetAttribute('d') }
}
if ($paths.Count -ne $ids.Count) {
    $missing = $ids.Values | Where-Object { -not $paths.ContainsKey($_) }
    throw "The source map did not contain all Classic territories: $($missing -join ', ')."
}

$seaIds = @(
    'eastern-mediterranean', 'mid-atlantic', 'barents-sea', 'norwegian-sea', 'north-atlantic', 'western-mediterranean',
    'aegean-sea', 'tyrrhenian-sea', 'gulf-of-lyon', 'adriatic-sea', 'helgoland-bight', 'skagerrak', 'north-sea',
    'black-sea', 'english-channel', 'irish-sea', 'baltic-sea', 'gulf-of-bothnia', 'ionian-sea'
)
$impassable = @('Shetland Islands', 'Faero Islands', 'Cypres', 'Rhodos', 'Sardina', 'Corsica', 'Mallorca', 'Switzerland')

$lines = [System.Collections.Generic.List[string]]::new()
$lines.Add('<?xml version="1.0" encoding="UTF-8"?>')
$lines.Add('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 3044.0415 2401.3554" role="img" aria-label="Classic Diplomacy blank map">')
$lines.Add('  <style>.territory { fill-rule:evenodd; stroke:#343a3a; stroke-width:1.35; stroke-linejoin:round; } .land { fill:#d0c9aa; } .sea { fill:#9ebbd2; } .impassable { fill:#777870; stroke:#343a3a; stroke-width:1.35; stroke-linejoin:round; } .map-borders { display:none; }</style>')
$lines.Add('  <rect id="map-background" width="100%" height="100%" fill="#9ebbd2"/>')
$lines.Add("  <g id=`"map-geometry`" transform=`"$($sourceRoot.GetAttribute('transform'))`">")
$lines.Add("    <g id=`"territories`" transform=`"$($provinceLayer.GetAttribute('transform'))`">")
foreach ($entry in $paths.GetEnumerator() | Sort-Object Key) {
    $kind = if ($seaIds -contains $entry.Key) { 'sea' } else { 'land' }
    $lines.Add("      <path id=`"territory-$($entry.Key)`" class=`"territory $kind`" d=`"$($entry.Value)`"/>")
}
$lines.Add('    </g>')
$lines.Add("    <g id=`"impassable-regions`" transform=`"$($provinceLayer.GetAttribute('transform'))`">")
foreach ($label in $impassable) {
    $node = $provinceLayer.SelectSingleNode(".//svg:path[@ink:label='$label']", $namespaces)
    if ($null -eq $node) { throw "Could not find impassable source region: $label" }
    $id = ($label.ToLowerInvariant() -replace '[^a-z0-9]+', '-').Trim('-')
    $lines.Add("      <path id=`"impassable-$id`" class=`"impassable`" d=`"$($node.GetAttribute('d'))`"/>")
}
$lines.Add('    </g>')
$lines.Add("    <path id=`"map-borders`" class=`"map-borders`" d=`"$($border.GetAttribute('d'))`"/>")
$lines.Add('  </g>')
$lines.Add('</svg>')

$directory = Split-Path -Parent $Output
New-Item -ItemType Directory -Force -Path $directory | Out-Null
[System.IO.File]::WriteAllLines((Resolve-Path $directory | Join-Path -ChildPath (Split-Path -Leaf $Output)), $lines, [System.Text.UTF8Encoding]::new($false))
Write-Output "Wrote $Output with $($paths.Count) playable territories."
