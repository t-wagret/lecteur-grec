// Ajoute aux pages de texte de The Greek Library une petite barre de lecture et, dans la marge,
// un bouton ▶ par paragraphe et un trait qui suit le passage lu. Le texte est envoyé morceau par
// morceau au lecteur local (serveur_lecture.py) ; le morceau suivant est préparé pendant que le
// précédent est lu.
(() => {
  const texteGrec = document.querySelector("#greek-text");
  if (!texteGrec) return;

  const VOIX_MODERNES = ["spyros", "kostas", "athina", "katerina"];
  let session = 0; // change à chaque nouvelle lecture ou arrêt : l'ancienne boucle s'arrête
  let audio = null;
  let finir = null; // termine le morceau en cours (pour reculer ou avancer)
  let saut = null; // prochain morceau demandé par ⏮ ou ⏭
  let enCours = null; // morceau en train d'être lu
  const enMemoire = new Map();
  const MIN_MORCEAU = 100; // caractères : en dessous, la phrase suivante est jointe
  const memoire = {
    lire: (cle, defaut) => {
      try {
        return localStorage.getItem(cle) ?? defaut;
      } catch {
        return defaut;
      }
    },
    ecrire: (cle, valeur) => {
      try {
        localStorage.setItem(cle, valeur);
      } catch {}
    },
  };

  // --- barre de lecture -------------------------------------------------------------------
  const barre = document.createElement("div");
  barre.className = "tgl-lecteur";
  barre.innerHTML = `
    <button type="button" class="tgl-lecteur__allumer" title="Allumer le lecteur grec">🔊</button>
    <div class="tgl-lecteur__commandes">
      <button type="button" data-action="reculer" title="Revenir au début de la phrase (deux fois : phrase précédente)" disabled>⏮</button>
      <button type="button" data-action="lire" class="tgl-lecteur__lire" title="Lire à partir du passage affiché">▶ Lire</button>
      <button type="button" data-action="avancer" title="Phrase suivante" disabled>⏭</button>
      <button type="button" data-action="arreter" title="Arrêter" disabled>⏹</button>
      <select title="Voix">
        <option value="attique">attique restitué</option>
        <optgroup label="grec moderne">${VOIX_MODERNES.map((v) => `<option>${v}</option>`).join("")}</optgroup>
      </select>
      <button type="button" data-action="eteindre" title="Éteindre le lecteur">⏻</button>
      <span class="tgl-lecteur__etat" role="status"></span>
    </div>`;
  document.body.append(barre);
  const bouton = (action) => barre.querySelector(`[data-action="${action}"]`);
  const choixVoix = barre.querySelector("select");
  const etat = barre.querySelector(".tgl-lecteur__etat");
  choixVoix.value = memoire.lire("tgl-lecteur-voix", "attique");
  choixVoix.addEventListener("change", () => memoire.ecrire("tgl-lecteur-voix", choixVoix.value));

  function allumer(oui) {
    document.documentElement.classList.toggle("tgl-eteint", !oui);
    memoire.ecrire("tgl-lecteur-allume", oui ? "1" : "0");
    if (!oui) arreter();
  }
  barre.querySelector(".tgl-lecteur__allumer").addEventListener("click", () => allumer(true));
  bouton("eteindre").addEventListener("click", () => allumer(false));

  // --- marge : bouton ▶ par paragraphe et trait du passage lu ----------------------------------
  // Le site découpe un paragraphe en mots cliquables quand il apparaît à l'écran, ce qui
  // efface son contenu : on remet nos éléments chaque fois qu'ils disparaissent.
  const repere = document.createElement("span");
  repere.className = "tgl-repere";

  function garnirMarge() {
    for (const p of texteGrec.querySelectorAll("p")) {
      p.classList.add("tgl-paragraphe");
      if (p.querySelector(":scope > .tgl-lire-ici")) continue;
      const b = document.createElement("button");
      b.type = "button";
      b.className = "tgl-lire-ici";
      b.title = "Lire à partir d'ici";
      b.textContent = "▶";
      b.addEventListener("click", (e) => {
        e.stopPropagation();
        lire(morceaux(p, null));
      });
      p.prepend(b);
    }
    if (enCours && !enCours.p.contains(repere)) placerRepere();
  }

  // --- découpage du texte en morceaux à lire ---------------------------------------------
  // Le texte d'un paragraphe reste le même avant et après son découpage en mots par le site :
  // un morceau est repéré par sa position en caractères { p, debut, fin, texte }.
  const ignorer = (n) => n.parentElement.closest(".text-milestone, .tgl-lire-ici, .tgl-repere");

  function noeudsTexte(p) {
    const marcheur = document.createTreeWalker(p, NodeFilter.SHOW_TEXT);
    const noeuds = [];
    for (let n = marcheur.nextNode(); n; n = marcheur.nextNode()) if (!ignorer(n)) noeuds.push(n);
    return noeuds;
  }

  function morceaux(depuis, selection) {
    const paragraphes = [...texteGrec.querySelectorAll("p")];
    const sortie = [];
    for (const p of paragraphes.slice(depuis ? paragraphes.indexOf(depuis) : 0)) {
      // partie du paragraphe à lire : tout, ou seulement ce qui est sélectionné
      let texte = "", debut = null, fin = null;
      for (const n of noeudsTexte(p)) {
        const t = n.textContent;
        if (selection && selection.intersectsNode(n)) {
          const a = n === selection.startContainer ? selection.startOffset : 0;
          const b = n === selection.endContainer ? selection.endOffset : t.length;
          if (debut === null) debut = texte.length + a;
          fin = texte.length + b;
        }
        texte += t;
      }
      if (!selection) [debut, fin] = [0, texte.length];
      if (debut === null) continue;
      // phrases regroupées jusqu'à une longueur confortable pour la voix
      let a = debut;
      for (const m of texte.slice(debut, fin).matchAll(/[^.;·;!]+[.;·;!]*/g)) {
        const b = debut + m.index + m[0].length;
        if (texte.slice(a, b).trim().length >= MIN_MORCEAU) {
          sortie.push({ p, debut: a, fin: b });
          a = b;
        }
      }
      if (texte.slice(a, fin).trim()) sortie.push({ p, debut: a, fin });
      for (const m of sortie) if (m.p === p) m.texte = texte.slice(m.debut, m.fin).replace(/\s+/g, " ").trim();
    }
    return sortie.filter((m) => /\p{L}/u.test(m.texte));
  }

  // Trait vertical dans la marge, à la hauteur des lignes du morceau lu.
  function placerRepere() {
    if (!enCours) return repere.remove();
    const { p, debut, fin } = enCours;
    const plage = document.createRange();
    let pos = 0;
    for (const n of noeudsTexte(p)) {
      const l = n.textContent.length;
      if (pos <= debut && debut < pos + l) plage.setStart(n, debut - pos);
      if (pos < fin && fin <= pos + l) plage.setEnd(n, fin - pos);
      pos += l;
    }
    const lignes = [...plage.getClientRects()].filter((r) => r.width > 1);
    if (!lignes.length) return;
    const haut = Math.min(...lignes.map((r) => r.top));
    const bas = Math.max(...lignes.map((r) => r.bottom));
    const cadre = p.getBoundingClientRect();
    if (!p.contains(repere)) p.append(repere);
    repere.style.top = `${haut - cadre.top}px`;
    repere.style.height = `${bas - haut}px`;
    if (haut < 80 || haut > innerHeight - 160) {
      repere.scrollIntoView({ block: "center", behavior: "smooth" });
    }
  }

  garnirMarge();
  new MutationObserver(garnirMarge).observe(texteGrec, { childList: true, subtree: true });
  addEventListener("resize", placerRepere);

  // --- lecture --------------------------------------------------------------------------

  function demander(texte, voix) {
    const cle = `${voix}|${texte}`;
    if (!enMemoire.has(cle)) {
      enMemoire.set(
        cle,
        chrome.runtime.sendMessage({ type: "lire", texte, voix }).then((r) => {
          if (!r?.ok) {
            enMemoire.delete(cle);
            throw new Error(r?.erreur || "pas de réponse");
          }
          return r.audio;
        }),
      );
    }
    return enMemoire.get(cle);
  }

  function jouer(b64, ma) {
    return new Promise((fini) => {
      finir = fini;
      audio = new Audio(`data:audio/wav;base64,${b64}`);
      audio.addEventListener("ended", fini);
      audio.addEventListener("error", fini);
      if (ma === session) audio.play().catch(fini);
      else fini();
    });
  }

  function interface(lecture) {
    for (const a of ["reculer", "avancer", "arreter"]) bouton(a).disabled = !lecture;
    const lire = bouton("lire");
    lire.textContent = lecture ? "⏸" : selectionDansTexte() ? "▶ Lire la sélection" : "▶ Lire";
    lire.title = lecture ? "Pause" : "Lire à partir du passage affiché";
  }

  async function lire(liste) {
    if (!liste.length) return;
    const ma = ++session;
    if (audio) audio.pause();
    const voix = choixVoix.value;
    interface(true);
    try {
      let i = 0;
      while (i < liste.length && ma === session) {
        etat.textContent = enMemoire.has(`${voix}|${liste[i].texte}`) ? "" : "Préparation de la voix…";
        const b64 = await demander(liste[i].texte, voix);
        if (i + 1 < liste.length) demander(liste[i + 1].texte, voix).catch(() => {});
        if (ma !== session) break;
        etat.textContent = "";
        enCours = Object.assign(liste[i], { indice: i });
        interface(true);
        placerRepere();
        await jouer(b64, ma);
        i = saut ?? i + 1;
        saut = null;
      }
    } catch (err) {
      etat.textContent =
        voix === "attique"
          ? "Voix attique introuvable : double-clique sur « Lancer la voix attique.command » dans le dossier grec-ancien-tts, puis réessaie."
          : "Lecteur introuvable : double-clique sur « Lancer le lecteur.command » dans le dossier lecteur-grec, puis réessaie.";
      console.warn("Lecteur grec :", err);
    }
    if (ma === session) arreter();
  }

  function sauter(vers) {
    if (!enCours || !finir) return;
    saut = Math.max(vers, 0);
    audio.pause();
    finir();
  }

  function arreter() {
    session++;
    if (audio) audio.pause();
    finir?.();
    enCours = finir = saut = null;
    placerRepere();
    interface(false);
  }

  // Sans lecture en cours, ▶ lit la sélection s'il y en a une dans le texte grec,
  // sinon à partir du premier paragraphe visible à l'écran.
  function selectionDansTexte() {
    const s = getSelection();
    if (!s.rangeCount || s.isCollapsed) return null;
    const r = s.getRangeAt(0);
    return texteGrec.contains(r.commonAncestorContainer) || r.intersectsNode(texteGrec) ? r : null;
  }
  function premierVisible() {
    // le premier paragraphe qui occupe encore le quart supérieur de l'écran
    return [...texteGrec.querySelectorAll("p")].find((p) => p.getBoundingClientRect().bottom > innerHeight / 4);
  }
  document.addEventListener("selectionchange", () => !enCours && interface(false));
  bouton("lire").addEventListener("mousedown", (e) => e.preventDefault()); // garder la sélection
  bouton("lire").addEventListener("click", () => {
    if (!enCours) {
      const sel = selectionDansTexte();
      lire(morceaux(sel ? null : premierVisible(), sel));
    } else if (audio.paused) {
      audio.play();
      bouton("lire").textContent = "⏸";
    } else {
      audio.pause();
      bouton("lire").textContent = "▶";
    }
  });
  // ⏮ : retour au début de la phrase ; si elle vient de commencer, phrase précédente
  bouton("reculer").addEventListener("click", () =>
    sauter(enCours.indice - (audio.currentTime < 2 ? 1 : 0)),
  );
  bouton("avancer").addEventListener("click", () => sauter(enCours.indice + 1));
  bouton("arreter").addEventListener("click", arreter);

  allumer(memoire.lire("tgl-lecteur-allume", "1") === "1");
})();
