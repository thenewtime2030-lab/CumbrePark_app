import {parseCSV} from '../core/csv.js';
import {validateActivity} from '../core/activity.js';
import {localDateISO} from '../core/utils.js';
const named=(root,name)=>[...root.getElementsByTagNameNS('*',name)];
const text=(root,name)=>named(root,name)[0]?.textContent.trim()||'';
const value=(root,name)=>{const v=text(root,name);return v===''?null:Number(v)};
function fingerprint(s){let h=2166136261;for(let i=0;i<s.length;i++){h^=s.charCodeAt(i);h=Math.imul(h,16777619)}return (h>>>0).toString(16)}
function kmBetween(a,b){const rad=Math.PI/180;const dlat=(b.lat-a.lat)*rad,dlon=(b.lon-a.lon)*rad;const h=Math.sin(dlat/2)**2+Math.cos(a.lat*rad)*Math.cos(b.lat*rad)*Math.sin(dlon/2)**2;return 6371*2*Math.atan2(Math.sqrt(h),Math.sqrt(Math.max(0,1-h)))}
function numeric(x){return x!==null&&x!==''&&Number.isFinite(Number(x))}
export function parseActivityFile(content,filename,sport,Parser=globalThis.DOMParser){
 if(content.length>8*1024*1024)throw new Error('El archivo supera los 8 MB.');let records=[];
 if(/\.csv$/i.test(filename)){records=parseCSV(content).map(r=>({sport:r.sport||sport,date:r.date,minutes:r.minutes,distance:r.distance||0,elevation:r.elevation||0,heartRate:r.heart_rate||null,kind:r.notes||'Importado de archivo'}));}
 else if(/\.(tcx|gpx)$/i.test(filename)){
  if(!Parser)throw new Error('Este navegador no permite leer el archivo.');if(/<!DOCTYPE|<!ENTITY/i.test(content))throw new Error('El archivo XML contiene declaraciones no admitidas.');
  const doc=new Parser().parseFromString(content,'application/xml');if(named(doc,'parsererror').length)throw new Error('El XML está dañado.');
  if(/\.tcx$/i.test(filename)){
   const activities=named(doc,'Activity');if(activities.length!==1)throw new Error('Exporta una sola actividad por archivo TCX.');const a=activities[0],laps=named(a,'Lap');
   const seconds=laps.reduce((sum,l)=>sum+(value(l,'TotalTimeSeconds')||0),0),meters=laps.reduce((sum,l)=>sum+(value(l,'DistanceMeters')||0),0);
   const weighted=laps.map(l=>({hr:value(named(l,'AverageHeartRateBpm')[0]||doc.createElement('none'),'Value'),seconds:value(l,'TotalTimeSeconds')||0})).filter(x=>numeric(x.hr)&&x.seconds>0);
   const completeHR=weighted.length===laps.length&&seconds>0;
   const date=new Date(text(a,'Id'));if(!Number.isFinite(date.getTime()))throw new Error('El TCX no incluye una fecha válida.');
   const altitudes=named(a,'Trackpoint').map(p=>value(p,'AltitudeMeters'));let gain=0;for(let i=1;i<altitudes.length;i++)if(numeric(altitudes[i])&&numeric(altitudes[i-1]))gain+=Math.max(0,altitudes[i]-altitudes[i-1]);
   records=[{sport,date:localDateISO(date),minutes:Math.round(seconds/60*100)/100,distance:Math.round(meters/100)/10,elevation:Math.round(gain),heartRate:completeHR?Math.round(weighted.reduce((sum,x)=>sum+x.hr*x.seconds,0)/seconds):null,kind:'Importado de TCX'}];
  }else{
   if(named(doc,'trk').length!==1)throw new Error('Exporta una sola actividad con track GPX.');let distance=0,gain=0;const times=[];
   for(const segment of named(doc,'trkseg')){let previous=null;for(const p of named(segment,'trkpt')){const lat=Number(p.getAttribute('lat')),lon=Number(p.getAttribute('lon'));if(!p.hasAttribute('lat')||!p.hasAttribute('lon')||!Number.isFinite(lat)||!Number.isFinite(lon)||Math.abs(lat)>90||Math.abs(lon)>180)throw new Error('El GPX tiene coordenadas inválidas.');const point={lat,lon,alt:value(p,'ele')};if(previous){distance+=kmBetween(previous,point);if(numeric(point.alt)&&numeric(previous.alt))gain+=Math.max(0,point.alt-previous.alt)}previous=point;const t=Date.parse(text(p,'time'));if(Number.isFinite(t))times.push(t)}}
   if(times.length<2)throw new Error('Este GPX no tiene tiempos suficientes. Importa un TCX o registra la sesión manualmente.');
   const first=times.reduce((a,b)=>Math.min(a,b),Infinity),last=times.reduce((a,b)=>Math.max(a,b),-Infinity);records=[{sport,date:localDateISO(new Date(first)),minutes:Math.round((last-first)/600)/100,distance:Math.round(distance*10)/10,elevation:Math.round(gain),kind:'GPX: duración total; incluye pausas. Desnivel calculado sin filtro.'}];
  }
 }else throw new Error('Usa un archivo TCX, GPX o CSV. Los archivos FIT y ZIP aún no se importan.');
 if(!records.length||records.length>100)throw new Error('Importa entre 1 y 100 actividades a la vez.');const id=fingerprint(content);
 return records.map((r,i)=>({...validateActivity({...r,source:'watch',importId:`${id}-${i}`}),source:'watch',importId:`${id}-${i}`}));
}
