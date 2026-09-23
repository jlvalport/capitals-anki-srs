/**
 * Aplicación Web Capitales del Mundo - Repetición Espaciada Anki (SRS)
 * Manejo de estado del cliente, consumo de REST API y transiciones 3D sin spoilers.
 */

// Estado global de la aplicación
const state = {
  token: localStorage.getItem('capitals_auth_token') || null,
  user: JSON.parse(localStorage.getItem('capitals_user') || 'null'),
  theme: localStorage.getItem('capitals_theme') || 'system',
  currentTab: 'anki',
  dueCards: [],
  currentCardIndex: 0,
  dueCount: 0,
  newCount: 0,
  learnedCount: 0,
  sessionTotal: 0,
  isCardFlipped: false,
  isTransitioning: false,
  cardStartTime: null,
  countdownInterval: null,
  quizQuestion: null,
  quizStreak: 0,
  allCountries: [],
  authMode: 'login' // 'login' | 'register'
};

// ============================================================================
// INICIALIZACIÓN Y MANEJO DE AUTENTICACIÓN
// ============================================================================

document.addEventListener('DOMContentLoaded', async () => {
  // Inicializar sistema de temas (Sistema, Claro, Oscuro)
  initTheme();

  // Inicializar iconos de Lucide
  if (window.lucide) {
    lucide.createIcons();
  }

  // Verificar si hay token o iniciar sesión automática de invitado para persistir en BD
  await ensureAuthenticated();
  updateAuthUI();

  // Cargar datos iniciales según la pestaña
  await loadDueCards();
  await loadStats();

  // Registrar atajos de teclado globales
  setupKeyboardShortcuts();
});

async function apiFetch(url, options = {}) {
  options.headers = options.headers || {};
  if (state.token) {
    options.headers['Authorization'] = `Bearer ${state.token}`;
  }
  if (options.body && typeof options.body === 'object') {
    options.headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(options.body);
  }

  const response = await fetch(url, options);
  if (response.status === 401) {
    // Token expirado o inválido
    console.warn("Sesión expirada. Creando nueva sesión...");
    localStorage.removeItem('capitals_auth_token');
    localStorage.removeItem('capitals_user');
    state.token = null;
    state.user = null;
    updateAuthUI();
  }
  return response;
}

// ============================================================================
// GESTIÓN DE TEMAS (SISTEMA, CLARO, OSCURO)
// ============================================================================

function initTheme() {
  applyTheme(state.theme, false);

  // Escuchar cambios de preferencia del sistema en vivo si el modo es 'system'
  const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
  mediaQuery.addEventListener('change', () => {
    if (state.theme === 'system') {
      applyTheme('system', false);
    }
  });

  // Cerrar menú desplegable al hacer clic fuera del contenedor
  document.addEventListener('click', (e) => {
    const container = document.getElementById('theme-menu-container');
    const dropdown = document.getElementById('theme-dropdown');
    if (container && dropdown && !container.contains(e.target)) {
      dropdown.classList.add('hidden');
    }
  });
}

function toggleThemeMenu(event) {
  if (event) event.stopPropagation();
  const dropdown = document.getElementById('theme-dropdown');
  if (dropdown) {
    dropdown.classList.toggle('hidden');
  }
}

function setTheme(theme) {
  state.theme = theme;
  localStorage.setItem('capitals_theme', theme);
  applyTheme(theme, true);
  const dropdown = document.getElementById('theme-dropdown');
  if (dropdown) dropdown.classList.add('hidden');
}

function applyTheme(theme, updateUI = true) {
  const isDark = theme === 'dark' || (theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);

  // Alternar clases en <html>
  document.documentElement.classList.toggle('dark', isDark);
  document.documentElement.classList.toggle('light', !isDark);
  document.documentElement.style.colorScheme = isDark ? 'dark' : 'light';

  // Actualizar icono y texto del botón en la barra superior
  const iconElem = document.getElementById('theme-current-icon');
  const textElem = document.getElementById('theme-current-text');

  if (iconElem && textElem) {
    if (theme === 'system') {
      iconElem.setAttribute('data-lucide', 'monitor');
      textElem.textContent = 'Auto';
    } else if (theme === 'light') {
      iconElem.setAttribute('data-lucide', 'sun');
      textElem.textContent = 'Claro';
    } else {
      iconElem.setAttribute('data-lucide', 'moon');
      textElem.textContent = 'Oscuro';
    }
  }

  // Actualizar indicadores de selección en el menú
  ['system', 'light', 'dark'].forEach(t => {
    const opt = document.getElementById(`theme-opt-${t}`);
    if (opt) {
      const check = opt.querySelector('.theme-check');
      if (check) {
        if (t === theme) {
          check.classList.remove('hidden');
          opt.classList.add('bg-indigo-50/60', 'dark:bg-indigo-950/40', 'text-indigo-600', 'dark:text-indigo-400');
        } else {
          check.classList.add('hidden');
          opt.classList.remove('bg-indigo-50/60', 'dark:bg-indigo-950/40', 'text-indigo-600', 'dark:text-indigo-400');
        }
      }
    }
  });

  if (window.lucide) {
    lucide.createIcons();
  }
}

