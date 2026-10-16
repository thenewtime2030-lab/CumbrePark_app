/* Prueba de lógica del Service Worker sin navegador ni red. */
import {readFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {runInNewContext} from 'node:vm';
import assert from 'node:assert/strict';
const root = resolve(fileURLToPath(new URL('..', import.meta.url)));
const js = await readFile(resolve(root,'dist/service-worker.js'),'utf8');
const scope='https://example.com/CumbrePark_app/';
const listeners=new Map();
const saved=new Map();
let claimed=false;
const cacheNameKeys=new Set(['cumbrepark-pwa-ancienne']);
const cache={addAll:async urls=>{for (const u of urls){assert.ok(u.startsWith(scope));saved.set(u,{ok:true,url:u})}}};
const caches={
  open:async key=>{cacheNameKeys.add(key);return cache},
  match:async url=>saved.get(url),
  keys:async()=>[...cacheNameKeys],
  delete:async key=>cacheNameKeys.delete(key)
};
const self={registration:{scope},location:{origin:'https://example.com'},
  clients:{claim:async()=>{claimed=true}},skipWaiting:async()=>{},
  addEventListener:(kind,fn)=>listeners.set(kind,fn)};
runInNewContext(js,{self,caches,URL,Promise,Response,fetch:async()=>{throw Error('Sin internet')}});
async function fire(type,options={}){
  let waiting=null,response=null;
  listeners.get(type)({ ...options, waitUntil(p){waiting=p}, respondWith(p){response=p} });
  if(waiting)await waiting;
  return response?await response:null;
}
await fire('install');
assert.ok(saved.size>=35, `Precaché incompleto: ${saved.size}`);
assert.ok(saved.has(`${scope}index.html`));
await fire('activate');
assert.equal(claimed,true);
assert.ok(!cacheNameKeys.has('cumbrepark-pwa-ancienne'));
const offline=await fire('fetch',{request:{method:'GET',url:scope,mode:'navigate'}});
assert.equal(offline.url,`${scope}index.html`);
const external=await fire('fetch',{request:{method:'GET',url:'https://api.met.no/weatherapi/any',mode:'navigate'}});
assert.equal(external,null);
console.log('Service Worker: precaché, ruta de subcarpeta, actualización y apertura offline aprobados.');
