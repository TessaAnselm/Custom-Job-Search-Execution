// ── Resume upload ─────────────────────────────────────────────────────────

const uploadZone   = document.getElementById('uploadZone');
const fileInput    = document.getElementById('resumeFile');
const uploadStatus = document.getElementById('uploadStatus');
const journey      = window.CareerPilotJourney;
const journeyRoot  = document.getElementById('careerPilotJourney');
const journeyAction = document.getElementById('careerPilotJourneyAction');
const connectionStatus = document.getElementById('vllmConnectionStatus');

uploadZone.addEventListener('dragover', e => { e.preventDefault(); uploadZone.classList.add('drag-over'); });
uploadZone.addEventListener('dragleave', () => uploadZone.classList.remove('drag-over'));
uploadZone.addEventListener('drop', e => {
  e.preventDefault();
  uploadZone.classList.remove('drag-over');
  if (e.dataTransfer.files[0]) handleFile(e.dataTransfer.files[0]);
});
fileInput.addEventListener('change', () => { if (fileInput.files[0]) handleFile(fileInput.files[0]); });

async function handleFile(file) {
  if (file.size > 5 * 1024 * 1024) { showToast('File too large (max 5MB)', true); return; }

  uploadStatus.className = 'upload-status';
  uploadStatus.textContent = 'Reading resume and extracting profile…';
  journey?.setStatus('I’m reading the resume and asking the configured AI to extract profile facts. This may take a moment.', 'talk');
  uploadZone.style.opacity = '0.5';
  uploadZone.style.pointerEvents = 'none';

  const fd = new FormData();
  fd.append('resume', file);

  try {
    const res  = await fetch('/api/upload-resume', { method: 'POST', body: fd });
    const data = await res.json();

    uploadZone.style.opacity = '';
    uploadZone.style.pointerEvents = '';

    if (data.ok) {
      const p = data.profile || data.extracted || {};
      document.querySelector('[name="profile_verified"]').checked = false;
      fillForm({
        name:                 p.name,
        experience_years:     p.experience_years,
        role_type:            p.role_type,
        target_titles:        p.target_titles,
        skills:               p.skills,
        location_preferred:   p.location?.preferred ?? p.location_preferred,
        location_hard_no:     p.location?.hard_no ?? p.location_hard_no,
        salary_minimum:       p.salary?.minimum ?? p.salary_minimum,
        salary_target:        p.salary?.target ?? p.salary_target,
        industries_preferred: p.industries?.preferred ?? p.industries_preferred,
        industries_avoid:     p.industries?.avoid ?? p.industries_avoid,
      });
      if (p.base_resume !== undefined && p.base_resume !== null) {
        document.getElementById('baseResumeText').value = p.base_resume;
      }
      journey?.setState({ resumeUploaded: true, profileVerified: false, matchesReady: false, draftReady: false });
      document.getElementById('profileForm').scrollIntoView({ behavior: 'smooth', block: 'start' });
      if (data.warning) {
        uploadStatus.textContent = data.warning;
        uploadStatus.classList.add('status-error');
        const partialExtraction = data.warning.includes('could not identify');
        journey?.setStatus(partialExtraction
          ? 'I read the resume, but could not identify every key detail. Fill in any missing fields, then verify the complete profile.'
          : 'The resume text is saved, but profile extraction did not run successfully. Check the message above, then review and fill in the profile fields yourself.', 'surprise');
        return;
      }
      uploadStatus.textContent = 'Resume read. Review every extracted fact, confirm the profile, then save to start matching.';
      uploadStatus.classList.add('status-ok');
      journey?.clearStatus();
    } else {
      uploadStatus.textContent = 'Failed: ' + (data.error || 'unknown error');
      uploadStatus.classList.add('status-error');
    }
  } catch (err) {
    uploadZone.style.opacity = '';
    uploadZone.style.pointerEvents = '';
    uploadStatus.textContent = 'Network error — try again.';
    uploadStatus.classList.add('status-error');
  }
}