async function ensureAuthenticated() {
  if (state.token) {
    try {
      const res = await apiFetch('/api/auth/me');
      if (res.ok) {
        const data = await res.json();
        state.user = data.user;
        localStorage.setItem('capitals_user', JSON.stringify(state.user));
        return;
      }
    } catch (e) {
      console.error("Error verificando sesión:", e);
    }
  }

  // Si no hay sesión, crear un usuario anónimo/invitado en la base de datos
  // para que TODO su progreso quede guardado en SQLite sin perderse
  try {
    const guestId = Math.random().toString(36).substring(2, 9);
    const guestUsername = `Estudiante_${guestId}`;
    const guestEmail = `estudiante_${guestId}@anki.local`;
    const guestPassword = `pwd_${guestId}_${Date.now()}`;

    const res = await fetch('/api/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        username: guestUsername,
        email: guestEmail,
        password: guestPassword
      })
    });

    if (res.ok) {
      const data = await res.json();
      state.token = data.token;
      state.user = data.user;
      localStorage.setItem('capitals_auth_token', state.token);
      localStorage.setItem('capitals_user', JSON.stringify(state.user));
    }
  } catch (e) {
    console.error("Error creando sesión anónima en BD:", e);
  }
}

function updateAuthUI() {
  const userPill = document.getElementById('user-pill');
  const loginBtn = document.getElementById('login-open-btn');
  const displayName = document.getElementById('user-display-name');
  const guestBanner = document.getElementById('guest-banner');

  if (state.user && !state.user.username.startsWith('Estudiante_')) {
    userPill.classList.remove('hidden');
    userPill.classList.add('flex');
    loginBtn.classList.add('hidden');
    displayName.textContent = state.user.username;
    guestBanner.classList.add('hidden');
  } else {
    userPill.classList.add('hidden');
    loginBtn.classList.remove('hidden');
    guestBanner.classList.remove('hidden');
  }
}

function openAuthModal(mode = 'login') {
  setAuthMode(mode);
  document.getElementById('auth-modal').classList.remove('hidden');
  document.getElementById('auth-error').classList.add('hidden');
}

function closeAuthModal() {
  document.getElementById('auth-modal').classList.add('hidden');
}

function setAuthMode(mode) {
  state.authMode = mode;
  const tabLogin = document.getElementById('modal-tab-login');
  const tabRegister = document.getElementById('modal-tab-register');
  const emailGroup = document.getElementById('field-email-group');
  const emailInput = document.getElementById('auth-email');
  const submitBtn = document.getElementById('auth-submit-btn');
  const usernameLabel = document.querySelector('label[for="auth-username"]');
  const errorBox = document.getElementById('auth-error');

  if (errorBox) errorBox.classList.add('hidden');

  if (mode === 'login') {
    tabLogin.classList.add('text-indigo-400', 'border-b-2', 'border-indigo-500');
    tabLogin.classList.remove('text-slate-400');
    tabRegister.classList.remove('text-indigo-400', 'border-b-2', 'border-indigo-500');
    tabRegister.classList.add('text-slate-400');
    emailGroup.classList.add('hidden');
    if (usernameLabel) usernameLabel.textContent = 'Usuario o Correo';
    if (emailInput) emailInput.required = false;
    submitBtn.textContent = 'Iniciar Sesión';
  } else {
    tabRegister.classList.add('text-indigo-400', 'border-b-2', 'border-indigo-500');
    tabRegister.classList.remove('text-slate-400');
    tabLogin.classList.remove('text-indigo-400', 'border-b-2', 'border-indigo-500');
    tabLogin.classList.add('text-slate-400');
    emailGroup.classList.remove('hidden');
    if (usernameLabel) usernameLabel.textContent = 'Nombre de Usuario';
    if (emailInput) emailInput.required = true;
    submitBtn.textContent = 'Crear Cuenta';
  }
}

