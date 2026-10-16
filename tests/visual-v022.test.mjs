import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {renderHome} from '../src/pages/home.js';
import {renderSettings} from '../src/pages/settings.js';
import {CITIES} from '../src/core/constants.js';
import {getCity,setCity} from '../src/core/state.js';
const css=readFileSync(new URL('../styles/app.css',import.meta.url),'utf8');
const homeCode=readFileSync(new URL('../src/pages/home.js',import.meta.url),'utf8');
test('El inicio conserva clima y selector manual de ciudad',()=>{
 const markup=renderHome();
 assert.match(markup,/id="home-city"/);
 assert.match(markup,/id="weather-value"/);
 assert.match(markup,/Salida del sol/);
 assert.match(markup,/Puesta del sol/);
 assert.match(markup,/Organizar mi actividad/);
 for(const city of CITIES)assert.ok(markup.includes(`value="${city.id}"`));
});
test('La preferencia de localidad es compartida con Ajustes y Explorar',()=>{
 const original=getCity().id;
 const alternative=CITIES.find(c=>c.id!==original);
 try{setCity(alternative.id);assert.equal(getCity().id,alternative.id);assert.ok(renderSettings().includes('id="settings-city"'));assert.ok(renderHome().includes(`value="${alternative.id}" selected`));}
 finally{setCity(original)}
});
test('Tipografía, tarjetas cuadradas y tamaño táctil conservado',()=>{
 assert.match(css,/Inter/);
 assert.doesNotMatch(css,/Manrope/);
 assert.match(css,/--brand:#c8102e/);
 assert.match(css,/--lime:#c8102e/);
 assert.match(css,/\.hero-secondary\{/);
 assert.match(css,/--radius:10px/);
 assert.match(css,/\.home-city-select\{/);
 assert.match(css,/min-height:44px/);
 assert.match(homeCode,/addEventListener\('change'/);
});
