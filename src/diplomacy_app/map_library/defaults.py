"""Fixed application unit symbols shared by Placement and rendered games."""

DEFAULT_ARMY_SVG = b"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 52 28" width="42" height="24" role="img" color="#697474">
  <title>Army</title>
  <g fill="currentColor" stroke="#293333" stroke-width="1.8" stroke-linejoin="round">
    <path d="M5 18.5h37l4 3.5-4 4H8q-4 0-5.5-3.5z"/>
    <path d="m10 18.5 4-6.5h22l6 6.5z"/>
    <path d="M19 12V7.5h13l4 4.5z"/>
    <path d="M31 8.5h17.5q2 0 2 1.8t-2 1.7H34z"/>
  </g>
  <g fill="#293333">
    <circle cx="10" cy="22.5" r="2.2"/>
    <circle cx="18" cy="22.5" r="2.2"/>
    <circle cx="26" cy="22.5" r="2.2"/>
    <circle cx="34" cy="22.5" r="2.2"/>
    <circle cx="41" cy="22.5" r="2.2"/>
  </g>
</svg>
"""

DEFAULT_FLEET_SVG = b"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 72 24" width="52" height="18" role="img" color="#697474">
  <title>Fleet</title>
  <g fill="currentColor" stroke="#293333" stroke-width="1.7" stroke-linejoin="round">
    <path d="M2.5 14h55l11-5 1.5 2-6.5 7.5q-1.8 2-5.5 2H11q-5 0-7-3z"/>
    <path d="M13 14v-4h10l3-4.5h11l3 4.5h12v4z"/>
    <path d="M28 5.5V2h4.5v3.5zM35 5.5V3h4v4z"/>
    <path d="M8 14v-3h9v3zM51 14v-3h7l5-2v3l-5 2z"/>
  </g>
  <path d="M8 17h55M30.2 2V.8" fill="none" stroke="#293333" stroke-width="1.4" stroke-linecap="round"/>
</svg>
"""
