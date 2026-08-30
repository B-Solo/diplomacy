# England Map Provenance

## Variant

This map reconstructs the six-player **Anarchy in the UK** variant created by amisond and Evansevern and adapted for webDiplomacy by amisond and Acquiesce.
The configured game begins in Spring 2000 and uses the standard Diplomacy rules with the variant's documented map exceptions.

## Sources

- [vDiplomacy variant description and special rules](https://www.vdiplomacy.net/variants.php?variantID=79)
- [Authoritative territory and border data](https://github.com/Sleepcap/vDiplomacy/blob/master/variants/AnarchyInTheUK/install.php)
- [Authoritative starting units](https://github.com/Sleepcap/vDiplomacy/blob/master/variants/AnarchyInTheUK/classes/adjudicatorPreGame.php)
- [Original map resources](https://github.com/Sleepcap/vDiplomacy/tree/master/variants/AnarchyInTheUK/resources)

The upstream vDiplomacy repository distributes this variant under the GNU Affero General Public License version 3 or later.

## Reconstruction

The clean SVG is traced from the upstream flat-colour map rather than from the labelled reference screenshot.
Every playable region is a separate SVG path with a stable `territory-...` identifier.
The SVG contains no territory text, supply-centre markers, ownership colours or units.

The army and fleet assets are clean vector interpretations of the military
silhouette style in the supplied `references/playdiplomacy` image, using a tank
and warship respectively. They use `currentColor` for their power-coloured fill
and a fixed dark outline. The tank has an intrinsic footprint of 42×24 pixels,
while the destroyer-style warship uses a long, low 52×18-pixel footprint.

The reconstruction script checks all 74 playable territories and 34 supply centres against the source data.
It also compares vector-map contact with the complete authoritative topology and permits exactly these non-visual connections:

- North Atlantic to North Sea for fleets.
- Gwynedd to Anglesey for armies and fleets.
- Hampshire to Isle of Wight for armies and fleets.

Devon and Dyfed retain their authoritative north and south fleet coasts.
Seven shared land borders between ordinary coastal provinces are marked as
fleet removals because the provinces' coastlines do not meet: Cumbria–Durham,
Cumbria–N.Yorkshire, Cumbria–Northumberland, Dorset–Somerset,
Durham–N.Yorkshire, Durham–Northumberland and Lancashire–N.Yorkshire.
