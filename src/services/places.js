import {fetchJSON,normalize,kmBetween,closestTypoScore} from '../core/utils.js';
import {getItem,setItem} from '../core/storage.js';
// Puntos de ejemplo aproximados: solo para explorar la interfaz cuando Overpass no responde.
// Nunca usar sus coordenadas como instrucciones de navegación.
const EXAMPLES=[
 {name:'Parque Metropolitano de Santiago',lat:-33.422,lon:-70.634,type:'Parque metropolitano'},
 {name:'Cerro Manquehue',lat:-33.356,lon:-70.584,type:'Cerro'},
 {name:'Parque Natural Aguas de Ramón',lat:-33.438,lon:-70.517,type:'Parque natural'},
 {name:'Parque Nacional Río Clarillo',lat:-33.738,lon:-70.487,type:'Parque nacional'},
 {name:'Monumento Natural El Morado',lat:-33.824,lon:-70.089,type:'Área protegida'},
 {name:'Parque Nacional La Campana',lat:-32.965,lon:-71.084,type:'Parque nacional'},
 {name:'Parque Nacional Conguillío',lat:-38.651,lon:-71.635,type:'Parque nacional'},
 {name:'Reserva Nacional Mocho-Choshuenco',lat:-39.933,lon:-72.03,type:'Reserva nacional'},
 {name:'Parque Nacional Torres del Paine',lat:-50.949,lon:-73.406,type:'Parque nacional'}
];
export function classify(tags={}){
 const name=String(tags.name||tags['name:es']||'').trim();if(!name)return null;
 const n=normalize(name);
 if(tags.natural==='peak')return 'Cerro / cumbre';
 if(tags.route==='hiking')return 'Ruta de trekking';
 if(tags.boundary==='national_park'||tags.protect_class==='2'||tags.leisure==='nature_reserve'||tags.boundary==='protected_area')return 'Área natural protegida';
 if(tags.tourism==='viewpoint'&&(n.includes('mirador')||n.includes('cerro')))return 'Mirador';
 if(tags.leisure==='park'&&(/parque nacional|parque metropolitano|parque natural|parque regional|parque aventura|parque ecologico/.test(n)))return 'Parque outdoor';
 return null;
}
export function parseElements(elements,city,radius){
 const seen=new Set(),out=[];
 for(const e of elements||[]){const tags=e.tags||{};const type=classify(tags);if(!type)continue;
 const lat=e.lat??e.center?.lat,lon=e.lon??e.center?.lon;
 if(!Number.isFinite(lat)||!Number.isFinite(lon))continue;
 const distance=kmBetween(city.lat,city.lon,lat,lon);if(distance>radius*1.1)continue;
 const name=String(tags.name||tags['name:es']||'').trim();const slug=normalize(name);if(seen.has(slug))continue;seen.add(slug);
 out.push({id:`osm-${e.type}-${e.id}`,name,type,lat,lon,distance,source:'OpenStreetMap',sample:false});
 }
 return out.sort((a,b)=>a.distance-b.distance).slice(0,35);
}
export function demoPlaces(city,radius){return EXAMPLES.map((p,i)=>({...p,id:`demo-${i}`,distance:kmBetween(city.lat,city.lon,p.lat,p.lon),source:'Demostración · ubicación aproximada',sample:true})).filter(p=>p.distance<=radius).sort((a,b)=>a.distance-b.distance)}
export async function discover(city,radius){
 const key=`places.${city.id}.${radius}`;const old=getItem(key);if(old&&Date.now()-old.savedAt<20*60*1000)return {places:old.places,live:true,cached:true};
 const r=Math.round(radius*1000);
 const query=`[out:json][timeout:18];(nwr(around:${r},${city.lat},${city.lon})["boundary"~"national_park|protected_area"]["name"];nwr(around:${r},${city.lat},${city.lon})["leisure"="nature_reserve"]["name"];nwr(around:${r},${city.lat},${city.lon})["natural"="peak"]["name"];relation(around:${r},${city.lat},${city.lon})["route"="hiking"]["name"];nwr(around:${r},${city.lat},${city.lon})["leisure"="park"]["name"~"Parque Nacional|Parque Metropolitano|Parque Natural|Parque Regional",i];);out center tags 120;`;
 const url=`https://overpass.kumi.systems/api/interpreter?data=${encodeURIComponent(query)}`;
 const json=await fetchJSON(url,{timeout:22000});const places=parseElements(json.elements,city,radius);
 setItem(key,{savedAt:Date.now(),places});return {places,live:true,cached:false};
}
export function filterPlaces(items,query){const q=normalize(query);if(!q)return items;return items.map(p=>({...p,match:Math.max(closestTypoScore(q,p.name),p.name.split(/\s+/).reduce((mx,w)=>Math.max(mx,closestTypoScore(q,w)),0))})).filter(p=>p.match>=.58).sort((a,b)=>b.match-a.match||a.distance-b.distance)}
