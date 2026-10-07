(function () {
    'use strict';
    if (typeof i18n === 'undefined' && window.translations) {
        let language = 'ko';
        try { language = localStorage.getItem('i18n_language') || localStorage.getItem('selectedLanguage') || 'ko'; } catch (error) {}
        const dictionary = window.translations[language] || window.translations.ko;
        document.querySelectorAll('.mf-header [data-i18n],.mf-skip[data-i18n]').forEach(element => {
            const text = dictionary[element.dataset.i18n];
            if (text) element.textContent = text;
        });
    }
    // Progressive enhancement: preserve page handlers and existing preference keys.
    const dialogs = Array.from(document.querySelectorAll('[role="dialog"], .mobile-o2o-overlay, .kakao-link-overlay, .map-overlay, .modal-overlay, .pdf-overlay, .survey-overlay'));
    let active = null;
    let previousFocus = null;
    const visible = element => element.getClientRects().length && getComputedStyle(element).visibility !== 'hidden';
    const controls = dialog => Array.from(dialog.querySelectorAll('button,a[href],input,select,textarea,[tabindex="0"]')).filter(element => !element.disabled && visible(element));
    function syncDialogs() {
        const next = dialogs.find(visible) || null;
        if (next === active) return;
        const old = active;
        active = next;
        if (next) {
            previousFocus = document.activeElement;
            next.setAttribute('role', 'dialog'); next.setAttribute('aria-modal', 'true');
            if (!next.hasAttribute('aria-label') && !next.hasAttribute('aria-labelledby')) next.setAttribute('aria-label', 'MediFlow');
            next.setAttribute('tabindex', '-1');
            (controls(next)[0] || next).focus();
        } else if (old && previousFocus?.isConnected && visible(previousFocus)) {
            previousFocus.focus(); previousFocus = null;
        }
    }
    if (dialogs.length) {
        const observer = new MutationObserver(syncDialogs);
        dialogs.forEach(dialog => observer.observe(dialog, {attributes:true, attributeFilter:['class','style','hidden']}));
        document.addEventListener('keydown', event => {
            if (!active) return;
            if (event.key === 'Tab') {
                const items = controls(active);
                if (!items.length) {event.preventDefault(); active.focus(); return;}
                const first = items[0], last = items[items.length - 1];
                if (event.shiftKey && (document.activeElement === first || document.activeElement === active)) {event.preventDefault(); last.focus();}
                else if (!event.shiftKey && (document.activeElement === last || !active.contains(document.activeElement))) {event.preventDefault(); first.focus();}
            }
        });
        syncDialogs();
    }
    document.querySelectorAll('[data-mf-finish]').forEach(button => button.addEventListener('click', () => {
        if (!window.confirm('이번 검사를 종료하고 화면의 임시 정보를 지울까요? 저장된 이력은 유지됩니다.')) return;
        if (window.initializeMasterSession) window.initializeMasterSession();
        location.href = '/';
    }));
})();
