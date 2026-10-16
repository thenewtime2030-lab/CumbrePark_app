import {getItem as read,setItem as write,removeItem as remove} from './storage.js';
import {activeProfile} from './profiles.js';
function key(k){const p=activeProfile();return p?`profile.${p.id}.${k}`:k}
export function getItem(k,fallback=null){return read(key(k),fallback)}
export function setItem(k,value){return write(key(k),value)}
export function removeItem(k){return remove(key(k))}
