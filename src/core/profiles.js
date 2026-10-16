import {getItem,setItem,removeItem} from './storage.js';
import {CITIES,SPORTS} from './constants.js';
const KEY='profiles.v1';
export const PERSONAL_KEYS=['activities.v2','athleteProfile','favorites','event.drafts','academy.drafts','restingHR.v1','liveSession.v1'];
function database(){const x=getItem(KEY,{});return {items:Array.isArray(x?.items)?x.items.filter(p=>p&&typeof p.id==='string'&&typeof p.name==='string'):[],activeId:x?.activeId||null}}
function write(data){if(!setItem(KEY,data))throw new Error('No se pudo guardar. Revisa el espacio y los permisos del navegador.');}
export function listProfiles(){return database().items}
export function activeProfile(){const db=database();return db.items.find(p=>p.id===db.activeId)||null}
export function saveProfile(input,id=null){
 const name=String(input.name||'').trim();if(name.length<2||name.length>40)throw new Error('El nombre debe tener entre 2 y 40 caracteres.');
 if(!CITIES.some(c=>c.id===input.city))throw new Error('Selecciona una localidad válida.');
 const sports=[...new Set(input.sports||[])];if(sports.length>3||sports.some(s=>!SPORTS.includes(s)))throw new Error('Elige hasta 3 deportes del catálogo.');
 const db=database();if(id&&!db.items.some(p=>p.id===id))throw new Error('El perfil ya no existe.');
 if(!id&&db.items.length>=10)throw new Error('Puedes guardar hasta 10 perfiles de prueba.');
 const old=db.items.find(p=>p.id===id);
 const profile={id:id||`p-${Date.now()}-${Math.random().toString(36).slice(2,10)}`,name,city:input.city,sports,sportsUnified:true,createdAt:old?.createdAt||new Date().toISOString()};
 db.items=id?db.items.map(p=>p.id===id?profile:p):[...db.items,profile];db.activeId=profile.id;write(db);return profile;
}
export function selectProfile(id){const db=database();if(id!==null&&!db.items.some(p=>p.id===id))throw new Error('Ese perfil no existe.');db.activeId=id;write(db);return activeProfile()}
export function deleteProfile(id){const db=database();if(!db.items.some(p=>p.id===id))return;db.items=db.items.filter(p=>p.id!==id);if(db.activeId===id)db.activeId=null;write(db);PERSONAL_KEYS.forEach(k=>removeItem(`profile.${id}.${k}`));}

// Single selection shared by the public profile and the technical profile.
// For older profiles, keep their chosen interests, or recover technical interests if empty.
export function profileSports(){
 const p=activeProfile(),legacy=getItem(p?`profile.${p.id}.athleteProfile`:'athleteProfile',{});
 const selected=p&&(p.sportsUnified||p.sports?.length)?p.sports:legacy.sports;
 return Array.isArray(selected)?[...new Set(selected)].filter(s=>SPORTS.includes(s)).slice(0,3):[];
}
export function updateProfileSports(sports){const p=activeProfile();if(p)saveProfile({...p,sports},p.id)}
