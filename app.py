from flask import Flask, jsonify
from flasgger import Swagger

app = Flask(__name__)

@app.route('/serverUp')
def server_up():
    """
    Verifica se o servidor está em execução.
    ---
    responses:
      200:
        description: Mensagem indicando que o servidor está em execução.
        schema:
          type: string
    """
    return jsonify(message='Server running!')

if __name__ == "__main__":
    # Criar uma instância da interface Swagger UI
    swagger = Swagger(app)

    # Definir o caminho personalizado para a interface Swagger UI
    app.config['SWAGGER'] = {
        'swagger_ui_prefix': '/api/docs'
    }

    app.run(debug=True)

