# config.py
import os

class Config:
    # Chave secreta para sessões Flask; em produção use variável de ambiente
    SECRET_KEY = os.environ.get("SECRET_KEY", "chave-super-secreta")
    
    # Conexão com o PostgreSQL; ajuste conforme necessário
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        "postgresql://postgres:123@localhost:5432/nanoweb"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Pasta para uploads (certifique-se de criá-la manualmente)
    UPLOAD_FOLDER = os.path.join("static", "uploads")
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # Limite de 16 MB
