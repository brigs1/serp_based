# app/__init__.py
from flask import Flask
import os
from config import Config

def create_app(config_class=Config):
    app = Flask(__name__,
                template_folder='../templates',  # 상위 디렉토리의 templates 폴더 지정
                static_folder='../static')       # 상위 디렉토리의 static 폴더 지정
    app.config.from_object(config_class)

    # Register blueprints
    from app.routes.main_routes import main
    from app.routes.api_routes import api
    app.register_blueprint(main)
    app.register_blueprint(api, url_prefix='/api')

    return app