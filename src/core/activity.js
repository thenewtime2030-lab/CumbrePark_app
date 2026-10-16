import {getItem,setItem} from './profile-storage.js';
import {OUTDOOR_SPORTS} from './sport-registry.js';
const KEY='activities.v2';
export function readActivities(){const data=getItem(KEY,[]);return Array.isArray(data)?data.filter(x=>x&&typeof x==='object'):[]}
export function validateActivity(input){
 const sport=String(input.sport||''),kind=String(input.kind||'').trim();
 if(!OUTDOOR_SPORTS.includes(sport))throw new Error('Selecciona un deporte del catálogo.');
 const date=String(input.date||'');if(!/^\d{4}-\d{2}-\d{2}$/.test(date)||!Number.isFinite(Date.parse(date+'T12:00:00')))throw new Error('Selecciona una fecha válida.');
 if(new Date(date+'T12:00:00').getTime()>Date.now()+86400000)throw new Error('No puedes registrar actividades futuras.');
 const distance=Number(input.distance||0),elevation=Number(input.elevation||0),minutes=Number(input.minutes||0);
 if(!Number.isFinite(distance)||distance<0||distance>1000||!Number.isFinite(elevation)||elevation<0||elevation>12000||!Number.isFinite(minutes)||minutes<1||minutes>10080)throw new Error('Revisa distancia, desnivel y minutos.');
 return {id:`a-${Date.now()}-${Math.random().toString(36).slice(2,8)}`,sport,date,distance,elevation,minutes,kind:kind.slice(0,60),verified:false};
}
export function saveActivity(data){const all=readActivities();const entry=validateActivity(data);const success=setItem(KEY,[entry,...all].slice(0,300));return success?entry:null}
export function removeActivity(id){return setItem(KEY,readActivities().filter(x=>x.id!==id))}
export function monthKey(date){return String(date||'').slice(0,7)}
export function monthlyTotals(items,month){const m=(items||[]).filter(x=>monthKey(x.date)===month);return {count:m.length,distance:Math.round(m.reduce((sum,x)=>sum+(Number(x.distance)||0),0)*10)/10,elevation:Math.round(m.reduce((sum,x)=>sum+(Number(x.elevation)||0),0)),minutes:Math.round(m.reduce((sum,x)=>sum+(Number(x.minutes)||0),0))}}
export function sportsMonthly(items,month){return OUTDOOR_SPORTS.map(sport=>({sport,...monthlyTotals(items.filter(x=>x.sport===sport),month)})).filter(x=>x.count).sort((a,b)=>b.distance-a.distance)}
