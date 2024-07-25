# Documentation Index

{% assign doclist = site.pages | sort: 'url'  %}
{% for doc in doclist %}
{% if doc.name contains '.md' and doc.dir == '/docs/' and doc.name != 'index.md' %}
* [{{ doc.name }}]({{ doc.url | relative_url }})
{% endif %}
{% endfor %}