function fillForm(d) {
  const set = (name, val) => {
    const el = document.querySelector(`[name="${name}"]`);
    if (!el || val === undefined || val === null) return;
    el.value = Array.isArray(val) ? val.join('\n') : val;
  };

  set('name',               d.name);
  set('experience_years',   d.experience_years);
  set('target_titles',      d.target_titles);
  set('skills',             d.skills);
  set('location_preferred', d.location_preferred);
  set('location_hard_no',   d.location_hard_no);
  set('industries_preferred', d.industries_preferred);
  set('industries_avoid',     d.industries_avoid);

  if (d.salary_minimum !== undefined && d.salary_minimum !== null) set('salary_minimum', d.salary_minimum);
  if (d.salary_target !== undefined && d.salary_target !== null) set('salary_target', d.salary_target);

  // role_type is a <select>
  if (d.role_type) {
    const sel = document.querySelector('[name="role_type"]');
    if (sel) sel.value = d.role_type;
  }
}

// ── Profile form save ─────────────────────────────────────────────────────

document.getElementById('profileForm').addEventListener('submit', async e => {
  e.preventDefault();
  const fd = new FormData(e.target);
  if (fd.get('profile_verified') !== 'on') {
    showSaveStatus('Review the profile and check the confirmation box before continuing to job matching.', true);
    journey?.setStatus('Please review the fields, correct anything inaccurate, and check the confirmation box. The AI must not treat guesses as your experience.', 'talk');
    document.querySelector('[name="profile_verified"]').focus();
    return;
  }

  const payload = {
    profile_verified: fd.get('profile_verified') === 'on',
    name:             fd.get('name'),
    experience_years: parseInt(fd.get('experience_years')) || 0,
    role_type:        fd.get('role_type'),
    target_titles:    lines(fd.get('target_titles')),
    skills:           lines(fd.get('skills')),
    location: {
      preferred: lines(fd.get('location_preferred')),
      hard_no:   lines(fd.get('location_hard_no')),
    },
    salary: {
      minimum: parseInt(fd.get('salary_minimum')) || 0,
      target:  parseInt(fd.get('salary_target'))  || 0,
    },
    industries: {
      preferred: lines(fd.get('industries_preferred')),
      avoid:     lines(fd.get('industries_avoid')),
    },
    scoring_weights: {
      title_match:    parseFloat(fd.get('w_title'))    || 0.30,
      skills_match:   parseFloat(fd.get('w_skills'))   || 0.25,
      salary_match:   parseFloat(fd.get('w_salary'))   || 0.20,
      location_match: parseFloat(fd.get('w_location')) || 0.15,
      industry_match: parseFloat(fd.get('w_industry')) || 0.10,
    },
    minimum_score: parseInt(fd.get('minimum_score')) || 65,
    base_resume:   fd.get('base_resume'),
  };

  showSaveStatus('Saving…');

  try {
    const res  = await fetch('/api/save-profile', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (data.ok) {
      journey?.setState({ profileVerified: true });
      await runSearchAndRedirect();
    } else {
      showSaveStatus('Error: ' + (data.error || 'unknown'), true);
    }
  } catch {
    showSaveStatus('Network error', true);
  }
});

document.getElementById('profileForm').addEventListener('input', e => {
  if (e.target.name === 'profile_verified') return;
  const verification = document.querySelector('[name="profile_verified"]');
  if (verification.checked) verification.checked = false;
  journey?.setState({ profileVerified: false, matchesReady: false, draftReady: false });
});

// ── Helpers ───────────────────────────────────────────────────────────────

function lines(str) {
  return (str || '').split('\n').map(s => s.trim()).filter(Boolean);
}

function showSaveStatus(msg, isError) {
  const el = document.getElementById('saveStatus');
  el.textContent = msg;
  el.className = 'save-status' + (isError ? ' status-error' : ' status-ok');
}

function showToast(msg, isError) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'toast' + (isError ? ' toast-error' : '');
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.classList.add('hidden'), 2500);
}

