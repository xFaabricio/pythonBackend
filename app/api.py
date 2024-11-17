from fastapi import FastAPI, jsonify
from sqlalchemy import create_engine, text
import os
import requests

DATABASE_URL = os.getenv("DATABASE_URL")
HEROKU_API_TOKEN = os.getenv("HEROKU_API_TOKEN")

# SQLAlchemy
engine = create_engine(DATABASE_URL)

app = FastAPI()

headers = {
    "Authorization": f"Bearer {HEROKU_API_TOKEN}",  # Token de autenticação
    "Accept": "application/vnd.heroku+json; version=3"  # Versão da API Heroku
}

@app.get("/testDatabase/")
async def databaseConnectionTest():
    query = "SELECT 'Database connected !' as message"  # Corrigido para retornar a mensagem desejada
    with engine.connect() as connection:
        result = connection.execute(text(query))
        return {"message": result.fetchone()["message"]}

@app.get("/", tags=["Root"])
async def serverUp():
    return {"serverUp": "Server running !!"}

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title="Custom Title",
        version="2.5.0",
        description="This is a very custom OpenAPI schema",
        routes=app.routes,
    )
    app.openapi_schema = openapi_schema
    return app.openapi_schema

# Endpoint para iniciar o dyno
@app.route("/start/<app_name>", methods=["POST"])
def start_app(app_name):
    """Start a Heroku app by its name"""
    url = f"https://api.heroku.com/apps/{app_name}/formation/web"
    response = requests.patch(url, headers=headers, json={"updates": [{"type": "web", "quantity": 1}]})

    if response.status_code == 200:
        return jsonify({"message": f"App {app_name} started successfully"}), 200
    else:
        return jsonify({"error": f"Failed to start app {app_name}"}), response.status_code


@app.route("/stop/<app_name>", methods=["POST"])
def stop_app(app_name):
    """Stop a Heroku app by its name"""
    url = f"https://api.heroku.com/apps/{app_name}/formation/web"
    response = requests.patch(url, headers=headers, json={"updates": [{"type": "web", "quantity": 0}]})

    if response.status_code == 200:
        return jsonify({"message": f"App {app_name} stopped successfully"}), 200
    else:
        return jsonify({"error": f"Failed to stop app {app_name}"}), response.status_code

@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    return get_swagger_ui_html(openapi_url="/openapi.json", title="Custom Swagger UI")

@app.get("/openapi.json", include_in_schema=False)
async def get_custom_openapi():
    return custom_openapi()

