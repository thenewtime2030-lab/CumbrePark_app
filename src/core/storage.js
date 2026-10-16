const PREFIX='cumbrepark.web.v1.';
export function getItem(key,fallback=null){try{const v=localStorage.getItem(PREFIX+key);return v===null?fallback:JSON.parse(v)}catch{return fallback}}
export function setItem(key,value){try{localStorage.setItem(PREFIX+key,JSON.stringify(value));return true}catch{return false}}
export function removeItem(key){try{localStorage.removeItem(PREFIX+key)}catch{}}
export function clearAll(){try{Object.keys(localStorage).filter(k=>k.startsWith(PREFIX)).forEach(k=>localStorage.removeItem(k))}catch{}}
