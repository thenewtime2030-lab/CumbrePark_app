import {fetchJSON,dateInZone} from '../core/utils.js';
import {getItem,setItem} from '../core/storage.js';
// MET Norway: CC BY 4.0, con atribución. Navegadores envían Origin (no User-Agent personalizable).
// Un proxy identificable y con caché será necesario antes de escalar a producción.
const TTL=35*60*1000;
const describe={clearsky_day:'Despejado',clearsky_night:'Despejado',fair_day:'Mayormente despejado',partlycloudy_day:'Parcialmente nublado',cloudy:'Nublado',fog:'Niebla',rain:'Lluvia',lightrain:'Lluvia ligera',heavyrain:'Lluvia intensa',snow:'Nieve',lightsnow:'Nieve ligera',rainshowers_day:'Chubascos',sleet:'Aguanieve'};
function condition(code){const s=String(code||'');return describe[s]|| (s.includes('rain')?'Lluvia':s.includes('snow')?'Nieve':s.includes('cloud')?'Nubosidad':'Pronóstico disponible')}
export function simplifyForecast(json,city,now=new Date()){
 const series=json?.properties?.timeseries;if(!Array.isArray(series)||!series.length)throw new Error('Sin pronóstico válido');
 const nowTs=now.getTime();const cur=series.find(x=>Date.parse(x.time)>=nowTs)||series[0];
 const instant=cur.data?.instant?.details||{};
 const localDate=dateInZone(now,city.tz);
 const vals=series.filter(x=>dateInZone(new Date(x.time),city.tz)===localDate).map(x=>x.data?.instant?.details?.air_temperature).filter(Number.isFinite);
 const symbol=cur.data?.next_1_hours?.summary?.symbol_code||cur.data?.next_6_hours?.summary?.symbol_code||'';
 return {temp:Number.isFinite(instant.air_temperature)?Math.round(instant.air_temperature):null,wind:Number.isFinite(instant.wind_speed)?Math.round(instant.wind_speed*3.6):null,min:vals.length?Math.round(Math.min(...vals)):null,max:vals.length?Math.round(Math.max(...vals)):null,condition:condition(symbol),at:now.toISOString(),source:'MET Norway'};
}
export async function getWeather(city){
 const key=`weather.${city.id}`,saved=getItem(key);if(saved&&Date.now()-saved.savedAt<TTL)return saved.data;
 const url=`https://api.met.no/weatherapi/locationforecast/2.0/compact?lat=${city.lat.toFixed(4)}&lon=${city.lon.toFixed(4)}`;
 const raw=await fetchJSON(url,{timeout:11000});const data=simplifyForecast(raw,city);setItem(key,{savedAt:Date.now(),data});return data;
}
