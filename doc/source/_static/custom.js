document.addEventListener('DOMContentLoaded', function () {

    /* open links in new windows */
    /* TODO: include internal links which aren't in nav bar */
    var externalLinks = document.querySelectorAll('a.external');
    externalLinks.forEach(function (link) {
        link.setAttribute('target', '_blank');
    });

});