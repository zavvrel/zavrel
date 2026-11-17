/* Render saved words as text, never as HTML. */
(() => {
  const node = (tag, text, cls) => {
    const element = document.createElement(tag);
    if (text !== undefined) element.textContent = text;
    if (cls) element.className = cls;
    return element;
  };
  const safeLink = value => {
    try {
      const url = new URL(value);
      return url.protocol === 'https:' && !url.username && !url.password ? url.href : null;
    } catch { return null; }
  };
  fetch('/api/content', { cache: 'no-store' }).then(response => {
    if (!response.ok) throw new Error('Content unavailable');
    return response.json();
  }).then(({ document: doc }) => {
    if (!doc || typeof doc.title !== 'string' || !Array.isArray(doc.drawers) || doc.drawers.length !== 4 ||
      !doc.drawers.every(d => typeof d.title === 'string' && typeof d.text === 'string' && Array.isArray(d.photos))) {
      throw new Error('Invalid content');
    }
    document.title = doc.title;
    document.querySelector('h1').textContent = doc.title;
    const intro = document.querySelector('header p');
    intro.textContent = doc.intro;
    intro.classList.add('saved-text');
    document.querySelector('footer').textContent = doc.signature;
    document.querySelector('.hint').textContent = doc.hint;
    document.querySelectorAll('.cabinet > details').forEach((details, index) => {
      const drawer = doc.drawers[index];
      details.querySelector('summary').textContent = drawer.title;
      const inside = details.querySelector('.inside');
      inside.replaceChildren();
      if (index === 3) {
        const present = node('span', undefined, 'present');
        present.setAttribute('aria-hidden', 'true');
        inside.append(present);
        if (drawer.gift_heading) inside.append(node('h2', drawer.gift_heading));
      }
      if (drawer.text) inside.append(node('p', drawer.text, 'saved-text'));
      drawer.photos.forEach(photo => {
        if (!/^[a-f0-9]{32}$/.test(photo.id)) return;
        const figure = node('figure', undefined, 'drawer-photo');
        const image = node('img');
        image.src = '/media/' + photo.id + '.webp';
        image.alt = photo.alt || '';
        image.loading = 'lazy';
        figure.append(image);
        if (photo.caption) figure.append(node('figcaption', photo.caption));
        inside.append(figure);
      });
      const href = safeLink(drawer.link);
      if (href) {
        const link = node('a', drawer.link_label || 'Open link', 'drawer-link');
        link.href = href;
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
        inside.append(link);
      } else if (index === 3 && drawer.placeholder) {
        inside.append(node('span', drawer.placeholder, 'playlist-placeholder'));
      }
    });
  }).catch(() => {
    const message = node('p', 'The latest saved words could not load. Please refresh in a moment.', 'content-status');
    message.setAttribute('role', 'status');
    document.querySelector('main').append(message);
  });
})();
