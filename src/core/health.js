import {getItem,setItem,removeItem} from './profile-storage.js';
import {localDateISO} from './utils.js';
import {parseCSV} from './csv.js';
export const HEALTH_KEY='restingHR.v1';
export function validDate(date){return /^\d{4}-\d{2}-\d{2}$/.test(date)&&localDateISO(new Date(date+'T12:00:00'))===date}
export function readRestingHR(){const x=getItem(HEALTH_KEY,[]);return Array.isArray(x)?x:[]}
export function parseRestingCSV(text){const rows=parseCSV(text);if(!rows.length||rows.length>1500)throw new Error('Carga entre 1 y 1500 días.');return rows.map((r,i)=>{const value=Number(r.resting_hr);if(!validDate(r.date)||r.date>localDateISO()||!Number.isFinite(value)||value<25||value>220)throw new Error(`Fila ${i+2}: usa date (AAAA-MM-DD) y resting_hr (25–220 lpm), sin fechas futuras.`);return {date:r.date,value,source:String(r.device||'Archivo de reloj').slice(0,50)}})}
export function saveRestingHR(rows){const days=new Map(readRestingHR().map(x=>[x.date,x]));for(const x of rows)days.set(x.date,x);if(!setItem(HEALTH_KEY,[...days.values()].sort((a,b)=>b.date.localeCompare(a.date)).slice(0,1500)))throw new Error('No se pudieron guardar las mediciones.');}
export function clearRestingHR(){removeItem(HEALTH_KEY)}
export function weeklyRestingHR(rows,today=localDateISO()){
 const end=new Date(today+'T12:00:00'),start=new Date(end);start.setDate(end.getDate()-6);const from=localDateISO(start),byDay=new Map();
 for(const x of rows){if(validDate(x.date)&&x.date>=from&&x.date<=today&&Number.isFinite(Number(x.value))){const values=byDay.get(x.date)||[];values.push(Number(x.value));byDay.set(x.date,values)}}
 const daily=[...byDay.values()].map(v=>v.reduce((s,x)=>s+x,0)/v.length);
 return {average:daily.length?Math.round(daily.reduce((s,x)=>s+x,0)/daily.length*10)/10:null,days:daily.length,from,to:today};
}
