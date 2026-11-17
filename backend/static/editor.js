// Protect words that have not been saved when changing sections or uploading.
const dirty = new Set();
document.querySelectorAll('form').forEach(form => {
  form.addEventListener('input', () => dirty.add(form));
  form.addEventListener('change', () => dirty.add(form));
  form.addEventListener('submit', event => {
    if ([...dirty].some(other => other !== form) &&
        !confirm('Your changes are not saved. Continue without saving them? Choose Cancel to stay here.')) {
      event.preventDefault();
      return;
    }
    dirty.clear();
  });
});
window.addEventListener('beforeunload', event => {
  if (dirty.size) { event.preventDefault(); event.returnValue = ''; }
});
