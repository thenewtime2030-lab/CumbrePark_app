export function parseCSV(text){
 const s=String(text).replace(/^\uFEFF/,'').trim();if(!s)throw new Error('El archivo está vacío.');
 const first=s.split(/\r?\n/)[0],separator=first.includes(';')?';':',';const rows=[];let row=[],value='',quoted=false;
 for(let i=0;i<s.length;i++){const c=s[i];if(c==='"'){if(quoted&&s[i+1]==='"'){value+='"';i++}else quoted=!quoted}else if(!quoted&&(c===separator||c==='\n')){row.push(value.trim());value='';if(c==='\n'){if(row.some(Boolean))rows.push(row);row=[]}}else if(c!=='\r')value+=c}
 if(quoted)throw new Error('El CSV contiene comillas sin cerrar.');row.push(value.trim());if(row.some(Boolean))rows.push(row);
 const headers=rows.shift().map(h=>h.toLowerCase());if(new Set(headers).size!==headers.length)throw new Error('El CSV tiene columnas repetidas.');
 return rows.map((r,i)=>{if(r.length!==headers.length)throw new Error(`Revisa las columnas en la fila ${i+2}.`);return Object.fromEntries(headers.map((h,j)=>[h,r[j]]))});
}
