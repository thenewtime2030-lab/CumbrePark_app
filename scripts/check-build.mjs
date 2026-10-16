import {access, readFile, readdir} from 'node:fs/promises';
import {join,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';
const root=resolve(fileURLToPath(new URL('..',import.meta.url)));
const dist=join(root,'dist');
for(const file of ['index.html','manifest.webmanifest','service-worker.js','src/app.js','styles/app.css','assets/icons/icon-192.png','assets/icons/icon-512.png'])
 await access(join(dist,file));
const html=await readFile(join(dist,'index.html'),'utf8');
assert.match(html, /rel="manifest"/);
assert.match(html, /src="\.\/src\/app\.js\?v=[a-f0-9]+"/);
const sw=await readFile(join(dist,'service-worker.js'),'utf8');
assert.ok(sw.includes('cumbrepark-pwa-'));
assert.ok(!sw.includes('__PRECACHE_PATHS__'));
assert.ok(!sw.includes('__CACHE_VERSION__'));
const entry=await readFile(join(dist,'src/app.js'),'utf8');
assert.ok(!/from\s*['"]\.[^'"]+\.js['"]/.test(entry),'Unversioned module import');
for(const [,url] of entry.matchAll(/from\s*['"]([^'"]+)['"]/g)){assert.ok(sw.includes('src/'+url.replace(/^\.\//,'')),'Module missing from precache: '+url);}
const manifest=JSON.parse(await readFile(join(dist,'manifest.webmanifest'),'utf8'));
assert.equal(manifest.display,'standalone');
assert.ok(manifest.icons.some(icon=>icon.sizes==='192x192'));
assert.ok(manifest.icons.some(icon=>icon.sizes==='512x512'));
assert.equal((await readdir(dist)).includes('tests'),false);
console.log('Verificación de PWA: rutas, iconos, manifest, caché offline y dist correctos.');