async function handleAuthSubmit(e) {
  e.preventDefault();
  const username = document.getElementById('auth-username').value.trim();
  const password = document.getElementById('auth-password').value;
  const email = document.getElementById('auth-email').value.trim();
  const errorBox = document.getElementById('auth-error');
  const errorText = document.getElementById('auth-error-text');

  errorBox.classList.add('hidden');

  // Validación previa en el cliente para mensajes instantáneos y claros
  if (state.authMode === 'register') {
    if (!username || username.length < 3) {
      errorText.textContent = 'El nombre de usuario debe tener al menos 3 caracteres.';
      errorBox.classList.remove('hidden');
      return;
    }
    if (!email) {
      errorText.textContent = 'Por favor, ingresa tu correo electrónico para registrarte.';
      errorBox.classList.remove('hidden');
      return;
    }
    if (!email.includes('@') || !email.includes('.')) {
      errorText.textContent = 'Por favor, introduce un correo electrónico válido (ejemplo: usuario@correo.com).';
      errorBox.classList.remove('hidden');
      return;
    }
    if (!password || password.length < 6) {
      errorText.textContent = 'La contraseña debe tener al menos 6 caracteres.';
      errorBox.classList.remove('hidden');
      return;
    }
  } else {
    if (!username) {
      errorText.textContent = 'Por favor, ingresa tu usuario o correo electrónico.';
      errorBox.classList.remove('hidden');
      return;
    }
    if (!password) {
      errorText.textContent = 'Por favor, ingresa tu contraseña.';
      errorBox.classList.remove('hidden');
      return;
    }
  }

  try {
    let endpoint = state.authMode === 'login' ? '/api/auth/login' : '/api/auth/register';
    let payload = state.authMode === 'login' 
      ? { login: username, password: password }
      : { username: username, email: email, password: password };

    const res = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const data = await res.json();
    if (!res.ok) {
      let errorMsg = 'Ocurrió un error en la autenticación.';
      if (typeof data.detail === 'string') {
        errorMsg = data.detail;
      } else if (Array.isArray(data.detail)) {
        // Manejar array de errores de FastAPI/Pydantic
        const fieldErrors = data.detail.map(err => {
          const field = err.loc ? err.loc[err.loc.length - 1] : '';
          if (field === 'email') return 'El correo electrónico es obligatorio y debe tener un formato válido.';
          if (field === 'username') return 'El nombre de usuario debe tener entre 3 y 30 caracteres.';
          if (field === 'password') return 'La contraseña debe tener al menos 6 caracteres.';
          return err.msg || 'Dato inválido';
        });
        errorMsg = fieldErrors.join(' ');
      } else if (data.detail && typeof data.detail === 'object') {
        errorMsg = JSON.stringify(data.detail);
      }
      throw new Error(errorMsg);
    }

    state.token = data.token;
    state.user = data.user;
    localStorage.setItem('capitals_auth_token', state.token);
    localStorage.setItem('capitals_user', JSON.stringify(state.user));

    closeAuthModal();
    updateAuthUI();

    // Recargar datos para el usuario logueado
    await loadDueCards();
    await loadStats();
    if (state.currentTab === 'explorer') await loadExplorerCountries();

  } catch (err) {
    errorText.textContent = err.message || 'Error desconocido al procesar la solicitud.';
    errorBox.classList.remove('hidden');
  }
}

async function logoutUser() {
  if (confirm('¿Deseas cerrar tu sesión actual?')) {
    try {
      await apiFetch('/api/auth/logout', { method: 'POST' });
    } catch(e) {}
    localStorage.removeItem('capitals_auth_token');
    localStorage.removeItem('capitals_user');
    state.token = null;
    state.user = null;
    await ensureAuthenticated();
    updateAuthUI();
    await loadDueCards();
    await loadStats();
  }
}

// ============================================================================
// NAVEGACIÓN ENTRE PESTAÑAS (SPA)
// ============================================================================

