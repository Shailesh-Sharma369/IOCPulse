from app.config.settings import settings

def get_cors_origins():
    return settings.get_cors_origins()