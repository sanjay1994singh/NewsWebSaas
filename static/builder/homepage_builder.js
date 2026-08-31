(function ($) {
  function csrfToken() {
    return document.cookie
      .split('; ')
      .find(function (row) { return row.startsWith('csrftoken='); })
      ?.split('=')[1] || '';
  }

  function payload() {
    return $('#homepage-blocks .block-row').map(function () {
      var row = $(this);
      return {
        id: row.data('id'),
        heading: row.find('.block-heading').val(),
        category_id: row.find('.block-category').val(),
        article_count: row.find('.block-count').val(),
        desktop_columns: row.find('.block-columns').val(),
        is_enabled: row.find('.block-enabled').is(':checked'),
        show_image: row.find('.block-image').is(':checked'),
        show_description: row.find('.block-description').is(':checked')
      };
    }).get();
  }

  $(function () {
    $('#homepage-blocks').sortable({
      handle: '.drag-handle',
      axis: 'y'
    });

    $('#save-layout').on('click', function () {
      var list = $('#homepage-blocks');
      $.ajax({
        url: list.data('save-url'),
        method: 'POST',
        contentType: 'application/json',
        headers: { 'X-CSRFToken': csrfToken() },
        data: JSON.stringify(payload())
      });
    });
  });
})(jQuery);
