import {getItem,setItem} from './storage.js';
import {createActivityModel,OUTDOOR_SPORTS} from './sport-registry.js';
import {localDateISO} from './utils.js';
const KEY='event.drafts';
export function listEventDrafts(){const list=getItem(KEY,[]);return Array.isArray(list)?list:[]}
export function saveEventDraft(fields){const x=createActivityModel(fields);if(x.title.length<5||x.title.length>80)throw new Error('El título debe tener de 5 a 80 caracteres.');if(!OUTDOOR_SPORTS.includes(x.sport))throw new Error('Deporte no válido.');if(!/^\d{4}-\d{2}-\d{2}$/.test(x.date)||!Number.isFinite(Date.parse(x.date+'T12:00:00'))||x.date<localDateISO())throw new Error('Indica una fecha futura.');if(!Number.isInteger(x.capacity)||x.capacity<6||x.capacity>100)throw new Error('El cupo debe estar entre 6 y 100.');const draft={...x,id:`e-${Date.now()}`,published:false,confirmed:0};return setItem(KEY,[draft,...listEventDrafts()].slice(0,25))?draft:null}
export function deleteEventDraft(id){return setItem(KEY,listEventDrafts().filter(x=>x.id!==id))}
