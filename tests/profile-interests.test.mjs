import test from 'node:test';
import assert from 'node:assert/strict';
import {saveProfile,selectProfile,profileSports,updateProfileSports} from '../src/core/profiles.js';
import {setItem} from '../src/core/storage.js';
import {renderAccount} from '../src/pages/account.js';
import {renderSports} from '../src/pages/sports.js';
import {renderCommunity} from '../src/pages/community.js';
const data=new Map();globalThis.localStorage={getItem:k=>data.get(k)??null,setItem:(k,v)=>data.set(k,String(v)),removeItem:k=>data.delete(k)};
test('One sports selector in Mi perfil, with shared interests in the technical and community views',()=>{
 data.clear();const a=saveProfile({name:'Shared interests',city:'santiago',sports:['Trekking','Snowboard']});
 setItem(`profile.${a.id}.athleteProfile`,{sports:[],height:170});
 const markup=renderAccount();assert.equal((markup.match(/name="account-sport"/g)||[]).length,23);assert.doesNotMatch(markup,/name="favorite-sport"/);assert.match(markup,/2\/3/);
 assert.match(renderSports(),/value="Snowboard" checked/);assert.match(renderCommunity(),/Trekking, Snowboard/);
 updateProfileSports(['Kayak de mar']);assert.deepEqual(profileSports(),['Kayak de mar']);assert.match(renderAccount(),/value="Kayak de mar" checked/);
 const b=saveProfile({name:'Second interests',city:'santiago',sports:['MTB']});assert.deepEqual(profileSports(),['MTB']);selectProfile(a.id);assert.deepEqual(profileSports(),['Kayak de mar']);
});
test('Legacy technical interests remain available, while explicitly clearing interests stays empty',()=>{
 data.clear();setItem('profiles.v1',{items:[{id:'old',name:'Legacy',city:'santiago',sports:[],createdAt:'2026-01-01'}],activeId:'old'});setItem('profile.old.athleteProfile',{sports:['Escalada']});assert.deepEqual(profileSports(),['Escalada']);updateProfileSports([]);assert.deepEqual(profileSports(),[]);
});
