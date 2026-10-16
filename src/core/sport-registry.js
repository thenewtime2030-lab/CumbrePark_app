// Registro ampliable de disciplinas públicas. Deportes futuros no se publican aquí.
export const ENVIRONMENTS = [
 {id:'mountain',label:'Montaña',icon:'⛰',summary:'Trekking, montañismo, escalada y trail.',sports:['Trekking','Senderismo','Trail running','Montañismo','Escalada'],risk:'Variable según ruta y condiciones'},
 {id:'bike',label:'Bicicleta',icon:'🚴',summary:'MTB, ruta, gravel y cicloturismo.',sports:['MTB','Ciclismo de ruta','Gravel','Cicloturismo'],risk:'Variable según terreno y tráfico'},
 {id:'parks',label:'Parques y naturaleza',icon:'🌲',summary:'Caminatas, observación y exploración.',sports:['Caminatas','Observación de naturaleza','Fotografía de naturaleza'],risk:'Según sector y condiciones'},
 {id:'river',label:'Ríos',icon:'≈',summary:'Rafting, kayak de río y packraft.',sports:['Rafting','Kayak de río','Packraft'],risk:'Requiere evaluar caudal, experiencia y rescate'},
 {id:'snow',label:'Nieve',icon:'❄',summary:'Esquí, snowboard y travesías invernales.',sports:['Esquí','Snowboard','Raquetas de nieve','Esquí de travesía'],risk:'Atención a clima y avalanchas'},
 {id:'water',label:'Agua',icon:'〰',summary:'SUP, surf, kayak y natación.',sports:['SUP','Surf','Kayak de mar','Natación en aguas abiertas'],risk:'Atención a corriente, viento y temperatura'}
];
export const OUTDOOR_SPORTS=[...new Set(ENVIRONMENTS.flatMap(e=>e.sports))];
export function environmentFor(sport){return ENVIRONMENTS.find(e=>e.sports.includes(sport))||null}
// Modelo genérico válido para futuras disciplinas: no incluye equipos o deportes privados.
export function createActivityModel({title,sport,date,capacity=8,level='recreational'}={}){
 return {title:String(title||'').trim(),sport:String(sport||''),date:String(date||''),capacity:Number(capacity),level};
}
