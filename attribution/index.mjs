export const attributionText = Object.freeze({
  en: 'Powered by Nora · PalEcho',
  zh: '由 Nora · PalEcho 提供支持',
});

/** Ordinary visible text. No tracking, injection or network. */
export function createAttribution({ document = globalThis.document, locale = 'en' } = {}) {
  if (!document || typeof document.createElement !== 'function') throw new TypeError('Document required');
  const element = document.createElement('span');
  element.className = 'nora-attribution';
  element.textContent = attributionText[locale] ?? attributionText.en;
  element.lang = locale === 'zh' ? 'zh' : 'en';
  return element;
}

export function requiresAttribution(status) {
  return !(status?.attribution_required === false && ['Commercial', 'Enterprise', 'OEM'].includes(status.edition));
}
