'use strict';
const fs=require('fs'),assert=require('assert');
const html=fs.readFileSync('coordination/nox-r8/overrides/src/index.html','utf8');
const themes=['obsidian','aurora','copper','nebula','frost'];
for(const theme of themes) assert(html.includes("'"+theme+"'"),'MISSING_THEME_'+theme);
assert(html.includes('id="noxThemeToggle"'),'NO_SWITCHER');
assert(html.includes("noxThemeToggle.addEventListener('click'"),'NO_CLICK_HANDLER');
assert(html.includes('document.body.dataset.noxTheme=id'),'NOT_SHARED_BACKGROUND');
assert(html.includes('aria-label'),'NO_ACCESSIBLE_LABEL');
assert(html.includes('prefers-reduced-motion:reduce'),'MOTION_GUARD');
assert((html.match(/<button class="core /g)||[]).length===8,'CORE_COUNT_CHANGED');
for(const route of ['consciousness','atlas','reflection','nexus','forge','core','voice','persona'])
  assert(html.includes('data-route="'+route+'"'),'MISSING_ROUTE_'+route);
assert(html.includes('route(\'consciousness\');'),'ORIGINAL_NAVIGATION_MISSING');
console.log('NOX_R8_FIVE_THEMES_SOURCE_PASS 8 CORES / 5 VISUAL MODES');
