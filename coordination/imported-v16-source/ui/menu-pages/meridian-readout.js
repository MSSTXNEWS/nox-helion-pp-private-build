/* NOX HELION original MIT FORMWORK MERIDIAN rolling readout adapter.
 * Original source https://github.com/shellcat-com/formwork-meridian
 * Git blob 47926c5e44ff1db7ae780136231b5373e7c5ff08; no fabricated metrics.
 * Only numeric values from existing confirmed OneHost replies are animated.
 */
(()=>{'use strict';
 const reduce=matchMedia('(prefers-reduced-motion: reduce)').matches;
  function buildOdometer(el, str) {
    el.classList.add('odo');
    const frag = document.createDocumentFragment();
    for (const ch of str) {
      if (ch >= '0' && ch <= '9') {
        const col = document.createElement('span'); col.className = 'odo-col';
        const reel = document.createElement('span'); reel.className = 'odo-reel';
        for (let d = 0; d <= 9; d++) {
          const dg = document.createElement('span');
          dg.className = 'odo-d'; dg.textContent = d;
          reel.appendChild(dg);
        }
        col.appendChild(reel);
        frag.appendChild(col);
      } else {
        const s = document.createElement('span');
        s.className = 'odo-fixed'; s.textContent = ch;
        frag.appendChild(s);
      }
    }
    el.textContent = '';
    el.appendChild(frag);
    el._mask = str.replace(/[0-9]/g, '#');
  }

  function setReel(reel, digit, animate) {
    if (!animate || reduce) {
      reel.style.transition = 'none';
      reel.style.transform = `translateY(-${digit}em)`;
      requestAnimationFrame(() => { reel.style.transition = ''; });
    } else {
      reel.style.transform = `translateY(-${digit}em)`;
    }
  }

  // rollTo(el, "93.5 °C") — rebuilds only when the digit/unit shape changes,
  // otherwise the existing reels animate from their current value to the new one.
  function rollTo(el, str, animate) {
    const mask = str.replace(/[0-9]/g, '#');
    if (el._mask !== mask) {
      buildOdometer(el, str);
      if (animate && !reduce) void el.offsetWidth; // commit the 0 state so 0→N animates
    }
    const cols = el.querySelectorAll('.odo-col');
    let ci = 0;
    for (const ch of str) {
      if (ch >= '0' && ch <= '9') setReel(cols[ci++].firstChild, +ch, animate);
    }
    el._val = str;
  }


 window.NOXMeridian=Object.freeze({rollTo});
})();
