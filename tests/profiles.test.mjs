import test from 'node:test';
import assert from 'node:assert/strict';
import {saveProfile,activeProfile,selectProfile,deleteProfile,listProfiles} from '../src/core/profiles.js';
import {readActivities,saveActivity} from '../src/core/activity.js';
import {getItem,setItem} from '../src/core/profile-storage.js';
import {activitySummary} from '../src/core/summary.js';
import {renderSummary} from '../src/pages/summary.js';
import {renderAccount} from '../src/pages/account.js';
import {SPORTS} from '../src/core/constants.js';
const data=new Map();
globalThis.localStorage={getItem:k=>data.get(k)??null,setItem:(k,v)=>data.set(k,String(v)),removeItem:k=>data.delete(k)};
const input={sport:SPORTS[0],date:'2026-01-03',minutes:30,distance:4,elevation:20};
test('Profiles isolate activities and personal data, preserve guests, persist selection and delete only their data',()=>{
 data.clear();saveActivity(input);
 const a=saveProfile({name:'Clemente',city:'santiago',sports:[SPORTS[0]]});
 assert.equal(activeProfile().id,a.id);assert.equal(readActivities().length,0);
 saveActivity(input);setItem('favorites',[{id:'a'}]);setItem('athleteProfile',{height:180});
 const b=saveProfile({name:'Belén',city:'coyhaique',sports:[]});
 assert.equal(readActivities().length,0);assert.deepEqual(getItem('favorites',[]),[]);assert.deepEqual(getItem('athleteProfile',{}),{});
 saveActivity({...input,distance:9});selectProfile(a.id);
 assert.equal(readActivities()[0].distance,4);assert.equal(getItem('athleteProfile').height,180);
 saveProfile({name:'Cleme',city:'santiago',sports:[]},a.id);assert.equal(listProfiles().length,2);
 deleteProfile(a.id);assert.equal(activeProfile(),null);assert.equal(readActivities().length,1);
 assert.equal([...data.keys()].some(k=>k.includes(`profile.${a.id}.`)),false);
 selectProfile(b.id);assert.equal(readActivities()[0].distance,9);
 selectProfile(null);assert.equal(readActivities()[0].distance,4);
});
test('Reject invalid profiles and surface storage failures',()=>{
 data.clear();assert.throws(()=>saveProfile({name:'A',city:'santiago',sports:[]}));assert.throws(()=>saveProfile({name:'Valid',city:'invalid',sports:[]}));assert.throws(()=>selectProfile('missing'));
 const setter=localStorage.setItem;localStorage.setItem=()=>{throw Error('quota')};assert.throws(()=>saveProfile({name:'Valid',city:'santiago',sports:[]}),/No se pudo guardar/);localStorage.setItem=setter;
});
test('Summary groups month, weeks and disciplines without inventing records',()=>{
 const s=activitySummary([{...input},{...input,date:'2026-01-08',minutes:60,distance:6},{...input,date:'2026-02-01',minutes:100}], '2026-01');
 assert.equal(s.count,2);assert.equal(s.minutes,90);assert.equal(s.distance,10);assert.equal(s.activeDays,2);assert.equal(s.weeks[0].minutes,30);assert.equal(s.weeks[1].minutes,60);assert.equal(s.sports[0].count,2);
 assert.equal(activitySummary([], '2024-02').weeks.length,5);assert.equal(activitySummary([], '2025-02').weeks.length,4);
});
test('Profile names are escaped and empty summary has no fabricated activity',()=>{
 data.clear();saveProfile({name:'<img src=x>',city:'santiago',sports:[]});assert.doesNotMatch(renderAccount(),/<img src=x>/);assert.match(renderAccount(),/&lt;img/);assert.match(renderSummary(),/No hay actividades/);assert.match(renderSummary(),/summary-month/);
});