function switchTab(tabName) {
  state.currentTab = tabName;

  // Ocultar todas las secciones
  ['anki', 'quiz', 'explorer', 'stats'].forEach(t => {
    document.getElementById(`tab-${t}`).classList.add('hidden');
    
    // Estilos botones desktop
    const btn = document.getElementById(`nav-btn-${t}`);
    if (btn) {
      if (t === tabName) {
        btn.classList.add('bg-indigo-600', 'text-white', 'shadow');
        btn.classList.remove('text-slate-400');
      } else {
        btn.classList.remove('bg-indigo-600', 'text-white', 'shadow');
        btn.classList.add('text-slate-400');
      }
    }

    // Estilos botones mobile
    const mobBtn = document.getElementById(`mob-btn-${t}`);
    if (mobBtn) {
      if (t === tabName) {
        mobBtn.classList.add('text-indigo-400', 'font-medium');
        mobBtn.classList.remove('text-slate-400');
      } else {
        mobBtn.classList.remove('text-indigo-400', 'font-medium');
        mobBtn.classList.add('text-slate-400');
      }
    }
  });

  // Mostrar la sección activa
  document.getElementById(`tab-${tabName}`).classList.remove('hidden');

  // Acciones al cambiar de pestaña
  if (tabName === 'anki') {
    loadDueCards();
  } else if (tabName === 'quiz') {
    loadNextQuizQuestion();
  } else if (tabName === 'explorer') {
    loadExplorerCountries();
  } else if (tabName === 'stats') {
    loadStats();
  }

  if (window.lucide) lucide.createIcons();
}

// ============================================================================
// MODO ANKI SRS (REPETICIÓN ESPACIADA)
// ============================================================================

function pulseBadge(elemId) {
  const elem = document.getElementById(elemId);
  if (!elem) return;
  elem.classList.add('scale-110');
  setTimeout(() => {
    elem.classList.remove('scale-110');
  }, 350);
}

function updateSessionIndicators() {
  const dueElem = document.getElementById('counter-due');
  const newElem = document.getElementById('counter-new');
  const learnedElem = document.getElementById('counter-learned');
  const cardCurrentElem = document.getElementById('session-card-current');
  const cardTotalElem = document.getElementById('session-card-total');
  const pctElem = document.getElementById('session-progress-pct');
  const barElem = document.getElementById('session-progress-bar');

  if (dueElem) dueElem.textContent = state.dueCount;
  if (newElem) newElem.textContent = state.newCount;
  if (learnedElem) learnedElem.textContent = state.learnedCount;

  const total = state.dueCards ? state.dueCards.length : 0;
  const current = total > 0 ? Math.min(state.currentCardIndex + 1, total) : 0;
  if (cardCurrentElem) cardCurrentElem.textContent = current;
  if (cardTotalElem) cardTotalElem.textContent = total;

  const pct = total > 0 ? Math.round((state.currentCardIndex / total) * 100) : 100;
  if (pctElem) pctElem.textContent = `${pct}%`;
  if (barElem) barElem.style.width = `${pct}%`;
}

async function loadDueCards(requestedLimit = 15) {
  const continent = document.getElementById('anki-continent').value;
  try {
    const res = await apiFetch(`/api/srs/due?limit=${requestedLimit}&continent=${continent}`);
    if (!res.ok) throw new Error('Error al cargar tarjetas.');
    
    const data = await res.json();
    state.dueCards = data.cards;
    state.currentCardIndex = 0;
    state.dueCount = data.due_count;
    state.newCount = data.new_count;
    state.sessionTotal = data.cards.length;

    updateSessionIndicators();

    const tracker = document.getElementById('anki-session-tracker');
    if (state.dueCards.length > 0) {
      document.getElementById('anki-card-container').classList.remove('hidden');
      document.getElementById('anki-empty-state').classList.add('hidden');
      if (tracker) tracker.classList.remove('hidden');
      clearInterval(state.countdownInterval);
      renderCurrentCard();
    } else {
      document.getElementById('anki-card-container').classList.add('hidden');
      document.getElementById('anki-empty-state').classList.remove('hidden');
      if (tracker) tracker.classList.add('hidden');
      startCountdownTimer(data.next_due_time);
    }
  } catch (e) {
    console.error('Error cargando tarjetas SRS:', e);
  }
}

