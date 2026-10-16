import {getItem,setItem} from './profile-storage.js';
const KEY='academy.drafts';
export function listCourseDrafts(){const x=getItem(KEY,[]);return Array.isArray(x)?x:[]}
export function createCourseDraft({name,area,modules}={}){
 const title=String(name||'').trim();if(title.length<4||title.length>85)throw new Error('El nombre debe tener entre 4 y 85 caracteres.');
 const mod=Math.round(Number(modules));if(!Number.isInteger(mod)||mod<1||mod>30)throw new Error('Los módulos deben ser entre 1 y 30.');
 const draft={id:`c-${Date.now()}`,title,area:String(area||'Outdoor').slice(0,65),modules:mod,status:'Borrador local'};
 return setItem(KEY,[draft,...listCourseDrafts()].slice(0,30))?draft:null;
}
export function deleteCourseDraft(id){return setItem(KEY,listCourseDrafts().filter(x=>x.id!==id))}
