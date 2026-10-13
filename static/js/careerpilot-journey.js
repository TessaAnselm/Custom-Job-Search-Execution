/* Shared, privacy-light progress guide for the Profile and Jobs pages. */
(() => {
  const STATE_KEY = 'careerPilotJourneyState';
  const stages = [
    {
      title: 'Connect Akamai AI',
      image: '/static/monsters/monster-wave.png',
      message: 'First, test the Akamai vLLM connection. The check sends a tiny test prompt, not your resume.',
    },
    {
      title: 'Load your resume',
      image: '/static/monsters/monster-follow.png',
      message: 'Upload a PDF or text resume. Qwen can extract profile details; if it is unavailable, you can fill them in yourself.',
    },
    {
      title: 'Review your profile',
      image: '/static/monsters/monster-talk.png',
      message: 'Check the extracted facts, fix anything wrong, and confirm the profile before asking CareerPilot to use it.',
    },
    {
      title: 'Find and score jobs',
      image: '/static/monsters/monster-knock.png',
      message: 'The Collector gathers postings. The Scorekeeper ranks them against your profile. Save your verified profile to start a search.',
    },
    {
      title: 'Prepare a draft',
      image: '/static/monsters/monster-celebrate.png',
      message: 'Run CareerPilot. AWS Strands coordinates the tools and Qwen prepares match explanations and a truthful resume/cover-note draft.',
    },
    {
      title: 'You review and send',
      image: '/static/monsters/monster-celebrate.png',
      message: 'Review the draft, then use the employer’s own application page if you choose to apply. CareerPilot never sends it for you.',
    },
  ];

  function readState() {
    try { return JSON.parse(sessionStorage.getItem(STATE_KEY) || '{}'); }
    catch { return {}; }
  }

  function writeState(patch) {
    const next = { ...readState(), ...patch };
    try { sessionStorage.setItem(STATE_KEY, JSON.stringify(next)); } catch { /* Continue without persistence. */ }
    renderAll();
    return next;
  }

  function derive(root) {
    const state = readState();
    const complete = [
      Boolean(state.vllmConnected),
      state.resumeUploaded ?? (root.dataset.hasResume === 'true'),
      state.profileVerified ?? (root.dataset.profileVerified === 'true'),
      state.matchesReady ?? (root.dataset.hasMatches === 'true'),
      Boolean(state.draftReady),
    ];
    const current = complete.findIndex(done => !done);
    return { complete, current: current < 0 ? stages.length - 1 : current };
  }

  // Each fresh page load re-renders data-has-resume / data-profile-verified /
  // data-has-matches straight from the server (profile.yaml / job state) — that is
  // always the current truth at load time. sessionStorage only needs to track what
  // happens *after* that, within this page view (an upload or edit resetting
  // verification, a save confirming it) before the next reload refreshes it again.
  // Without this sync, a "false" cached from an earlier visit in this tab would
  // shadow a true value the server has had the whole time (the bug this fixes), via
  // the `??` fallback above only triggering on null/undefined, never on `false`.
  function syncFromServer() {
    const root = document.querySelector('.careerpilot-journey');
    if (!root) return;
    writeState({
      resumeUploaded: root.dataset.hasResume === 'true',
      profileVerified: root.dataset.profileVerified === 'true',
      matchesReady: root.dataset.hasMatches === 'true',
    });
  }

  function render(root) {
    const { complete, current } = derive(root);
    root.dataset.currentStep = String(current);
    root.querySelectorAll('.careerpilot-journey-step').forEach((item, index) => {
      const done = index < complete.length && complete[index];
      item.dataset.state = done ? 'done' : index === current ? 'current' : 'upcoming';
      if (index === current) item.setAttribute('aria-current', 'step');
      else item.removeAttribute('aria-current');
    });
    const stage = stages[current];
    const title = root.querySelector('.careerpilot-journey-title');
    const message = root.querySelector('.careerpilot-journey-message');
    const image = root.querySelector('.careerpilot-journey-monster');
    if (title && !root.dataset.customStatus) title.textContent = `Step ${current + 1} of ${stages.length} · ${stage.title}`;
    if (message && !root.dataset.customStatus) message.textContent = stage.message;
    if (image && !root.dataset.customStatus) image.src = stage.image;
    const action = root.querySelector('.careerpilot-journey-action');
    if (action) {
      const profilePage = root.dataset.page === 'profile';
      const profileLabels = ['Test Akamai connection', 'Choose resume file', 'Review and confirm profile', 'Run job search', 'Open CareerPilot', 'Review jobs'];
      const jobsLabels = ['Set up Akamai and profile', 'Upload or update resume', 'Review profile', 'Run job search', 'Run CareerPilot', 'Review application draft'];
      action.textContent = (profilePage ? profileLabels : jobsLabels)[current];
    }
  }

  function renderAll() {
    document.querySelectorAll('.careerpilot-journey').forEach(render);
  }

  function setStatus(message, mood = 'talk') {
    document.querySelectorAll('.careerpilot-journey').forEach(root => {
      root.dataset.customStatus = 'true';
      const title = root.querySelector('.careerpilot-journey-title');
      const text = root.querySelector('.careerpilot-journey-message');
      const image = root.querySelector('.careerpilot-journey-monster');
      if (title) title.textContent = 'CareerPilot guide';
      if (text) text.textContent = message;
      if (image) image.src = `/static/monsters/monster-${mood}.png`;
    });
  }

  function clearStatus() {
    document.querySelectorAll('.careerpilot-journey').forEach(root => { delete root.dataset.customStatus; });
    renderAll();
  }

  window.CareerPilotJourney = {
    getState: readState,
    setState: writeState,
    setStatus,
    clearStatus,
    render: renderAll,
  };

  // syncFromServer() already calls writeState(), which renders — no separate
  // renderAll() call needed here.
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', syncFromServer);
  else syncFromServer();
})();
