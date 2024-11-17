from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import JSONResponse
import os
import requests
import smtplib
from apscheduler.schedulers.background import BackgroundScheduler
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from apscheduler.triggers.cron import CronTrigger
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
    query = "SELECT 'Database connected !' as message"
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
    result = db.execute(query, {"key": "BACKEND_PASSWORD"}).fetchone()
    if result and result["value"] == password:
        return True
    return False

# Endpoint para iniciar o dyno com validação de senha
@app.post("/start/{app_name}/{password}")
async def start_app(app_name: str, password: str, db: Session = Depends(get_db)):
    """Start a Heroku app by its name if password is valid"""
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

# Função para iniciar o dyno
def start_dyno(app_name: str):
    url = f"https://api.heroku.com/apps/{app_name}/formation/web"
    data = {
        "type": "web",
        "quantity": 1  # Para iniciar o dyno
    }
    response = requests.patch(url, headers=headers, json=data)
    if response.status_code == 200:
        print(f"App {app_name} started successfully")
    else:
        print(f"Error starting app {app_name}: {response.json()}")

# Função para parar o dyno
def stop_dyno(app_name: str):
    url = f"https://api.heroku.com/apps/{app_name}/formation/web"
    data = {
        "type": "web",
        "quantity": 0  # Para parar o dyno
    }
    response = requests.patch(url, headers=headers, json=data)
    if response.status_code == 200:
        print(f"App {app_name} stopped successfully")
    else:
        print(f"Error stopping app {app_name}: {response.json()}")

# Agendando a execução de start_dyno e stop_dyno com APScheduler
def schedule_jobs():
    scheduler = BackgroundScheduler()

    # Agendar para iniciar o dyno todos os dias às 8h
    scheduler.add_job(
        start_dyno,
        CronTrigger(hour=8, minute=0, second=0),
        args=["paradise-system"]  # Substitua "paradise-system" pelo nome real do seu app
    )

    # Agendar para parar o dyno todos os dias às 18h
    scheduler.add_job(
        stop_dyno,
        CronTrigger(hour=18, minute=0, second=0),
        args=["paradise-system"]  # Substitua "paradise-system" pelo nome real do seu app
    )

    # Iniciar o agendador
    scheduler.start()

# Rodando os jobs ao iniciar a aplicação
@app.on_event("startup")
async def startup():
    schedule_jobs()
    print("Scheduler started")

# Função para enviar o e-mail
def send_email(subject, body, to_email):
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT"))
    smtp_username = os.getenv("SMTP_USERNAME")
    smtp_password = os.getenv("SMTP_PASSWORD")
    smtp_from = os.getenv("SMTP_FROM")

    # Preparando o e-mail
    message = MIMEMultipart()
    message["From"] = smtp_from
    message["To"] = to_email
    message["Subject"] = subject

    message.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_username, smtp_password)
            server.sendmail(smtp_from, to_email, message.as_string())
            print("E-mail enviado com sucesso.")
    except Exception as e:
        print(f"Erro ao enviar o e-mail: {e}")

# Função para recuperar parâmetros
def get_parameter(db: Session, key: str):
    query = text("SELECT * FROM parameters WHERE key = :key AND enable = TRUE")
    result = db.execute(query, {"key": key}).fetchone()
    if result:
        return result["value"]
    return None

def should_send_email(db: Session):
    """Verificar se o envio de e-mail está habilitado para os jobs"""
    send_email_job = get_parameter(db, "SEND_EMAIL_JOB")
    return send_email_job == "1"

def start_app_email(app_name, db: Session):
    """Enviar e-mail quando iniciar o dyno, se permitido"""
    if should_send_email(db):
        email = get_parameter(db, "EMAIL_JOB")
        if email:
            send_email(
                subject=f"Heroku App {app_name} Started",
                body=f"O dyno da aplicação {app_name} foi iniciado com sucesso.",
                to_email=email
            )

def stop_app_email(app_name, db: Session):
    """Enviar e-mail quando parar o dyno, se permitido"""
    if should_send_email(db):
        email = get_parameter(db, "EMAIL_JOB")
        if email:
            send_email(
                subject=f"Heroku App {app_name} Stopped",
                body=f"O dyno da aplicação {app_name} foi parado com sucesso.",
                to_email=email
            )

# Agendando os trabalhos para as duas aplicações
scheduler = BackgroundScheduler()

# Agendando o start
scheduler.add_job(start_app_email, 'cron', hour=8, minute=0, args=["paradise-system", Depends(get_db)])
scheduler.add_job(start_app_email, 'cron', hour=8, minute=0, args=["msv-sevenheads", Depends(get_db)])

# Agendando o stop
scheduler.add_job(stop_app_email, 'cron', hour=18, minute=0, args=["paradise-system", Depends(get_db)])
scheduler.add_job(stop_app_email, 'cron', hour=18, minute=0, args=["msv-sevenheads", Depends(get_db)])

# Iniciando o agendador
scheduler.start()
