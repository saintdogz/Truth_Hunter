(() => {
  const card = document.querySelector('[data-progress-url]');
  if (!card) return;
  const status = document.querySelector('#progress-status');
  const error = document.querySelector('#progress-error');
  const title = document.querySelector('#progress-title');
  const progressBar = document.querySelector('#progress-bar');
  const progressFill = progressBar.querySelector('span');
  const progressNote = document.querySelector('#progress-note');
  const steps = Array.from(document.querySelectorAll('[data-stage-index]'));
  const updateStages = (stageIndex, stageTotal, label) => {
    progressBar.setAttribute('aria-valuemax', String(stageTotal));
    progressBar.setAttribute('aria-valuenow', String(stageIndex));
    progressBar.setAttribute('aria-label', label);
    progressFill.style.width = `${Math.round(stageIndex / stageTotal * 100)}%`;
    steps.forEach((step) => {
      const index = Number(step.dataset.stageIndex);
      step.classList.toggle('completed', index < stageIndex);
      step.classList.toggle('current', index === stageIndex);
      step.classList.toggle('pending', index > stageIndex);
      if (index === stageIndex) step.setAttribute('aria-current', 'step');
      else step.removeAttribute('aria-current');
    });
  };
  const showFailure = (label) => {
    status.textContent = label;
    title.textContent = label;
    document.title = label + ' — Truth Hunter';
    card.classList.add('progress-has-failed');
    progressNote.hidden = true;
    error.hidden = false;
  };
  const poll = async () => {
    try {
      const response = await fetch(card.dataset.progressUrl, { headers: { Accept: 'application/json' } });
      if (!response.ok) throw new Error('status request failed');
      const data = await response.json();
      status.textContent = data.label;
      if (data.result_url) { window.location.assign(data.result_url); return; }
      if (data.status.endsWith('FAILED')) { showFailure(data.label); return; }
      updateStages(data.stage_index, data.stage_total, data.label);
    } catch (_) { showFailure(card.dataset.unavailableLabel); return; }
    window.setTimeout(poll, 2000);
  };
  window.setTimeout(poll, 1200);
})();
