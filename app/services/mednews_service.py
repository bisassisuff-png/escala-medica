"""
Serviço de notícias médicas (card "MedNews" do dashboard admin).
Busca as 2 publicações mais recentes de duas fontes e grava em cache
(tabela med_news_items). Pensado para rodar 1x/semana via CLI (`flask
mednews-refresh`) — o dashboard só lê o cache.
"""
import logging
import xml.etree.ElementTree as ET
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from app.extensions import db
from app.models.mednews import MedNewsItem

logger = logging.getLogger(__name__)

HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; VascularVixAIHub/1.0)'}
TIMEOUT = 10

SVS_URL = 'https://vascular.org/news/articles-press-releases'
SVS_BASE = 'https://vascular.org'
JVS_RSS_URL = 'https://rss.sciencedirect.com/publication/science/07415214'

SUMMARY_MAX_LEN = 160


def _truncate(text, max_len=SUMMARY_MAX_LEN):
    text = ' '.join(text.split())
    if len(text) <= max_len:
        return text
    return text[:max_len - 1].rsplit(' ', 1)[0] + '…'


def _fetch_svs(limit=2):
    """Últimas notícias/press releases da SVS (vascular.org)."""
    resp = requests.get(SVS_URL, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, 'html.parser')

    items = []
    for article in soup.select('article.listing-teaser')[:limit]:
        link_el = article.select_one('h3 a')
        title_el = article.select_one('h3 a .field--name-title')
        if not link_el or not title_el:
            continue
        date_el = article.select_one('.field--name-field-article-date time')
        body_el = article.select_one('.field--name-body')

        title = title_el.get_text(strip=True)
        url = urljoin(SVS_BASE, link_el.get('href', ''))
        meta = date_el.get_text(strip=True) if date_el else None
        summary = body_el.get_text(' ', strip=True) if body_el else None
        items.append({
            'title': title,
            'url': url,
            'meta': meta,
            'summary': _truncate(summary) if summary else None,
        })
    return items


def _fetch_jvs(limit=2):
    """Últimas publicações ("Latest published") do Journal of Vascular
    Surgery, via feed RSS oficial do ScienceDirect (a página do journal
    bloqueia scraping com 403)."""
    resp = requests.get(JVS_RSS_URL, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)

    items = []
    for item_el in root.findall('./channel/item')[:limit]:
        title = (item_el.findtext('title') or '').strip()
        url = (item_el.findtext('link') or '').strip()
        description = item_el.findtext('description') or ''
        paragraphs = [p.get_text(strip=True)
                      for p in BeautifulSoup(description, 'html.parser').find_all('p')]

        pub_date = next((p for p in paragraphs if p.lower().startswith('publication date')), None)
        source_line = next((p for p in paragraphs if p.lower().startswith('source')), None)
        authors_line = next((p for p in paragraphs if p.lower().startswith('author')), None)

        if pub_date and ':' in pub_date:
            pub_date = pub_date.split(':', 1)[1].strip()
        if source_line and ':' in source_line:
            source_line = source_line.split(':', 1)[1].strip()
            prefix = 'Journal of Vascular Surgery, '
            if source_line.startswith(prefix):
                source_line = source_line[len(prefix):]

        meta = ' · '.join(p for p in (pub_date, source_line) if p) or None

        summary = None
        if authors_line and ':' in authors_line:
            names = authors_line.split(':', 1)[1].strip()
            if names:
                summary = f'Autor(es): {_truncate(names)}'

        items.append({'title': title, 'url': url, 'meta': meta, 'summary': summary})
    return items


def refresh_mednews() -> dict:
    """Atualiza o cache de notícias. Por fonte: se a busca falhar, mantém o
    cache anterior (degradação graciosa) e registra o erro no log."""
    result = {}
    for source, fetch_fn in (('svs', _fetch_svs), ('jvs', _fetch_jvs)):
        try:
            items = fetch_fn()
            if not items:
                raise ValueError('nenhum item retornado')
            now = datetime.utcnow()
            MedNewsItem.query.filter_by(source=source).delete()
            for item in items:
                db.session.add(MedNewsItem(
                    source=source,
                    title=item['title'],
                    summary=item.get('summary'),
                    url=item['url'],
                    meta=item.get('meta'),
                    fetched_at=now,
                ))
            db.session.commit()
            result[source] = 'ok'
        except Exception as exc:
            db.session.rollback()
            logger.warning('Falha ao atualizar MedNews (%s): %s', source, exc)
            result[source] = f'erro: {exc}'
    return result


def get_mednews_dashboard_context():
    """Retorna os dados do card MedNews para os dashboards (admin e médico)."""
    mednews_svs = MedNewsItem.query.filter_by(source='svs').order_by(MedNewsItem.id).limit(2).all()
    mednews_jvs = MedNewsItem.query.filter_by(source='jvs').order_by(MedNewsItem.id).limit(2).all()
    mednews_all = mednews_svs + mednews_jvs
    mednews_updated_at = max((m.fetched_at for m in mednews_all), default=None)
    return dict(mednews_svs=mednews_svs, mednews_jvs=mednews_jvs,
                 mednews_updated_at=mednews_updated_at)
