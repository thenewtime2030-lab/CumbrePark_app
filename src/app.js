import {state,setTheme} from './core/state.js';
import {ROUTE_NAMES} from './core/constants.js';
import {setupPWA} from './core/pwa.js';
import {renderHome,mountHome} from './pages/home.js';
import {renderExplore,mountExplore} from './pages/explore.js';
import {renderSports,mountSports} from './pages/sports.js';
import {renderCommunity} from './pages/community.js';
import {renderEvents,mountEvents} from './pages/events.js';
import {activeProfile} from './core/profiles.js';
import {renderSummary,mountSummary} from './pages/summary.js';
import {renderAccount,mountAccount} from './pages/account.js';
import {renderSettings,mountSettings} from './pages/settings.js';
import {renderOutdoor} from './pages/outdoor.js';
import {renderActivityLog,mountActivityLog} from './pages/activity-log.js';
import {renderRanking} from './pages/ranking.js';
import {renderRewards} from './pages/rewards.js';
import {renderSafeMeet,mountSafeMeet} from './pages/safemeet.js';
import {renderAcademy,mountAcademy} from './pages/academy.js';
import {renderAdventure} from './pages/adventure.js';
import {renderNature} from './pages/nature.js';
import {renderPlans} from './pages/plans.js';
export const ROUTES={home:[renderHome,mountHome],explore:[renderExplore,mountExplore],outdoor:[renderOutdoor,null],sports:[renderSports,mountSports],activity:[renderActivityLog,mountActivityLog],ranking:[renderRanking,null],rewards:[renderRewards,null],community:[renderCommunity,null],events:[renderEvents,mountEvents],safemeet:[renderSafeMeet,mountSafeMeet],nature:[renderNature,null],academy:[renderAcademy,mountAcademy],adventure:[renderAdventure,null],plans:[renderPlans,null],summary:[renderSummary,mountSummary],account:[renderAccount,mountAccount],settings:[renderSettings,mountSettings]};
function applyTheme(){document.documentElement.dataset.theme=state.theme;const b=document.querySelector('#theme-toggle');if(b){b.textContent=state.theme==='dark'?'☀ Claro':'☾ Oscuro';b.setAttribute('aria-label',state.theme==='dark'?'Activar modo claro':'Activar modo oscuro')}document.querySelector('meta[name="theme-color"]').content=state.theme==='dark'?'#071018':'#f3f8fa'}
function closeDrawer(){state.drawerOpen=false;document.querySelector('#drawer').classList.remove('is-open');document.querySelector('#drawer-backdrop').hidden=true;document.querySelector('#menu-toggle').setAttribute('aria-expanded','false')}
function openDrawer(){state.drawerOpen=true;document.querySelector('#drawer').classList.add('is-open');document.querySelector('#drawer-backdrop').hidden=false;document.querySelector('#menu-toggle').setAttribute('aria-expanded','true')}
export function navigate(route,{updateHash=true}={}){if(!Object.hasOwn(ROUTES,route))route='home';state.route=route;const profile=activeProfile();document.querySelector('#profile-access').textContent=profile?profile.name:'Ingresar';document.querySelector('#profile-access').title=profile?'Perfil de prueba: '+profile.name:'Crear o elegir un perfil de prueba';document.querySelector('#breadcrumb').textContent=ROUTE_NAMES[route];document.querySelectorAll('.nav-item').forEach(el=>{const active=el.dataset.route===route;el.classList.toggle('is-active',active);if(active)el.setAttribute('aria-current','page');else el.removeAttribute('aria-current')});const [render,mount]=ROUTES[route];document.querySelector('#app').innerHTML=render();closeDrawer();if(updateHash&&location.hash!==`#${route}`)history.replaceState(null,'',`#${route}`);window.scrollTo(0,0);mount?.()}
function start(){applyTheme();document.querySelector('#footer-year').textContent=String(new Date().getFullYear());document.addEventListener('click',e=>{const go=e.target.closest('[data-route], [data-go]');if(go&&!go.disabled){navigate(go.dataset.route||go.dataset.go)}});document.addEventListener('keydown',e=>{if(e.key==='Escape')closeDrawer()});document.querySelector('#menu-toggle').addEventListener('click',()=>state.drawerOpen?closeDrawer():openDrawer());document.querySelector('#drawer-backdrop').addEventListener('click',closeDrawer);document.querySelector('#theme-toggle').addEventListener('click',()=>{setTheme(state.theme==='dark'?'light':'dark');applyTheme()});window.addEventListener('hashchange',()=>navigate(location.hash.slice(1),{updateHash:false}));window.addEventListener('cumbre:theme',()=>{applyTheme();navigate(state.route)});window.addEventListener('cumbre:refresh',()=>navigate(state.route));window.addEventListener('cumbre:reset',()=>{state.theme='dark';state.cityId='santiago';applyTheme();navigate('settings')});navigate(location.hash.slice(1)||'home',{updateHash:false});setupPWA()}
start();
