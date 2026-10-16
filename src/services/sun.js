// Aproximación NOAA: salida/puesta astronómicas para una ciudad (sin GPS ni llamadas a APIs).
import {dateInZone,formatHour} from '../core/utils.js';
export function sunTimes(lat,lon,tz,date=new Date()){
  const [y,m,d]=dateInZone(date,tz).split('-').map(Number);
  const jan1=Date.UTC(y,0,1);const N=Math.floor((Date.UTC(y,m-1,d)-jan1)/86400000)+1;
  const gamma=2*Math.PI/365*(N-1);
  const eq=229.18*(0.000075+0.001868*Math.cos(gamma)-0.032077*Math.sin(gamma)-0.014615*Math.cos(2*gamma)-0.040849*Math.sin(2*gamma));
  const dec=0.006918-0.399912*Math.cos(gamma)+0.070257*Math.sin(gamma)-0.006758*Math.cos(2*gamma)+0.000907*Math.sin(2*gamma)-0.002697*Math.cos(3*gamma)+0.00148*Math.sin(3*gamma);
  const phi=lat*Math.PI/180;
  const z=(Math.cos(90.833*Math.PI/180)/(Math.cos(phi)*Math.cos(dec)))-Math.tan(phi)*Math.tan(dec);
  if(z>1||z< -1)return {sunrise:'—',sunset:'—',polar:true};
  const h=Math.acos(z)*180/Math.PI;
  const rise=720-4*(lon+h)-eq,set=720-4*(lon-h)-eq;
  const base=Date.UTC(y,m-1,d);
  return {sunrise:formatHour(new Date(base+rise*60000),tz),sunset:formatHour(new Date(base+set*60000),tz),polar:false};
}
