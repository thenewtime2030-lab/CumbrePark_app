export const MIN_COMMUNITY_PEOPLE=6;
// Clasificación didáctica: no sustituye a una revisión competente de la ruta.
export function safemeetAssessment({risk='low',confirmed=0,verified=false,professional=false,adultsOnly=true}={}){
 const r=['low','medium','high'].includes(risk)?risk:'high',c=Math.max(0,Math.floor(Number(confirmed)||0));
 const issues=[];
 if(!adultsOnly)issues.push('La maqueta solo contempla eventos públicos para mayores de edad.');
 if(!verified)issues.push('Debe verificarse al organizador.');
 if(c<MIN_COMMUNITY_PEOPLE)issues.push(`Faltan ${MIN_COMMUNITY_PEOPLE-c} participantes para el mínimo de referencia.`);
 if(r==='medium'&&!professional)issues.push('Se requiere revisar experiencia y habilitación del organizador.');
 if(r==='high')issues.push('La actividad de alto riesgo exige validación profesional y revisión adicional; no se habilita automáticamente.');
 return {risk:r,confirmed:c,issues,eligible:issues.length===0&&r==='low'};
}
