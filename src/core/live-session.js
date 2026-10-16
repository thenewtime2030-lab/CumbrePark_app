import {getItem,setItem,removeItem} from './profile-storage.js';
import {OUTDOOR_SPORTS} from './sport-registry.js';
import {localDateISO} from './utils.js';
const KEY='liveSession.v1';
export function readSession(){return getItem(KEY,null)}
function write(s){if(!setItem(KEY,s))throw new Error('No se pudo guardar el cronómetro.');return s}
export function startSession(sport,now=Date.now()){if(!OUTDOOR_SPORTS.includes(sport))throw new Error('Selecciona un deporte.');if(readSession())throw new Error('Ya tienes una sesión pendiente.');return write({sport,date:localDateISO(new Date(now)),elapsed:0,runningSince:now})}
export function elapsedSession(s=readSession(),now=Date.now()){return s?Math.max(0,s.elapsed+(s.runningSince!==null?now-s.runningSince:0)):0}
export function pauseSession(now=Date.now()){const s=readSession();if(!s)return null;return write({...s,elapsed:elapsedSession(s,now),runningSince:null})}
export function resumeSession(now=Date.now()){const s=readSession();if(!s)return null;return s.runningSince===null?write({...s,runningSince:now}):s}
export function discardSession(){removeItem(KEY)}
export function sessionActivity(){const s=readSession();if(!s)return null;return {sport:s.sport,date:s.date,minutes:Math.round(elapsedSession(s)/600)/100,source:'live'}}