function renderCurrentCard() {
  const card = state.dueCards[state.currentCardIndex];
  if (!card) return;

  state.isCardFlipped = false;
  state.cardStartTime = Date.now();

  const flashcard = document.getElementById('flashcard');
  const actionsFront = document.getElementById('actions-front');
  const actionsBack = document.getElementById('actions-back');

  // Asegurar que la tarjeta comience siempre en el frente (boca arriba hacia el país)
  flashcard.classList.remove('is-flipped');
  actionsFront.classList.remove('hidden');
  actionsBack.classList.add('hidden');

  // Actualizar indicadores superiores en tiempo real
  updateSessionIndicators();

  // Inyectar datos en la cara frontal
  document.getElementById('card-flag').textContent = card.flag_emoji;
  document.getElementById('card-country').textContent = card.name_es;
  document.getElementById('card-country-en').textContent = card.name_en;
  document.getElementById('card-continent-badge').textContent = card.continent;

  const statusBadge = document.getElementById('card-status-badge');
  if (card.is_learned) {
    statusBadge.textContent = '🌟 Dominada';
    statusBadge.className = 'text-xs font-semibold px-2.5 py-0.5 rounded-full bg-emerald-50 dark:bg-emerald-500/20 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-500/30';
  } else if (card.state === 'learning' || (card.repetitions && card.repetitions > 0)) {
    statusBadge.textContent = '🔄 Repaso';
    statusBadge.className = 'text-xs font-semibold px-2.5 py-0.5 rounded-full bg-amber-50 dark:bg-amber-500/20 text-amber-700 dark:text-amber-300 border border-amber-200 dark:border-amber-500/30';
  } else {
    statusBadge.textContent = '✨ Nueva';
    statusBadge.className = 'text-xs font-semibold px-2.5 py-0.5 rounded-full bg-blue-50 dark:bg-blue-500/20 text-blue-700 dark:text-blue-300 border border-blue-200 dark:border-blue-500/30';
  }

  // Inyectar datos en la cara trasera
  document.getElementById('card-back-flag').textContent = card.flag_emoji;
  document.getElementById('card-back-country').textContent = card.name_es;
  document.getElementById('card-capital').textContent = card.capital_es;
  document.getElementById('card-capital-en').textContent = card.capital_en;
  document.getElementById('card-fun-fact').textContent = card.fun_fact || 'Dato histórico fascinante sobre esta nación.';

  // Inyectar etiquetas de tiempo dinámicas en los 4 botones
  if (card.buttons) {
    document.getElementById('btn-again-time').textContent = card.buttons.again.label;
    document.getElementById('btn-hard-time').textContent = card.buttons.hard.label;
    document.getElementById('btn-good-time').textContent = card.buttons.good.label;
    document.getElementById('btn-easy-time').textContent = card.buttons.easy.label;
  }
}

function toggleCardFlip() {
  if (state.isTransitioning) return;
  state.isCardFlipped = !state.isCardFlipped;

  const flashcard = document.getElementById('flashcard');
  const actionsFront = document.getElementById('actions-front');
  const actionsBack = document.getElementById('actions-back');

  if (state.isCardFlipped) {
    flashcard.classList.add('is-flipped');
    actionsFront.classList.add('hidden');
    actionsBack.classList.remove('hidden');
  } else {
    flashcard.classList.remove('is-flipped');
    actionsFront.classList.remove('hidden');
    actionsBack.classList.add('hidden');
  }
}

/**
 * Califica la tarjeta con el algoritmo Anki.
 * CRÍTICO: Garantiza que la siguiente carta jamás muestre su respuesta al voltear.
 */
