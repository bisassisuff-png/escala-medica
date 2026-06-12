"""
Testes do mednews_service: parsing das fontes externas (com requests.get
mockado, sem acessar a rede) e refresh_mednews (cache em med_news_items).
"""
from unittest.mock import patch, MagicMock

from app.extensions import db
from app.models.mednews import MedNewsItem
from app.services.mednews_service import _fetch_svs, _fetch_jvs, refresh_mednews


SVS_HTML = """
<html><body><div class="view-content">
  <div class="views-row"><article class="listing-teaser node node--type-article">
    <div class="article-content">
      <h3><a href="/news-advocacy/articles-press-releases/noticia-um" rel="bookmark">
        <span class="field field--name-title">Primeira notícia de teste</span>
      </a></h3>
      <div class="node__content">
        <div class="field field--name-field-article-date field__item">
          <time datetime="2026-06-10T12:00:00Z" class="datetime">June 10, 2026</time>
        </div>
        <div class="clearfix text-formatted field field--name-body field__item">
          <p class="text-align-center"><em>Resumo da primeira notícia de teste.</em></p>
        </div>
      </div>
    </div>
  </article></div>
  <div class="views-row"><article class="listing-teaser node node--type-article">
    <div class="article-content">
      <h3><a href="/news-advocacy/articles-press-releases/noticia-dois" rel="bookmark">
        <span class="field field--name-title">Segunda notícia de teste</span>
      </a></h3>
      <div class="node__content">
        <div class="field field--name-field-article-date field__item">
          <time datetime="2026-05-27T12:00:00Z" class="datetime">May 27, 2026</time>
        </div>
        <div class="clearfix text-formatted field field--name-body field__item">
          <p class="text-align-center"><em>Resumo da segunda notícia de teste.</em></p>
        </div>
      </div>
    </div>
  </article></div>
</div></body></html>
"""

JVS_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>ScienceDirect Publication: Journal of Vascular Surgery</title>
  <item>
    <title><![CDATA[Corrigendum]]></title>
    <link>https://www.sciencedirect.com/science/article/pii/S0000000001</link>
    <description><![CDATA[<p>Publication date: July 2026</p><p><b>Source:</b> Journal of Vascular Surgery, Volume 84, Issue 1</p><p>Author(s): </p>]]></description>
  </item>
  <item>
    <title><![CDATA[Artigo de teste sobre cirurgia vascular]]></title>
    <link>https://www.sciencedirect.com/science/article/pii/S0000000002</link>
    <description><![CDATA[<p>Publication date: July 2026</p><p><b>Source:</b> Journal of Vascular Surgery, Volume 84, Issue 1</p><p>Author(s): Fulano de Tal, Ciclano</p>]]></description>
  </item>
</channel></rss>
"""


def _mock_response(text):
    resp = MagicMock()
    resp.text = text
    resp.content = text.encode('utf-8')
    resp.raise_for_status = MagicMock()
    return resp


def test_fetch_svs_parses_top_items():
    with patch('app.services.mednews_service.requests.get', return_value=_mock_response(SVS_HTML)):
        items = _fetch_svs()

    assert len(items) == 2
    assert items[0]['title'] == 'Primeira notícia de teste'
    assert items[0]['url'] == 'https://vascular.org/news-advocacy/articles-press-releases/noticia-um'
    assert items[0]['meta'] == 'June 10, 2026'
    assert items[0]['summary'] == 'Resumo da primeira notícia de teste.'
    assert items[1]['title'] == 'Segunda notícia de teste'


def test_fetch_jvs_parses_items_and_handles_missing_authors():
    with patch('app.services.mednews_service.requests.get', return_value=_mock_response(JVS_RSS)):
        items = _fetch_jvs()

    assert len(items) == 2
    assert items[0]['title'] == 'Corrigendum'
    assert items[0]['meta'] == 'July 2026 · Volume 84, Issue 1'
    assert items[0]['summary'] is None  # "Author(s): " vazio

    assert items[1]['title'] == 'Artigo de teste sobre cirurgia vascular'
    assert items[1]['url'] == 'https://www.sciencedirect.com/science/article/pii/S0000000002'
    assert items[1]['summary'] == 'Autor(es): Fulano de Tal, Ciclano'


def test_refresh_mednews_caches_items_and_keeps_old_on_failure(app):
    with app.app_context():
        # cache pré-existente para 'jvs', simulando uma atualização anterior
        db.session.add(MedNewsItem(
            source='jvs', title='Artigo antigo', url='https://example.com/antigo', meta=None,
        ))
        db.session.commit()

    svs_resp = _mock_response(SVS_HTML)

    def fake_get(url, *args, **kwargs):
        if 'vascular.org' in url:
            return svs_resp
        raise ConnectionError('jvs indisponível')

    with patch('app.services.mednews_service.requests.get', side_effect=fake_get):
        with app.app_context():
            result = refresh_mednews()

    assert result['svs'] == 'ok'
    assert result['jvs'].startswith('erro:')

    with app.app_context():
        svs_items = MedNewsItem.query.filter_by(source='svs').order_by(MedNewsItem.id).all()
        jvs_items = MedNewsItem.query.filter_by(source='jvs').all()

        assert [i.title for i in svs_items] == ['Primeira notícia de teste', 'Segunda notícia de teste']
        # cache antigo do jvs mantido após falha
        assert len(jvs_items) == 1
        assert jvs_items[0].title == 'Artigo antigo'
