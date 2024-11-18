import logging
import os
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from databases import Database
from fastapi import FastAPI, HTTPException, Depends
from pytz import timezone
from sqlalchemy import create_engine
from sqlalchemy import text, MetaData
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker

# LOGGING
logging.basicConfig(level=logging.INFO)
logging.getLogger("apscheduler").setLevel(logging.DEBUG)

# Configuração
DATABASE_URL = os.getenv("DATABASE_URL")
HEROKU_API_TOKEN = os.getenv("HEROKU_API_TOKEN")
LOCAL_TIMEZONE = timezone("America/Sao_Paulo")

database = Database(DATABASE_URL)
metadata = MetaData()

# Criação do engine e session
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Criação da base
Base = declarative_base(metadata=metadata)

# Criar todas as tabelas no banco de dados
# Base.metadata.create_all(bind=engine)  # Este comando cria as tabelas no banco de dados

# Inicializar o job store com o banco de dados
job_store = SQLAlchemyJobStore(url=DATABASE_URL)

app = FastAPI()

headers = {
    "Authorization": f"Bearer {HEROKU_API_TOKEN}",
    "Accept": "application/vnd.heroku+json; version=3",
    "Content-Type": "application/json",
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
            logging.info("E-mail enviado com sucesso.")
    except Exception as e:
        logging.error(f"Erro ao enviar o e-mail: {e}")


# Função para iniciar o dyno
def start_dyno(app_name: str, db: Session):
    logging.info(f"Job executando: start_dyno para {app_name}")
    url = f"https://api.heroku.com/apps/{app_name}/formation/web"
    data = {"type": "web", "quantity": 1}

    response = requests.patch(url, headers=headers, json=data)
    email = get_parameter(db, "EMAIL_JOB")

    if response.status_code == 200:
        message = f"O dyno da aplicação {app_name} foi iniciado com sucesso."
        logging.info(message)
        if email:
            send_email(f"App {app_name} Started", message, email)
    else:
        error = f"Erro ao iniciar o dyno da aplicação {app_name}: {response.json()}"
        logging.error(error)
        if email:
            send_email(f"App {app_name} Start Failed", error, email)


# Função para parar o dyno
def stop_dyno(app_name: str, db: Session):
    logging.info(f"Job executando: stop_dyno para {app_name}")
    url = f"https://api.heroku.com/apps/{app_name}/formation/web"
    data = {"type": "web", "quantity": 0}

    response = requests.patch(url, headers=headers, json=data)
    email = get_parameter(db, "EMAIL_JOB")

    if response.status_code == 200:
        message = f"O dyno da aplicação {app_name} foi parado com sucesso."
        logging.info(message)
        if email:
            send_email(f"App {app_name} Stopped", message, email)
    else:
        error = f"Erro ao parar o dyno da aplicação {app_name}: {response.json()}"
        logging.error(error)
        if email:
            send_email(f"App {app_name} Stop Failed", error, email)


# Job de teste
def test_job():
    now = datetime.now(LOCAL_TIMEZONE)
    logging.info(f"Test Job Executed at {now}")


# Agendamento com APScheduler
# Criação do scheduler
scheduler = BackgroundScheduler(jobstores={'default': job_store})

# Função de inicialização para o evento "startup"
@app.on_event("startup")
async def startup():
    # Adiciona os jobs ao iniciar a aplicação
    add_jobs()
    scheduler.start()
    logging.info("Scheduler iniciado e jobs agendados.")


@app.on_event("shutdown")
async def shutdown():
    scheduler.shutdown()
    logging.info("Scheduler finalizado.")


# Endpoint para listar jobs
@app.get("/list-jobs")
async def list_jobs():
    jobs = scheduler.get_jobs()
    return {
        "jobs": [
            {
                "id": job.id,
                "next_run_time": str(getattr(job, "next_run_time", None)) if getattr(job, "next_run_time",
                                                                                     None) else "Not scheduled",
                # Acesso seguro
                "trigger": str(job.trigger) if hasattr(job, "trigger") else "Unknown trigger",
                # Verificação de existência
            }
            for job in jobs
        ]
    }


# Endpoint para testar envio de e-mail
@app.post("/test-email/{password}")
async def test_email(password: str, db: Session = Depends(get_db)):
    if not validate_password(db, password):
        raise HTTPException(status_code=403, detail="Invalid password")

    email_recipient = get_parameter(db, "EMAIL_JOB")
    if not email_recipient:
        raise HTTPException(
            status_code=400, detail="E-mail de destino não configurado no banco de dados."
        )

    server_time = datetime.now(LOCAL_TIMEZONE)

    send_email(
        subject="Teste de E-mail",
        body=f"Horário atual do servidor: {server_time}",
        to_email=email_recipient,
    )

    return {"message": "E-mail de teste enviado com sucesso", "server_time": str(server_time)}


# Endpoint para iniciar o dyno
@app.post("/start/{app_name}/{password}")
async def start_app(app_name: str, password: str, db: Session = Depends(get_db)):
    if not validate_password(db, password):
        raise HTTPException(status_code=403, detail="Invalid password")
    start_dyno(app_name, db)
    return {"message": f"App {app_name} started successfully"}


# Endpoint para parar o dyno
@app.post("/stop/{app_name}/{password}")
async def stop_app(app_name: str, password: str, db: Session = Depends(get_db)):
    if not validate_password(db, password):
        raise HTTPException(status_code=403, detail="Invalid password")
    stop_dyno(app_name, db)
    return {"message": f"App {app_name} stopped successfully"}


# Endpoint para ativar um job
@app.post("/enable-job/{job_id}/{password}")
async def enable_job(job_id: str, password: str, db: Session = Depends(get_db)):
    if not validate_password(db, password):
        raise HTTPException(status_code=403, detail="Invalid password")

    job = scheduler.get_job(job_id)
    if job:
        job.resume()
        logging.info(f"Job {job_id} ativado.")
        return {"message": f"Job {job_id} ativado com sucesso."}
    else:
        raise HTTPException(status_code=404, detail="Job não encontrado.")


# Endpoint para desativar um job
@app.post("/disable-job/{job_id}/{password}")
async def disable_job(job_id: str, password: str, db: Session = Depends(get_db)):
    if not validate_password(db, password):
        raise HTTPException(status_code=403, detail="Invalid password")

    job = scheduler.get_job(job_id)
    if job:
        job.pause()
        logging.info(f"Job {job_id} desativado.")
        return {"message": f"Job {job_id} desativado com sucesso."}
    else:
        raise HTTPException(status_code=404, detail="Job não encontrado.")


# Função para adicionar os jobs ao scheduler
def add_jobs():
    job_test = scheduler.add_job(test_job, "interval", minutes=2, timezone="America/Sao_Paulo")
    job_start_paradise = scheduler.add_job(start_dyno,
                                           CronTrigger(hour=8, minute=0, second=0, timezone="America/Sao_Paulo"),
                                           args=["paradise-system"])
    job_start_msv = scheduler.add_job(start_dyno,
                                      CronTrigger(hour=8, minute=0, second=0, timezone="America/Sao_Paulo"),
                                      args=["msv-sevenheads"])
    job_stop_paradise = scheduler.add_job(stop_dyno,
                                          CronTrigger(hour=18, minute=0, second=0, timezone="America/Sao_Paulo"),
                                          args=["paradise-system"])
    job_stop_msv = scheduler.add_job(stop_dyno,
                                     CronTrigger(hour=18, minute=0, second=0, timezone="America/Sao_Paulo"),
                                     args=["msv-sevenheads"])

    # Adiciona os IDs dos jobs à lista
    job_ids = [job_test.id, job_start_paradise.id, job_start_msv.id, job_stop_paradise.id, job_stop_msv.id]
    logging.info(f"Jobs agendados: {job_ids}")