// Injected before the Angular app boots. The app AES-encrypts every request body
// and response ("edata"), but plaintext still passes through JSON.stringify
// (before encryption) and JSON.parse (after decryption). Recording both, plus
// the XHR URLs, gives readable API traffic without touching the obfuscated crypto.
(() => {
  // Playwright's binding serializes its args with JSON.stringify, so logging must
  // not re-enter the hooks or every log line would produce another one.
  let busy = false;
  const rawStringify = JSON.stringify;
  const send = (kind, data) => {
    if (busy || !window.__bhuLog) return;
    busy = true;
    try { window.__bhuLog(rawStringify({ t: Date.now(), kind, data })); } catch (e) {}
    busy = false;
  };
  const interesting = (s) => typeof s === 'string' && s.length > 2 && s.length < 5_000_000 &&
    (s[0] === '{' || s[0] === '[');

  const origParse = JSON.parse;
  JSON.parse = function (text, reviver) {
    const out = origParse.call(this, text, reviver);
    if (interesting(text) && !text.includes('"edata"')) send('parse', text);
    return out;
  };

  const origStringify = JSON.stringify;
  JSON.stringify = function (value, ...rest) {
    const out = origStringify.call(this, value, ...rest);
    if (interesting(out) && !out.includes('"edata"') && !out.includes('__bhuLog')) send('stringify', out);
    return out;
  };

  const origOpen = XMLHttpRequest.prototype.open;
  const origSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (method, url, ...rest) {
    this.__bhu = { method, url: String(url) };
    return origOpen.call(this, method, url, ...rest);
  };
  XMLHttpRequest.prototype.send = function (body) {
    const meta = this.__bhu || {};
    if (meta.url && meta.url.includes('PublicBhuApi')) {
      send('xhr', { ...meta, phase: 'send' });
      this.addEventListener('loadend', () => send('xhr', { ...meta, phase: 'done', status: this.status }));
    }
    return origSend.call(this, body);
  };
})();
