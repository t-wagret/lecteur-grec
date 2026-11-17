// Fait les appels au lecteur local (127.0.0.1) à la place de la page, que le navigateur
// empêcherait de parler à l'ordinateur ; renvoie l'audio en base64.
const SERVEUR = "http://127.0.0.1:8766";

chrome.runtime.onMessage.addListener((msg, _expediteur, repondre) => {
  (async () => {
    try {
      if (msg.type === "etat") {
        const r = await fetch(`${SERVEUR}/etat`);
        repondre({ ok: true, ...(await r.json()) });
      } else if (msg.type === "lire") {
        const r = await fetch(`${SERVEUR}/lire`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ texte: msg.texte, voix: msg.voix }),
        });
        if (!r.ok) throw new Error(`erreur ${r.status}`);
        const octets = new Uint8Array(await r.arrayBuffer());
        let binaire = "";
        for (let i = 0; i < octets.length; i += 0x8000) {
          binaire += String.fromCharCode(...octets.subarray(i, i + 0x8000));
        }
        repondre({ ok: true, audio: btoa(binaire) });
      }
    } catch (err) {
      repondre({ ok: false, erreur: String(err) });
    }
  })();
  return true; // réponse asynchrone
});