function showViewJobsBtn() {
  const btn = document.getElementById('viewJobsBtn');
  if (btn) btn.style.display = '';
}

async function runSearchAndRedirect() {
  const msg = 'Searching jobs — this takes 1–2 minutes…';
  showSaveStatus(msg);
  journey?.setStatus('Your verified profile is saved. The Collector is searching enabled job sources and the Scorekeeper is ranking the results. I’ll take you to Jobs when the search responds.', 'knock');
  // Also update the upload status area if visible
  if (uploadStatus && !uploadStatus.classList.contains('hidden')) {
    uploadStatus.textContent = msg;
  }

  const submitBtn = document.querySelector('#profileForm [type="submit"]');
  if (submitBtn) submitBtn.disabled = true;

  try {
    const r    = await fetch('/api/trigger-search', { method: 'POST' });
    const data = await r.json();
    if (data.ok) {
      if (data.mode === 'standalone') {
        journey?.setState({ matchesReady: true });
        showSaveStatus(`Search complete — ${data.count} jobs scored. Loading your matches…`);
      } else {
        journey?.setStatus('Your job search workflow has started. Check the Jobs page for its progress and results.', 'talk');
        showSaveStatus('Search started. Loading Jobs…');
      }
      window.location.href = '/';
    } else {
      const errMsg = 'Saved — search failed: ' + (data.error || 'unknown');
      showSaveStatus(errMsg, true);
      if (uploadStatus) uploadStatus.textContent = errMsg;
      showViewJobsBtn();
      if (submitBtn) submitBtn.disabled = false;
    }
  } catch {
    const errMsg = 'Saved — could not reach server for search.';
    showSaveStatus(errMsg, true);
    if (uploadStatus) uploadStatus.textContent = errMsg;
    showViewJobsBtn();
    if (submitBtn) submitBtn.disabled = false;
  }
}

async function testAkamaiConnection() {
  journeyAction.disabled = true;
  connectionStatus.textContent = 'Sending a small test prompt to the configured vLLM endpoint…';
  journey?.setStatus('I’m checking the model connection with a tiny test prompt. Your resume is not included.', 'talk');
  try {
    const response = await fetch('/api/vllm/check', { method: 'POST' });
    const result = await response.json();
    if (!response.ok || !result.ok) throw new Error(result.error || 'Connection check failed.');
    journey?.setState({ vllmConnected: true });
    connectionStatus.textContent = `Connected to ${result.model} · ${result.latency_ms} ms round trip.`;
    journey?.setStatus(`Great, ${result.model} answered the test prompt in ${result.latency_ms} ms. Next, upload your resume.`, 'celebrate');
    journeyAction.textContent = 'Choose resume file';
  } catch (error) {
    connectionStatus.textContent = error.message || 'Could not connect to Akamai vLLM.';
    journey?.setStatus('I couldn’t reach the model. Check AI_PROVIDER, VLLM_HOST, the API key if needed, and that your kubectl port-forward is still running. You can still fill out the profile manually.', 'surprise');
  } finally {
    journeyAction.disabled = false;
  }
}

journeyAction?.addEventListener('click', () => {
  const step = Number(journeyRoot?.dataset.currentStep || 0);
  if (step === 0) return testAkamaiConnection();
  if (step === 1) {
    document.getElementById('uploadZone').scrollIntoView({ behavior: 'smooth', block: 'center' });
    fileInput.click();
  } else if (step === 2) {
    document.getElementById('profileForm').scrollIntoView({ behavior: 'smooth', block: 'start' });
    document.querySelector('[name="profile_verified"]').focus({ preventScroll: true });
  } else if (step === 3) {
    if (document.querySelector('[name="profile_verified"]').checked) runSearchAndRedirect();
    else document.getElementById('profileForm').scrollIntoView({ behavior: 'smooth', block: 'start' });
  } else {
    window.location.href = '/';
  }
});
