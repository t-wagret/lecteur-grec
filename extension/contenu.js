// Ajoute aux pages de texte de The Greek Library un bouton ▶ devant chaque paragraphe et une petite
// barre de lecture. Le texte est envoyé morceau par morceau au lecteur local (serveur_lecture.py) ;
// le morceau suivant est préparé pendant que le précédent est lu.
(() => {
  const texteGrec = document.querySelector("#greek-text");
  if (!texteGrec) return;

  const VOIX = ["spyros", "kostas", "athina", "katerina"];
  const MIN_MORCEAU = 100; // caractères : en dessous, la phrase suivante est jointe

  // --- barre de lecture -------------------------------------------------------------------
  const barre = document.createElement("div");
  barre.className = "tgl-lecteur";
  barre.innerHTML = `
    <button type="button" class="tgl-lecteur__lire">▶ Lire le texte</button>
    <button type="button" class="tgl-lecteur__pause" hidden>⏸</button>
    <button type="button" class="tgl-lecteur__stop" hidden>⏹</button>
    <select class="tgl-lecteur__voix" title="Voix">${VOIX.map((v) => `<option>${v}</option>`).join("")}</select>
    <span class="tgl-lecteur__etat" role="status"></span>`;
  document.body.append(barre);
  const [boutonLire, boutonPause, boutonStop] = barre.querySelectorAll("button");
  const choixVoix = barre.querySelector("select");
  const etat = barre.querySelector(".tgl-lecteur__etat");
  try {
    choixVoix.value = localStorage.getItem("tgl-lecteur-voix") || "spyros";
  } catch {}
  choixVoix.addEventListener("change", () => {
    try {
      localStorage.setItem("tgl-lecteur-voix", choixVoix.value);
    } catch {}
  });

  // Le site découpe un paragraphe en mots cliquables quand il apparaît à l'écran, ce qui
  // efface son contenu : on remet le bouton ▶ chaque fois qu'il disparaît.
  function ajouterBoutons() {
    for (const p of texteGrec.querySelectorAll("p")) {
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
  }
  ajouterBoutons();
  new MutationObserver(ajouterBoutons).observe(texteGrec, { childList: true, subtree: true });

  // --- découpage du texte en morceaux à lire ---------------------------------------------
  // Le texte d'un paragraphe reste le même avant et après son découpage en mots par le site :
  // un morceau est repéré par sa position en caractères { p, debut, fin, texte }.
  const ignorer = (n) => n.parentElement.closest(".text-milestone, .tgl-lire-ici");

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
        const long = texte.slice(a, b).trim().length;
        if (long >= MIN_MORCEAU) {
          sortie.push({ p, debut: a, fin: b });
          a = b;
        }
      }
      if (texte.slice(a, fin).trim()) sortie.push({ p, debut: a, fin });
      for (const m of sortie) if (m.p === p) m.texte = texte.slice(m.debut, m.fin).replace(/\s+/g, " ").trim();
    }
    return sortie.filter((m) => /\p{L}/u.test(m.texte));
  }

  // --- lecture --------------------------------------------------------------------------
  let session = 0; // change à chaque nouvelle lecture ou arrêt : l'ancienne boucle s'arrête
  let audio = null;
  let enCours = null; // morceau en train d'être lu
  const enMemoire = new Map();

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

  function surligner(morceau) {
    for (const m of texteGrec.querySelectorAll(".tgl-en-lecture")) m.classList.remove("tgl-en-lecture");
    if (!morceau) return;
    // mots dont le texte tombe entre debut et fin (s'il n'est pas encore découpé en mots par le
    // site, le paragraphe le sera en arrivant à l'écran, et on recommence un peu plus tard)
    let pos = 0, premier = null;
    for (const n of noeudsTexte(morceau.p)) {
      const mot = n.parentElement.closest(".reader-token");
      if (mot && pos < morceau.fin && pos + n.textContent.length > morceau.debut) {
        mot.classList.add("tgl-en-lecture");
        premier ??= mot;
      }
      pos += n.textContent.length;
    }
    const cible = premier || morceau.p;
    const r = cible.getBoundingClientRect();
    if (r.top < 80 || r.top > innerHeight - 160) cible.scrollIntoView({ block: "center", behavior: "smooth" });
    if (!premier) setTimeout(() => morceau === enCours && surligner(morceau), 600);
  }

  function jouer(b64, ma) {
    return new Promise((fini) => {
      audio = new Audio(`data:audio/wav;base64,${b64}`);
      audio.addEventListener("ended", fini);
      audio.addEventListener("error", fini);
      if (ma === session) audio.play().catch(fini);
      else fini();
    });
  }

  function interface(lecture) {
    boutonPause.hidden = boutonStop.hidden = !lecture;
    boutonLire.hidden = lecture;
    boutonPause.textContent = "⏸";
  }

  async function lire(liste) {
    if (!liste.length) return;
    const ma = ++session;
    if (audio) audio.pause();
    const voix = choixVoix.value;
    interface(true);
    try {
      for (let i = 0; i < liste.length && ma === session; i++) {
        etat.textContent = enMemoire.has(`${voix}|${liste[i].texte}`) ? "" : "Préparation de la voix…";
        const b64 = await demander(liste[i].texte, voix);
        if (i + 1 < liste.length) demander(liste[i + 1].texte, voix).catch(() => {});
        if (ma !== session) break;
        etat.textContent = "";
        enCours = liste[i];
        surligner(enCours);
        await jouer(b64, ma);
      }
    } catch (err) {
      etat.textContent =
        "Lecteur introuvable : double-clique sur « Lancer le lecteur.command » dans le dossier lecteur-grec, puis réessaie.";
      console.warn("Lecteur grec :", err);
    }
    if (ma === session) arreter();
  }

  function arreter() {
    session++;
    if (audio) audio.pause();
    enCours = null;
    surligner(null);
    interface(false);
  }

  // « Lire le texte » lit la sélection s'il y en a une dans le texte grec, sinon tout depuis le début
  function selectionDansTexte() {
    const s = getSelection();
    if (!s.rangeCount || s.isCollapsed) return null;
    const r = s.getRangeAt(0);
    return texteGrec.contains(r.commonAncestorContainer) || r.intersectsNode(texteGrec) ? r : null;
  }
  document.addEventListener("selectionchange", () => {
    boutonLire.textContent = selectionDansTexte() ? "▶ Lire la sélection" : "▶ Lire le texte";
  });
  boutonLire.addEventListener("mousedown", (e) => e.preventDefault()); // garder la sélection
  boutonLire.addEventListener("click", () => {
    const sel = selectionDansTexte();
    lire(morceaux(null, sel));
  });
  boutonPause.addEventListener("click", () => {
    if (!audio) return;
    if (audio.paused) {
      audio.play();
      boutonPause.textContent = "⏸";
    } else {
      audio.pause();
      boutonPause.textContent = "▶";
    }
  });
  boutonStop.addEventListener("click", arreter);
})();
