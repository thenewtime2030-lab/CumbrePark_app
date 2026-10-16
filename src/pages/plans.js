import {heading} from '../components/ui.js';
export function renderPlans(){return `${heading('MODELO DE SUSCRIPCIONES','Una plataforma, distintas necesidades','Los planes se muestran como propuesta comercial. No existen cobros, precios finales ni compras activas.','Sin pagos activos')}
<div class="pricing-grid">${[
 ['Free','Para explorar y conectar','Acceso gratuito','Comunidad, clubes, juntas, búsqueda, progreso básico, SafeMeet esencial, CumbreRank y acceso a cursos matriculados.','Disponible como visión del producto'],
 ['Premium','Para vivir el deporte a fondo','Precio por definir','Analítica avanzada, estadísticas históricas, personalización y herramientas individuales adicionales. Nunca ventaja en rankings.','En diseño'],
 ['VIP · Adventure Pro','Para operar excursiones','Precio profesional','Gestión de clientes, guías, salidas, reportes y herramientas de turismo aventura.','En diseño'],
 ['VIP · Academy','Para profesores y formadores','Precio profesional','Crear cursos, evaluaciones, materiales, registro de salidas y gestión de estudiantes.','En diseño'],
 ['Institutional','Para universidades y organizaciones','Contrato por definir','Múltiples docentes, alumnos sin pago obligatorio, gestión académica, permisos y reportes institucionales.','En diseño']
 ].map((x,i)=>`<article class="card price-card ${i===0?'price-highlight':''}"><div class="eyebrow">${x[0]}</div><h2>${x[1]}</h2><span class="plan-price">${x[2]}</span><p class="tiny">${x[3]}</p><span class="chip">${x[4]}</span></article>`).join('')}</div><section class="notice" style="margin-top:18px"><strong>Regla permanente:</strong> ninguna universidad puede exigir a sus alumnos pagar Premium para cursar, entregar tareas, aprobar evaluaciones o acceder a información esencial de seguridad.</section>`}