async function rateCard(rating) {
  if (state.isTransitioning || !state.dueCards.length) return;
  state.isTransitioning = true;

  const currentCard = state.dueCards[state.currentCardIndex];
  const responseTimeMs = state.cardStartTime ? Date.now() - state.cardStartTime : 0;
  const flashcard = document.getElementById('flashcard');

  // Actualizar de forma inmediata los indicadores superiores para retroalimentación instantánea
  const isNewCard = !currentCard.repetitions || currentCard.repetitions === 0;
  if (isNewCard) {
    state.newCount = Math.max(0, state.newCount - 1);
  } else {
    state.dueCount = Math.max(0, state.dueCount - 1);
  }

  if (rating === 'again') {
    // Si se falla la tarjeta, se re-añade al final de la sesión para volver a practicarla
    const retryCard = {
      ...currentCard,
      repetitions: (currentCard.repetitions || 0) + 1,
      state: 'learning'
    };
    state.dueCards.push(retryCard);
    state.dueCount += 1;
    pulseBadge('badge-counter-due');
  } else if (rating === 'good' || rating === 'easy') {
    state.learnedCount += 1;
    pulseBadge('badge-counter-learned');
  } else if (rating === 'hard') {
    pulseBadge('badge-counter-due');
  }

  updateSessionIndicators();

  // 1. Iniciar animación de salida (la tarjeta actual se desvanece suavemente)
  flashcard.classList.remove('card-transition-active');
  flashcard.classList.add('card-transition-exit');

  // Enviar calificación al backend de forma asíncrona
  const reviewPromise = apiFetch('/api/srs/review', {
    method: 'POST',
    body: {
      country_id: currentCard.id,
      rating: rating,
      response_time_ms: responseTimeMs
    }
  });

  // 2. Esperar 220ms mientras la tarjeta se desvanece
  await new Promise(r => setTimeout(r, 220));

  // 3. MIENTRAS ESTÁ OCULTA:
  // - Remover inmediatamente la clase 'is-flipped' para que vuelva a su cara frontal
  // - Ocultar los botones de calificación y mostrar el botón de voltear
  flashcard.classList.remove('is-flipped');
  document.getElementById('actions-front').classList.remove('hidden');
  document.getElementById('actions-back').classList.add('hidden');
  state.isCardFlipped = false;

  // Avanzar al siguiente índice
  state.currentCardIndex++;

  if (state.currentCardIndex < state.dueCards.length) {
    // 4. Inyectar los datos de la NUEVA tarjeta mientras la tarjeta está frontal y oculta
    renderCurrentCard();

    // 5. Preparar la entrada: colocarla en posición inicial de entrada
    flashcard.classList.remove('card-transition-exit');
    flashcard.classList.add('card-transition-enter');

    // Forzar reflow del navegador para que la transición ocurra
    void flashcard.offsetHeight;

    // 6. Animar la entrada fluida de la nueva tarjeta (con la cara frontal hacia adelante)
    flashcard.classList.remove('card-transition-enter');
    flashcard.classList.add('card-transition-active');

    state.isTransitioning = false;
  } else {
    // Se completaron todas las tarjetas de la sesión actual
    await loadDueCards();
    await loadStats();
    state.isTransitioning = false;
  }

  // Sincronizar confirmación con base de datos
  try {
    const res = await reviewPromise;
    if (res.ok) {
      const data = await res.json();
      if (data.total_learned !== undefined) {
        state.learnedCount = data.total_learned;
        updateSessionIndicators();
      }
      if (data.is_learned) {
        triggerLearnedConfetti();
      }
    }
  } catch (e) {
    console.error('Error enviando calificación:', e);
  }
}

function startCountdownTimer(nextDueTimeStr) {
  const timerElem = document.getElementById('countdown-timer');
  clearInterval(state.countdownInterval);

  if (!nextDueTimeStr) {
    timerElem.textContent = 'No hay repasos pendientes';
    return;
  }

  function update() {
    const now = new Date().getTime();
    // Parse UTC string "YYYY-MM-DD HH:MM:SS"
    const target = new Date(nextDueTimeStr.replace(' ', 'T') + 'Z').getTime();
    const diff = target - now;

    if (diff <= 0) {
      timerElem.textContent = '¡Listo para repasar!';
      clearInterval(state.countdownInterval);
      loadDueCards();
      return;
    }

    const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
    const seconds = Math.floor((diff % (1000 * 60)) / 1000);
    const hours = Math.floor(diff / (1000 * 60 * 60));

    if (hours > 0) {
      timerElem.textContent = `${hours}h ${minutes}m ${seconds}s`;
    } else {
      timerElem.textContent = `${minutes}m ${seconds}s`;
    }
  }

  update();
  state.countdownInterval = setInterval(update, 1000);
}

function triggerLearnedConfetti() {
  // Efecto visual sutil de felicitación
  const card = document.getElementById('card-continent-badge');
  if (card) {
    card.classList.add('pulse-badge');
    setTimeout(() => card.classList.remove('pulse-badge'), 2000);
  }
}

// ============================================================================
// ATAJOS DE TECLADO
// ============================================================================

function setupKeyboardShortcuts() {
  document.addEventListener('keydown', (e) => {
    // Evitar capturar si el usuario está escribiendo en un input
    if (['INPUT', 'SELECT', 'TEXTAREA'].includes(e.target.tagName)) return;

    if (state.currentTab === 'anki') {
      if (e.code === 'Space' || e.key === 'Enter') {
        e.preventDefault();
        toggleCardFlip();
      } else if (state.isCardFlipped) {
        if (e.key === '1') {
          e.preventDefault();
          rateCard('again');
        } else if (e.key === '2') {
          e.preventDefault();
          rateCard('hard');
        } else if (e.key === '3') {
          e.preventDefault();
          rateCard('good');
        } else if (e.key === '4') {
          e.preventDefault();
          rateCard('easy');
        }
      }
    }
  });
}

// ============================================================================
// MODO QUIZ (OPCIÓN MÚLTIPLE)
// ============================================================================

