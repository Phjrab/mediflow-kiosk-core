(function () {
    const status = document.getElementById('mf-capabilities');
    if (!status || !window.ScreeningFlow) return;
    let capability = null;
    function render() {
        status.removeAttribute('data-i18n');
        if (!capability) { status.textContent = i18n.getTranslation('mf_cap_error'); return; }
        const ready = (capability.modalities || []).filter(item => item.model_status === 'ready').map(item => item.label);
        const missing = (capability.modalities || []).filter(item => item.model_status !== 'ready').map(item => item.label);
        status.textContent = i18n.getTranslation('mf_cap_status', {ready: ready.join(' · ') || '—', missing: missing.join(' · ') || '—'});
    }
    ScreeningFlow.getConfig().then(config => {capability = config; render();}).catch(render);
    if (typeof i18n !== 'undefined') i18n.onLanguageChange(render);
})();
