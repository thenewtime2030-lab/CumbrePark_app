import {monthlyTotals} from './activity.js';
export function activitySummary(items,month){
 const selected=items.filter(x=>String(x.date).slice(0,7)===month);
 const weeks=Array.from({length:5},(_,i)=>({label:`${i*7+1}–${Math.min(i*7+7,new Date(Number(month.slice(0,4)),Number(month.slice(5,7)),0).getDate())}`,count:0,minutes:0}));
 for(const x of selected){const i=Math.min(4,Math.floor((Number(x.date.slice(8,10))-1)/7));if(i>=0){weeks[i].count++;weeks[i].minutes+=Number(x.minutes)||0}}
 const sports=[...new Set(selected.map(x=>x.sport))].map(sport=>({sport,...monthlyTotals(selected.filter(x=>x.sport===sport),month)})).sort((a,b)=>b.minutes-a.minutes);
 return {...monthlyTotals(selected,month),activeDays:new Set(selected.map(x=>x.date)).size,weeks:weeks.filter((_,i)=>i*7+1<=new Date(Number(month.slice(0,4)),Number(month.slice(5,7)),0).getDate()),sports};
}
