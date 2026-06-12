from datetime import datetime
from app.extensions import db


class MedNewsItem(db.Model):
    __tablename__ = 'med_news_items'

    id = db.Column(db.Integer, primary_key=True)
    source = db.Column(db.String(20), nullable=False)   # 'svs' | 'jvs'
    title = db.Column(db.String(500), nullable=False)
    summary = db.Column(db.Text)
    url = db.Column(db.String(1000), nullable=False)
    meta = db.Column(db.String(255))
    fetched_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f'<MedNewsItem {self.source} {self.title!r}>'
