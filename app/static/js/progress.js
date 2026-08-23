(() => {
  const card = document.querySelector('[data-progress-url]');
  if (!card) return;
  const status = document.querySelector('#progress-status');
  const error = document.querySelector('#progress-error');
  const title = document.querySelector('#progress-title');
  const progressBar = document.querySelector('#progress-bar');
  const progressNote = document.querySelector('#progress-note');
  const showFailure = (label) => {
    status.textContent = label;
    title.textContent = label;
    document.title = label + ' — Truth Hunter';
    progressBar.hidden = true;
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
    } catch (_) { showFailure('Investigation status unavailable'); return; }
    window.setTimeout(poll, 2000);
  };
  window.setTimeout(poll, 1200);
})();
