import {cp, mkdir, readdir, readFile, rm, writeFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {join, relative, resolve, sep} from 'node:path';
import {fileURLToPath} from 'node:url';

const ROOT = resolve(fileURLToPath(new URL('..', import.meta.url)));
const DIST = join(ROOT, 'dist');
const resources = ['index.html', 'manifest.webmanifest', '.nojekyll', 'src', 'styles', 'assets'];

async function walk(dir) {
  let output = [];
  for (const entry of await readdir(dir, {withFileTypes:true})) {
    if (entry.isSymbolicLink()) throw Error(`Enlace simbólico no admitido: ${entry.name}`);
    const path = join(dir, entry.name);
    if (entry.isDirectory()) output = output.concat(await walk(path));
    else if (entry.isFile()) output.push(path);
  }
  return output;
}

await rm(DIST, {recursive:true, force:true});
await mkdir(DIST, {recursive:true});
for (const resource of resources) await cp(join(ROOT, resource), join(DIST, resource), {recursive:true});
const files = (await walk(DIST)).map(path => relative(DIST, path).split(sep).join('/'));
const sha = createHash('sha256');
for (const file of [...files].sort()) {
  sha.update(file);
  sha.update(await readFile(join(DIST, file)));
}
sha.update(await readFile(join(ROOT, 'scripts', 'service-worker.template.js')));
const version = sha.digest('hex').slice(0, 14);
// Version every module URL so existing browser caches cannot mix releases.
for (const file of files.filter(file=>file.endsWith('.js'))) {
  const path=join(DIST,file);
  const source=await readFile(path,'utf8');
  await writeFile(path,source.replace(/(from\s*['"])(\.[^'"]+\.js)(['"])/g, `$1$2?v=${version}$3`));
}
const htmlPath=join(DIST,'index.html');
await writeFile(htmlPath,(await readFile(htmlPath,'utf8')).replace('./src/app.js\"', `./src/app.js?v=${version}\"`).replace('./styles/app.css\"', `./styles/app.css?v=${version}\"`));
const precache = ['./', ...files.filter(file => !file.startsWith('.') && file !== 'service-worker.js').flatMap(file=>/\.(js|css)$/.test(file)?[`./${file}`,`./${file}?v=${version}`]:[`./${file}`])];
const template = await readFile(join(ROOT, 'scripts', 'service-worker.template.js'), 'utf8');
await writeFile(join(DIST, 'service-worker.js'), template
    .replace('__CACHE_VERSION__', JSON.stringify(version))
    .replace('__PRECACHE_PATHS__', JSON.stringify(precache)));
await writeFile(join(DIST, 'build-info.json'), JSON.stringify({version, files:files.length, generatedAt: new Date().toISOString()},null,2));
console.log(`CumbrePark PWA: dist/ creada, ${files.length} recursos, revisión ${version}.`);