async function loadNextQuizQuestion() {
  const nextBtn = document.getElementById('quiz-next-btn');
  nextBtn.classList.add('hidden');

  try {
    const res = await apiFetch('/api/quiz/question');
    if (!res.ok) throw new Error('Error al cargar pregunta de quiz.');

    state.quizQuestion = await res.json();
    const target = state.quizQuestion.target_country;

    document.getElementById('quiz-flag').textContent = target.flag;
    document.getElementById('quiz-country').textContent = target.name;

    const container = document.getElementById('quiz-options-container');
    container.innerHTML = '';

    state.quizQuestion.options.forEach((opt, idx) => {
      const btn = document.createElement('button');
      btn.className = 'p-4 rounded-2xl bg-white dark:bg-slate-950 hover:bg-slate-50 dark:hover:bg-slate-800 border border-slate-200 dark:border-slate-800 text-left font-semibold text-slate-800 dark:text-slate-200 transition flex items-center justify-between group shadow-sm';
      btn.innerHTML = `
        <span class="flex items-center gap-3">
          <span class="w-7 h-7 rounded-lg bg-slate-100 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-400 group-hover:text-indigo-600 dark:group-hover:text-indigo-300 text-xs font-bold flex items-center justify-center">${String.fromCharCode(65 + idx)}</span>
          <span>${opt.capital}</span>
        </span>
        <span class="quiz-feedback-icon"></span>
      `;
      btn.onclick = () => selectQuizOption(btn, opt.is_correct);
      container.appendChild(btn);
    });

  } catch (e) {
    console.error('Error cargando quiz:', e);
  }
}

function selectQuizOption(selectedBtn, isCorrect) {
  const container = document.getElementById('quiz-options-container');
  const buttons = container.querySelectorAll('button');

  // Desactivar todos los botones para evitar múltiples clics
  buttons.forEach(btn => btn.disabled = true);

  if (isCorrect) {
    selectedBtn.classList.remove('bg-white', 'dark:bg-slate-950', 'border-slate-200', 'dark:border-slate-800');
    selectedBtn.classList.add('bg-emerald-50', 'dark:bg-emerald-950/60', 'border-emerald-500', 'text-emerald-700', 'dark:text-emerald-200');
    selectedBtn.querySelector('.quiz-feedback-icon').innerHTML = '✅';
    state.quizStreak++;
  } else {
    selectedBtn.classList.remove('bg-white', 'dark:bg-slate-950', 'border-slate-200', 'dark:border-slate-800');
    selectedBtn.classList.add('bg-rose-50', 'dark:bg-rose-950/60', 'border-rose-500', 'text-rose-700', 'dark:text-rose-200');
    selectedBtn.querySelector('.quiz-feedback-icon').innerHTML = '❌';
    state.quizStreak = 0;

    // Resaltar la respuesta correcta
    state.quizQuestion.options.forEach((opt, idx) => {
      if (opt.is_correct) {
        buttons[idx].classList.remove('bg-white', 'dark:bg-slate-950', 'border-slate-200', 'dark:border-slate-800');
        buttons[idx].classList.add('bg-emerald-50/80', 'dark:bg-emerald-950/40', 'border-emerald-500/50', 'text-emerald-700', 'dark:text-emerald-300');
      }
    });
  }

  document.getElementById('quiz-streak').textContent = state.quizStreak;
  document.getElementById('quiz-next-btn').classList.remove('hidden');
}

// ============================================================================
// EXPLORADOR DE PAÍSES
// ============================================================================

async function loadExplorerCountries() {
  try {
    const res = await apiFetch('/api/countries');
    if (!res.ok) throw new Error('Error al cargar catálogo de países.');

    const data = await res.json();
    state.allCountries = data.countries;
    filterExplorer();
  } catch (e) {
    console.error('Error cargando países:', e);
  }
}

function filterExplorer() {
  const searchTerm = (document.getElementById('explorer-search').value || '').toLowerCase().trim();
  const continent = document.getElementById('explorer-continent').value;
  const status = document.getElementById('explorer-status').value;

  const filtered = state.allCountries.filter(c => {
    // Filtro texto
    const matchesText = !searchTerm || 
      c.name_es.toLowerCase().includes(searchTerm) || 
      c.capital_es.toLowerCase().includes(searchTerm) ||
      c.name_en.toLowerCase().includes(searchTerm);

    // Filtro continente
    const matchesContinent = continent === 'todos' || c.continent === continent;

    // Filtro estado
    let matchesStatus = true;
    if (status === 'learned') matchesStatus = c.is_learned === 1;
    else if (status === 'learning') matchesStatus = c.state === 'learning' && !c.is_learned;
    else if (status === 'new') matchesStatus = c.state === 'new' && !c.is_learned;

    return matchesText && matchesContinent && matchesStatus;
  });

  document.getElementById('explorer-count').textContent = filtered.length;
  renderExplorerGrid(filtered);
}

