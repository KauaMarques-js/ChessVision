"use strict";
// Only transmits the chess board to a local application. No external APIs.
chrome.runtime.onMessage.addListener((message, sender, respond) => {
  if (!message || message.type !== "chessvision-position" ||
      !sender.url || !/^https:\/\/(www\.)?chess\.com\//.test(sender.url)) return;
  const payload = message.payload;
  if (!payload || typeof payload.placement !== "string") return;
  fetch("http://127.0.0.1:8765/position", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(payload),
    cache: "no-store"
  }).then(r => respond({ok:r.ok})).catch(() => respond({ok:false}));
  return true;
});
