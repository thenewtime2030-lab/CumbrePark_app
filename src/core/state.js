import {CITIES} from './constants.js';
import {getItem,setItem} from './storage.js';
export const state = { route:'home', cityId:getItem('city','santiago'), theme:getItem('theme','dark'), drawerOpen:false };
export function getCity(){return CITIES.find(x=>x.id===state.cityId)||CITIES[0]}
export function setCity(id){if(!CITIES.some(x=>x.id===id))return;state.cityId=id;setItem('city',id)}
export function setTheme(t){state.theme=t==='light'?'light':'dark';setItem('theme',state.theme)}
