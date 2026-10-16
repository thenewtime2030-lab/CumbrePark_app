/** Instalación y caché del shell. Las consultas de lugares y clima siguen siendo online. */
let installEvent = null;
let initialized = false;
function notify(text){
  document.querySelector('.pwa-help')?.remove();
  const el=document.createElement('div');
  el.className='toast pwa-help';el.setAttribute('role','status');el.textContent=text;
  document.body.append(el);
  el.addEventListener('click',()=>el.remove(),{once:true});
}
export function setupPWA(){
  if(initialized)return;
  initialized=true;
  if('serviceWorker' in navigator && (location.protocol==='https:' || location.hostname==='localhost')) {
    window.addEventListener('load',()=>navigator.serviceWorker.register('./service-worker.js',{scope:'./'})
      .catch(error=>console.warn('No fue posible habilitar caché PWA:',error.message)), {once:true});
  }
  window.addEventListener('beforeinstallprompt',event=>{
    event.preventDefault();installEvent=event;
    document.querySelector('#install-app')?.classList.add('pwa-ready');
  });
  window.addEventListener('appinstalled',()=>{
    installEvent=null;notify('CumbrePark se instaló en el dispositivo.');
  });
  document.querySelector('#install-app')?.addEventListener('click',async()=>{
    if(installEvent){
      const event=installEvent;installEvent=null;
      await event.prompt();
      return;
    }
    const ios=/iPad|iPhone|iPod/.test(navigator.userAgent);
    const isStandalone=matchMedia('(display-mode: standalone)').matches || navigator.standalone===true;
    notify(isStandalone?'CumbrePark ya está abierta como aplicación.':ios?
      'En iPhone o iPad: menú Compartir del navegador → Añadir a pantalla de inicio.':
      'Busca Instalar aplicación en el menú de Chrome o Edge; si no aparece, abre la web con HTTPS.');
  });
}
