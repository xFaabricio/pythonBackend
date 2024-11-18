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
from datetime import datetime
import pytz
from pytz import timezone

# Configuração
DATABASE_URL = os.getenv("DATABASE_URL")
HEROKU_API_TOKEN = os.getenv("HEROKU_API_TOKEN")
LOCAL_TIMEZONE = timezone("America/Sao_Paulo")

# SQLAlchemy
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

app = FastAPI()

headers = {
    "Authorization": f"Bearer {HEROKU_API_TOKEN}",
    "Accept": "application/vnd.heroku+json; version=3",
    "Content-Type": "application/json"
}


# Obtém uma conexão com o banco de dados
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Função para validar senha
def validate_password(db: Session, password: str):
    query = text("SELECT * FROM parameters WHERE key = :key AND enable = TRUE")
    result = db.execute(query, {"key": "BACKEND_PASSWORD"}).fetchone()
    if result and result["value"] == password:
        return True
    return False


# Função para recuperar parâmetros
def get_parameter(db: Session, key: str):
    query = text("SELECT * FROM parameters WHERE key = :key AND enable = TRUE")
    result = db.execute(query, {"key": key}).fetchone()
    if result:
        return result["value"]
    return None


# Função para enviar e-mail
def send_email(subject, body, to_email):
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT"))
    smtp_username = os.getenv("SMTP_USERNAME")
    smtp_password = os.getenv("SMTP_PASSWORD")
    smtp_from = os.getenv("SMTP_FROM")

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


# Função para iniciar o dyno
def start_dyno(app_name: str, db: Session):
    url = f"https://api.heroku.com/apps/{app_name}/formation/web"
    data = {"type": "web", "quantity": 1}

    response = requests.patch(url, headers=headers, json=data)
    email = get_parameter(db, "EMAIL_JOB")

    if response.status_code == 200:
        message = f"O dyno da aplicação {app_name} foi iniciado com sucesso."
        print(message)
        if email:
            send_email(f"App {app_name} Started", message, email)
    else:
        error = f"Erro ao iniciar o dyno da aplicação {app_name}: {response.json()}"
        print(error)
        if email:
            send_email(f"App {app_name} Start Failed", error, email)


# Função para parar o dyno
def stop_dyno(app_name: str, db: Session):
    url = f"https://api.heroku.com/apps/{app_name}/formation/web"
    data = {"type": "web", "quantity": 0}

    response = requests.patch(url, headers=headers, json=data)
    email = get_parameter(db, "EMAIL_JOB")

    if response.status_code == 200:
        message = f"O dyno da aplicação {app_name} foi parado com sucesso."
        print(message)
        if email:
            send_email(f"App {app_name} Stopped", message, email)
    else:
        error = f"Erro ao parar o dyno da aplicação {app_name}: {response.json()}"
        print(error)
        if email:
            send_email(f"App {app_name} Stop Failed", error, email)


# Agendamento com APScheduler
scheduler = BackgroundScheduler()

# Agendar start e stop para ambas as aplicações
scheduler.add_job(start_dyno, 'cron', hour=8, minute=0, args=["paradise-system", Depends(get_db)])
scheduler.add_job(start_dyno, 'cron', hour=8, minute=0, args=["msv-sevenheads", Depends(get_db)])
scheduler.add_job(stop_dyno, 'cron', hour=15, minute=15, args=["paradise-system", Depends(get_db)])
scheduler.add_job(stop_dyno, 'cron', hour=15, minute=15, args=["msv-sevenheads", Depends(get_db)])


# Iniciar o agendador na inicialização da aplicação
@app.on_event("startup")
async def startup():
    scheduler.start()
    print("Scheduler iniciado")


# Endpoint para testar envio de e-mail
@app.post("/test-email/{password}")
async def test_email(password: str, db: Session = Depends(get_db)):
    if not validate_password(db, password):
        raise HTTPException(status_code=403, detail="Invalid password")

    email_recipient = get_parameter(db, "EMAIL_JOB")
    if not email_recipient:
        raise HTTPException(status_code=400, detail="E-mail de destino não configurado no banco de dados.")

    server_time = datetime.now()
    server_timezone = datetime.now().astimezone().tzinfo

    send_email(
        subject="Teste de E-mail",
        body=f"Horário atual do servidor: {server_time}\nFuso horário do servidor: {server_timezone}",
        to_email=email_recipient
    )

    return {"message": "E-mail de teste enviado com sucesso", "server_time": str(server_time),
            "server_timezone": str(server_timezone)}


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

@app.get("/", tags=["Root"])
async def serverUp():
    return {"serverUp": "Server running !!"}