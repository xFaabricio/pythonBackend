from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import JSONResponse
import os
import requests
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

DATABASE_URL = os.getenv("DATABASE_URL")
HEROKU_API_TOKEN = os.getenv("HEROKU_API_TOKEN")

# SQLAlchemy
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

app = FastAPI()

headers = {
    "Authorization": f"Bearer {HEROKU_API_TOKEN}",
    "Accept": "application/vnd.heroku+json; version=3",
    "Content-Type": "application/json"
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

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Função para validar a senha
def validate_password(db: Session, password: str):
    query = text("SELECT * FROM parameters WHERE key = :key AND enable = TRUE")
    result = db.execute(query, {"key": "BACKEND_PASSWORD"}).fetchone()  # Passando o valor como parâmetro
    if result and result["value"] == password:
        return True
    return False

# Endpoint para iniciar o dyno com validação de senha
@app.post("/start/{app_name}/{password}")
async def start_app(app_name: str, password: str, db: Session = Depends(get_db)):
    """Start a Heroku app by its name if password is valid"""
    # Verificando a senha
    if not validate_password(db, password):
        raise HTTPException(status_code=403, detail="Invalid password")

    url = f"https://api.heroku.com/apps/{app_name}/formation/web"
    data = {
        "type": "web",
        "quantity": 1  # Para iniciar o dyno
    }

    # Enviando a requisição PATCH
    response = requests.patch(url, headers=headers, json=data)

    if response.status_code == 200:
        return JSONResponse(content={"message": f"App {app_name} started successfully"}, status_code=200)
    else:
        return JSONResponse(content={"error": response.json(), "status_code": response.status_code}, status_code=response.status_code)

# Endpoint para parar o dyno com validação de senha
@app.post("/stop/{app_name}/{password}")
async def stop_app(app_name: str, password: str, db: Session = Depends(get_db)):
    """Stop a Heroku app by its name if password is valid"""
    # Verificando a senha
    if not validate_password(db, password):
        raise HTTPException(status_code=403, detail="Invalid password")

    url = f"https://api.heroku.com/apps/{app_name}/formation/web"
    data = {
        "type": "web",
        "quantity": 0  # Para parar o dyno
    }

    # Enviando a requisição PATCH para parar o dyno
    response = requests.patch(url, headers=headers, json=data)

    if response.status_code == 200:
        return JSONResponse(content={"message": f"App {app_name} stopped successfully"}, status_code=200)
    else:
        return JSONResponse(content={"error": response.json(), "status_code": response.status_code}, status_code=response.status_code)

@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    return get_swagger_ui_html(openapi_url="/openapi.json", title="Custom Swagger UI")

@app.get("/openapi.json", include_in_schema=False)
async def get_custom_openapi():
    return custom_openapi()