function renderExplorerGrid(countries) {
  const grid = document.getElementById('explorer-grid');
  grid.innerHTML = '';

  if (!countries.length) {
    grid.innerHTML = `
      <div class="col-span-full text-center py-12 text-slate-500 text-sm">
        No se encontraron países que coincidan con la búsqueda.
      </div>
    `;
    return;
  }

  countries.forEach(c => {
    const card = document.createElement('div');
    card.className = 'bg-white dark:bg-slate-900/60 p-4 rounded-2xl border border-slate-200 dark:border-slate-800/80 hover:border-slate-300 dark:hover:border-slate-700 shadow-sm transition flex flex-col justify-between';

    let badgeHtml = '';
    if (c.is_learned) {
      badgeHtml = '<span class="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-50 dark:bg-emerald-500/20 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-500/30">🌟 Dominado</span>';
    } else if (c.state === 'learning') {
      badgeHtml = '<span class="text-[10px] font-bold px-2 py-0.5 rounded-full bg-amber-50 dark:bg-amber-500/20 text-amber-700 dark:text-amber-300 border border-amber-200 dark:border-amber-500/30">🔄 En Repaso</span>';
    } else {
      badgeHtml = '<span class="text-[10px] font-bold px-2 py-0.5 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 border border-slate-200 dark:border-slate-700">⏳ Por Aprender</span>';
    }

    card.innerHTML = `
      <div>
        <div class="flex items-center justify-between mb-2">
          <span class="text-xs text-slate-500 dark:text-slate-400 font-medium">${c.continent}</span>
          ${badgeHtml}
        </div>
        <div class="flex items-center gap-3 my-2">
          <span class="text-3xl">${c.flag_emoji}</span>
          <div>
            <h4 class="font-bold text-slate-900 dark:text-white text-base leading-tight">${c.name_es}</h4>
            <p class="text-xs text-slate-500 dark:text-slate-400">${c.name_en}</p>
          </div>
        </div>
        <div class="mt-3 pt-2 border-t border-slate-100 dark:border-slate-800/60 flex items-center justify-between text-xs">
          <span class="text-slate-500 dark:text-slate-400">Capital:</span>
          <span class="font-black text-emerald-600 dark:text-emerald-300 text-sm">${c.capital_es}</span>
        </div>
      </div>
      ${c.fun_fact ? `<p class="text-[11px] text-slate-600 dark:text-slate-400 italic mt-3 line-clamp-2">"${c.fun_fact}"</p>` : ''}
    `;
    grid.appendChild(card);
  });
}

// ============================================================================
// PANEL DE ESTADÍSTICAS
// ============================================================================

async function loadStats() {
  try {
    const res = await apiFetch('/api/srs/stats');
    if (!res.ok) return;

    const data = await res.json();

    document.getElementById('stats-total-countries').textContent = data.total_countries;
    document.getElementById('stats-learned').textContent = data.learned_count;
    document.getElementById('stats-learning').textContent = data.learning_count;
    document.getElementById('stats-reviews').textContent = data.total_reviews;
    state.learnedCount = data.learned_count;
    updateSessionIndicators();

    // Barra de porcentaje
    document.getElementById('stats-percentage').textContent = `${data.mastery_percentage}%`;
    document.getElementById('stats-progress-bar').style.width = `${data.mastery_percentage}%`;

    // Desglose por continente
    const contList = document.getElementById('continent-stats-list');
    contList.innerHTML = '';

    data.continents.forEach(c => {
      const pct = c.total_continent > 0 ? Math.round((c.learned_continent / c.total_continent) * 100) : 0;
      const row = document.createElement('div');
      row.className = 'space-y-1';
      row.innerHTML = `
        <div class="flex justify-between text-xs">
          <span class="font-semibold text-slate-700 dark:text-slate-200">${c.continent}</span>
          <span class="text-slate-500 dark:text-slate-400">${c.learned_continent} / ${c.total_continent} (${pct}%)</span>
        </div>
        <div class="w-full bg-slate-100 dark:bg-slate-950 h-2 rounded-full overflow-hidden border border-slate-200 dark:border-slate-800">
          <div class="bg-indigo-500 h-full rounded-full transition-all duration-500" style="width: ${pct}%"></div>
        </div>
      `;
      contList.appendChild(row);
    });

  } catch (e) {
    console.error('Error cargando estadísticas:', e);
  }
}
