from app.extensions import db

class DocumentSection(db.Model):
    __tablename__ = 'document_sections'

    id = db.Column(db.Integer, primary_key=True)
    document_draft_id = db.Column(db.Integer, db.ForeignKey('document_drafts.id'), nullable=False)
    title = db.Column(db.String(255))
    content = db.Column(db.Text)  # Rich HTML
    position = db.Column(db.Integer, default=0)

    draft = db.relationship('DocumentDraft', backref='sections')

    def to_dict(self):
        return {
            "id": self.id,
            "document_draft_id": self.document_draft_id,
            "title": self.title,
            "content": self.content,
            "position": self.position
        }
