# models.py
from extensions import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

class User(UserMixin, db.Model):
    __tablename__ = "user"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)

    # For storing user profile data
    full_name = db.Column(db.String(100), nullable=True)
    email = db.Column(db.String(120), unique=True, nullable=True)
    phone = db.Column(db.String(20), nullable=True)

    # Field referencing the chosen antenna
    antenna_id = db.Column(db.Integer, db.ForeignKey('antena.id', name="fk_user_antenna_id"), nullable=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<User {self.username}>"

class Antena(db.Model):
    __tablename__ = "antena"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    pdf_datasheet = db.Column(db.String(200), nullable=True)
    image = db.Column(db.String(200), nullable=True)
    description = db.Column(db.Text, nullable=True)

    # One antenna can be selected by multiple users
    users = db.relationship("User", backref="antena", lazy=True)

    def __repr__(self):
        return f"<Antena {self.name}>"
