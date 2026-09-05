(function () {
  function csrfToken() {
    var cookie = document.cookie
      .split('; ')
      .find(function (row) { return row.indexOf('csrftoken=') === 0; });
    return cookie ? cookie.split('=')[1] : '';
  }

  function rows() {
    return Array.prototype.slice.call(document.querySelectorAll('#homepage-blocks .block-row'));
  }

  function payload() {
    return rows().map(function (row) {
      return {
        id: row.dataset.id,
        heading: row.querySelector('.block-heading').value,
        category_id: row.querySelector('.block-category').value,
        article_count: row.querySelector('.block-count').value,
        desktop_columns: row.querySelector('.block-columns').value,
        is_enabled: row.querySelector('.block-enabled').checked,
        show_image: row.querySelector('.block-image').checked,
        show_description: row.querySelector('.block-description').checked
      };
    });
  }

  function moveRow(source, target) {
    var list = source.parentNode;
    var sourceBox = source.getBoundingClientRect();
    var targetBox = target.getBoundingClientRect();
    var before = sourceBox.top < targetBox.top
      ? target.nextSibling
      : target;
    list.insertBefore(source, before);
  }

  document.addEventListener('DOMContentLoaded', function () {
    var list = document.getElementById('homepage-blocks');
    if (!list) return;

    rows().forEach(function (row) {
      row.draggable = true;
      row.addEventListener('dragstart', function (event) {
        row.classList.add('is-dragging');
        event.dataTransfer.effectAllowed = 'move';
        event.dataTransfer.setData('text/plain', row.dataset.id || '');
      });
      row.addEventListener('dragend', function () {
        row.classList.remove('is-dragging');
      });
      row.addEventListener('dragover', function (event) {
        var dragging = list.querySelector('.is-dragging');
        if (!dragging || dragging === row) return;
        event.preventDefault();
        moveRow(dragging, row);
      });
    });

    document.getElementById('save-layout').addEventListener('click', function () {
      fetch(list.dataset.saveUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken()
        },
        credentials: 'same-origin',
        body: JSON.stringify(payload())
      });
    });
  });
})();
