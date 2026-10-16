import test from 'node:test';
import assert from 'node:assert/strict';
import {SPORTS} from '../src/core/constants.js';
import {saveProfile,selectProfile,deleteProfile} from '../src/core/profiles.js';
import {parseRestingCSV,saveRestingHR,readRestingHR,weeklyRestingHR} from '../src/core/health.js';
import {startSession,pauseSession,resumeSession,elapsedSession,readSession,sessionActivity,discardSession} from '../src/core/live-session.js';
import {parseActivityFile} from '../src/services/activity-import.js';
import {saveImportedActivities,readActivities,validateActivity} from '../src/core/activity.js';
import {renderAccount} from '../src/pages/account.js';
import {renderActivityLog} from '../src/pages/activity-log.js';
const data=new Map();globalThis.localStorage={getItem:k=>data.get(k)??null,setItem:(k,v)=>data.set(k,String(v)),removeItem:k=>data.delete(k)};
test('Live timer excludes paused time, resumes and remains isolated by profile',()=>{
 data.clear();const a=saveProfile({name:'Timer A',city:'santiago',sports:[]});const now=Date.now();startSession(SPORTS[0],now);assert.equal(elapsedSession(readSession(),now+60000),60000);pauseSession(now+60000);assert.equal(elapsedSession(readSession(),now+90000),60000);resumeSession(now+100000);assert.equal(elapsedSession(readSession(),now+110000),70000);pauseSession(now+110000);assert.equal(sessionActivity().minutes,1.17);
 saveProfile({name:'Timer B',city:'santiago',sports:[]});assert.equal(readSession(),null);selectProfile(a.id);assert.equal(elapsedSession(),70000);discardSession();assert.equal(readSession(),null);
});
test('Seven calendar days use only resting measurements, average days equally and handle empty data',()=>{
 const r=weeklyRestingHR([{date:'2026-10-09',value:200},{date:'2026-10-10',value:60},{date:'2026-10-10',value:64},{date:'2026-10-16',value:58},{date:'2026-10-17',value:200}], '2026-10-16');assert.equal(r.average,60);assert.equal(r.days,2);assert.equal(r.from,'2026-10-10');assert.equal(weeklyRestingHR([], '2026-10-16').average,null);
});
test('Resting CSV validates atomically, replaces days and stays isolated',()=>{
 data.clear();const a=saveProfile({name:'Health A',city:'santiago',sports:[]});const rows=parseRestingCSV('date;resting_hr;device\n2026-01-01;62;Reloj\n2026-01-02;58;Reloj');saveRestingHR(rows);saveRestingHR([{date:'2026-01-01',value:64,source:'Reloj'}]);assert.equal(readRestingHR().length,2);assert.equal(readRestingHR().find(x=>x.date==='2026-01-01').value,64);assert.throws(()=>parseRestingCSV('date,resting_hr\n2026-02-30,62'));
 const b=saveProfile({name:'Health B',city:'santiago',sports:[]});assert.equal(readRestingHR().length,0);selectProfile(a.id);deleteProfile(a.id);assert.equal([...data.keys()].some(k=>k.includes(`profile.${a.id}.`)),false);selectProfile(b.id);
});
test('Activity CSV supports quotes, preserves origin and HR, rejects invalid rows and reimports',()=>{
 data.clear();const file='date,sport,minutes,distance,elevation,heart_rate,notes\n2026-01-02,Trekking,60,5,100,125,"Cerros, senderos"';const rows=parseActivityFile(file,'reloj.csv',SPORTS[0]);assert.equal(rows[0].kind,'Cerros, senderos');assert.equal(rows[0].heartRate,125);saveImportedActivities(rows);assert.equal(readActivities()[0].source,'watch');assert.throws(()=>saveImportedActivities(rows),/ya importaste/);assert.equal(readActivities().length,1);
 assert.throws(()=>parseActivityFile(file.replace('2026-01-02','2026-02-30'),'reloj.csv',SPORTS[0]));assert.throws(()=>parseActivityFile('bytes','reloj.fit',SPORTS[0]),/FIT/);assert.throws(()=>validateActivity({...rows[0],heartRate:999}));
});
test('Profile contains the editable base data and resting average controls, activity has three modes',()=>{
 data.clear();saveProfile({name:'Base Test',city:'santiago',sports:[]});const markup=renderAccount();for(const id of ['age','height','weight','resting','active','lifestyle','weekly-hr-enabled','resting-file'])assert.ok(markup.includes(`id="${id}"`));const log=renderActivityLog();for(const mode of ['manual','live','watch'])assert.ok(log.includes(`data-activity-mode="${mode}"`));assert.match(markup,/Mis datos base/);
});
