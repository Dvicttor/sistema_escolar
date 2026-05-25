import os
from io import BytesIO

from flask import Flask, flash, redirect, render_template, request, send_file, url_for, session
from mysql.connector import Error

from db import IntegrityError, database_label, execute, fetch_all, fetch_one, is_sqlite
from relatorios import gerar_relatorio_json, gerar_relatorio_pdf
from auth import (
    login_usuario,
    logout_usuario,
    obter_usuario_autenticado,
    registrar_usuario,
    requer_autenticacao,
    requer_tipo,
)


app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "sistema-academico-dev")


def validar_campos_obrigatorios(campos):
    dados = {}
    erros = []
    for nome_campo, rotulo in campos.items():
        valor = request.form.get(nome_campo, "").strip()
        dados[nome_campo] = valor
        if not valor:
            erros.append(f"O campo {rotulo} e obrigatorio.")
    return dados, erros


def somente_digitos(valor):
    return "".join(caractere for caractere in valor if caractere.isdigit())


def validar_cpf(cpf):
    if len(somente_digitos(cpf)) != 11:
        return "O CPF deve ter 11 numeros."
    return None


def validar_carga_horaria():
    valor = request.form.get("carga_horaria", "").strip()
    try:
        carga_horaria = int(valor)
    except ValueError:
        return None, "A carga horaria deve ser um numero inteiro."

    if carga_horaria < 1:
        return None, "A carga horaria deve ser maior que zero."

    return carga_horaria, None


def get_avisos_configuracao():
    avisos = []
    if app.secret_key == "sistema-academico-dev":
        avisos.append("Defina FLASK_SECRET_KEY antes de usar o sistema fora do ambiente de testes.")
    if os.getenv("FLASK_DEBUG", "").lower() in {"1", "true", "yes"}:
        avisos.append("Desative FLASK_DEBUG em ambiente de producao.")
    return avisos


def get_dashboard_counts():
    return {
        "alunos": fetch_one("SELECT COUNT(*) AS total FROM alunos")["total"],
        "professores": fetch_one("SELECT COUNT(*) AS total FROM professores")["total"],
        "disciplinas": fetch_one("SELECT COUNT(*) AS total FROM disciplinas")["total"],
        "matriculas": fetch_one(
            "SELECT COUNT(*) AS total FROM matriculas WHERE ativo = 1"
        )["total"],
    }


def get_dados_relatorio_banco():
    alunos = fetch_all(
        """
        SELECT id, nome, cpf, matricula, curso, criado_em
          FROM alunos
         ORDER BY nome
        """
    )
    professores = fetch_all(
        """
        SELECT id, nome, cpf, registro, area, criado_em
          FROM professores
         ORDER BY nome
        """
    )
    disciplinas = fetch_all(
        """
        SELECT d.id, d.nome, d.codigo, d.carga_horaria,
               COALESCE(p.nome, 'Sem professor') AS professor,
               d.criado_em
          FROM disciplinas d
          LEFT JOIN professores p ON p.id = d.professor_id
         ORDER BY d.nome
        """
    )
    matriculas = fetch_all(
        """
        SELECT m.id, a.nome AS aluno, a.matricula,
               d.nome AS disciplina, d.codigo,
               CASE WHEN m.ativo = 1 THEN 'ativa' ELSE 'removida' END AS status,
               m.criado_em, m.removido_em
          FROM matriculas m
          JOIN alunos a ON a.id = m.aluno_id
          JOIN disciplinas d ON d.id = m.disciplina_id
         ORDER BY d.nome, a.nome
        """
    )

    return {
        "banco": database_label(),
        "alunos": alunos,
        "professores": professores,
        "disciplinas": disciplinas,
        "matriculas": matriculas,
    }


@app.errorhandler(Error)
def handle_database_error(error):
    return render_template("erro.html", error=error), 500


# ============= ROTAS DE AUTENTICACAO =============

@app.route("/login", methods=["GET", "POST"])
def login():
    usuario = obter_usuario_autenticado()
    if usuario:
        return redirect(url_for("dashboard"))
    
    username = ""
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        senha = request.form.get("password", "").strip()
        
        if not username or not senha:
            flash("Erro: usuário e senha são obrigatórios. Tente novamente.", "warning")
            return render_template("login.html", username=username)
        
        resultado = login_usuario(username, senha)
        if resultado['sucesso']:
            flash(resultado['mensagem'], 'success')
            return redirect(url_for("dashboard"))
        else:
            flash("Erro: usuário ou senha incorretos. Tente novamente.", 'warning')
            return render_template("login.html", username=username)
    
    return render_template("login.html", username=username)


@app.route("/logout")
def logout():
    logout_usuario()
    flash("Logout realizado com sucesso.", "success")
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    usuario = obter_usuario_autenticado()
    if usuario:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        dados, erros = validar_campos_obrigatorios(
            {
                "username": "Usuário",
                "email": "Email",
                "senha": "Senha",
                "nome": "Nome",
                "cpf": "CPF",
                "matricula": "Matrícula",
                "curso": "Curso",
            }
        )

        if erros:
            for erro in erros:
                flash(erro, "warning")
            return render_template("register.html", **dados)

        if len(dados["senha"]) < 6:
            flash("A senha deve ter pelo menos 6 caracteres.", "warning")
            return render_template("register.html", **dados)

        try:
            aluno_id = execute(
                """
                INSERT INTO alunos (nome, cpf, matricula, curso)
                VALUES (%s, %s, %s, %s)
                """,
                (dados["nome"], dados["cpf"], dados["matricula"], dados["curso"]),
            )
        except IntegrityError as e:
            mensagem_erro = str(e).lower()
            if "cpf" in mensagem_erro or "matricula" in mensagem_erro:
                flash("CPF ou matrícula já cadastrado.", "warning")
            else:
                flash("Erro ao cadastrar perfil de aluno. Tente novamente.", "danger")
            return render_template("register.html", **dados)

        resultado = registrar_usuario(
            dados["username"],
            dados["email"],
            dados["senha"],
            "aluno",
            aluno_id=aluno_id,
        )

        if not resultado["sucesso"]:
            execute(
                "DELETE FROM alunos WHERE id = %s",
                (aluno_id,),
            )
            flash(resultado["mensagem"], "warning")
            return render_template("register.html", **dados)

        flash("Cadastro realizado com sucesso. Agora faça login.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/dashboard")
@requer_autenticacao
def dashboard():
    usuario = obter_usuario_autenticado()
    
    if usuario['tipo'] == 'aluno':
        return redirect(url_for("dashboard_aluno"))
    elif usuario['tipo'] == 'professor':
        return redirect(url_for("dashboard_professor"))
    else:
        return redirect(url_for("secretaria_scope"))


@app.route("/dashboard/aluno")
@requer_tipo("aluno")
def dashboard_aluno():
    usuario = obter_usuario_autenticado()
    aluno_id = usuario['aluno_id']
    
    disciplinas_count = fetch_one(
        """
        SELECT COUNT(*) AS total FROM matriculas 
        WHERE aluno_id = %s AND ativo = 1
        """,
        (aluno_id,)
    )['total']

    professores_count = fetch_one(
        """
        SELECT COUNT(DISTINCT p.id) AS total
          FROM matriculas m
          JOIN disciplinas d ON d.id = m.disciplina_id
          JOIN professores p ON p.id = d.professor_id
         WHERE m.aluno_id = %s AND m.ativo = 1
        """,
        (aluno_id,)
    )['total']
    
    return render_template(
        "dashboard.html",
        usuario=usuario,
        disciplinas_count=disciplinas_count,
        professores_count=professores_count,
    )


@app.route("/ver-disciplinas")
@requer_tipo("aluno")
def ver_disciplinas():
    pesquisa = request.args.get("pesquisa", "").strip()
    filtro = ""
    params = ()
    if pesquisa:
        filtro = """
        WHERE LOWER(d.nome) LIKE LOWER(%s)
           OR LOWER(d.codigo) LIKE LOWER(%s)
           OR LOWER(p.nome) LIKE LOWER(%s)
        """
        params = (f"%{pesquisa}%", f"%{pesquisa}%", f"%{pesquisa}%")

    disciplinas = fetch_all(
        """
        SELECT d.id, d.nome, d.codigo, d.carga_horaria,
               COALESCE(p.nome, 'Sem professor') AS professor,
               COUNT(m.aluno_id) AS total_alunos
          FROM disciplinas d
          LEFT JOIN professores p ON p.id = d.professor_id
          LEFT JOIN matriculas m ON m.disciplina_id = d.id AND m.ativo = 1
         {filtro}
         GROUP BY d.id, p.nome
         ORDER BY d.nome
        """.format(filtro=filtro),
        params,
    )
    return render_template(
        "disciplinas.html",
        disciplinas=disciplinas,
        pesquisa=pesquisa,
        read_only=True,
    )


@app.route("/ver-professores")
@requer_tipo("aluno")
def ver_professores():
    pesquisa = request.args.get("pesquisa", "").strip()
    filtro = ""
    params = ()
    if pesquisa:
        filtro = """
        WHERE LOWER(p.nome) LIKE LOWER(%s)
           OR LOWER(p.registro) LIKE LOWER(%s)
           OR LOWER(p.area) LIKE LOWER(%s)
        """
        params = (f"%{pesquisa}%", f"%{pesquisa}%", f"%{pesquisa}%")

    group_concat = "GROUP_CONCAT(d.nome, ', ')" if is_sqlite() else "GROUP_CONCAT(d.nome ORDER BY d.nome SEPARATOR ', ')"
    professores = fetch_all(
        f"""
        SELECT p.*, {group_concat} AS disciplinas
          FROM professores p
          LEFT JOIN disciplinas d ON d.professor_id = p.id
         {filtro}
         GROUP BY p.id
         ORDER BY p.nome
        """,
        params,
    )
    return render_template(
        "professores.html",
        professores=professores,
        pesquisa=pesquisa,
        read_only=True,
    )


@app.route("/dashboard/professor")
@requer_tipo("professor")
def dashboard_professor():
    usuario = obter_usuario_autenticado()
    professor_id = usuario['professor_id']
    
    disciplinas_count = fetch_one(
        """
        SELECT COUNT(*) AS total FROM disciplinas 
        WHERE professor_id = %s
        """,
        (professor_id,)
    )['total'] if professor_id else 0
    
    alunos_count = fetch_one(
        """
        SELECT COUNT(DISTINCT m.aluno_id) AS total FROM matriculas m
        JOIN disciplinas d ON d.id = m.disciplina_id
        WHERE d.professor_id = %s AND m.ativo = 1
        """,
        (professor_id,)
    )['total'] if professor_id else 0
    
    return render_template(
        "dashboard.html",
        usuario=usuario,
        disciplinas_count=disciplinas_count,
        alunos_count=alunos_count
    )


@app.route('/secretaria')
@requer_tipo('secretaria')
def secretaria_scope():
    # Escopo antigo com links para cadastros principais
    return render_template('secretaria_old.html')


@app.route("/dashboard/secretaria")
@requer_tipo("secretaria")
def dashboard_secretaria():
    usuario = obter_usuario_autenticado()
    counts = get_dashboard_counts()
    
    return render_template(
        "dashboard.html",
        usuario=usuario,
        alunos_count=counts['alunos'],
        professores_count=counts['professores'],
        disciplinas_count=counts['disciplinas'],
        matriculas_count=counts['matriculas']
    )


@app.route("/perfil")
@requer_autenticacao
def perfil_usuario():
    usuario = obter_usuario_autenticado()
    usuario_info = None
    
    if usuario['tipo'] == 'aluno':
        usuario_info = fetch_one(
            "SELECT nome, cpf, matricula, curso FROM alunos WHERE id = %s",
            (usuario['aluno_id'],)
        )
    elif usuario['tipo'] == 'professor':
        usuario_info = fetch_one(
            "SELECT nome, cpf, registro, area FROM professores WHERE id = %s",
            (usuario['professor_id'],)
        )
    
    return render_template(
        "perfil.html",
        usuario=usuario,
        usuario_info=usuario_info
    )


@app.route("/minhas-disciplinas")
@requer_tipo("aluno")
def minhas_disciplinas():
    usuario = obter_usuario_autenticado()
    aluno_id = usuario['aluno_id']
    
    disciplinas = fetch_all(
        """
        SELECT d.id, d.nome, d.codigo, d.carga_horaria,
               COALESCE(p.nome, 'Sem professor') AS professor
          FROM matriculas m
          JOIN disciplinas d ON d.id = m.disciplina_id
          LEFT JOIN professores p ON p.id = d.professor_id
         WHERE m.aluno_id = %s AND m.ativo = 1
         ORDER BY d.nome
        """,
        (aluno_id,)
    )
    
    return render_template(
        "minhas_disciplinas_aluno.html",
        disciplinas=disciplinas
    )


@app.route("/minhas-disciplinas-professor")
@requer_tipo("professor")
def minhas_disciplinas_prof():
    usuario = obter_usuario_autenticado()
    professor_id = usuario['professor_id']
    
    if not professor_id:
        flash("Você não está vinculado a nenhuma disciplina.", "info")
        return redirect(url_for("dashboard"))
    
    disciplinas = fetch_all(
        """
        SELECT id, nome, codigo, carga_horaria FROM disciplinas
         WHERE professor_id = %s
         ORDER BY nome
        """,
        (professor_id,)
    )
    
    return render_template(
        "minhas_disciplinas_professor.html",
        disciplinas=disciplinas
    )


@app.route("/alunos-minhas-disciplinas")
@requer_tipo("professor")
def alunos_minhas_disciplinas():
    usuario = obter_usuario_autenticado()
    professor_id = usuario['professor_id']
    
    if not professor_id:
        flash("Você não está vinculado a nenhuma disciplina.", "info")
        return redirect(url_for("dashboard"))
    
    alunos = fetch_all(
        """
        SELECT DISTINCT a.id, a.nome, a.matricula, a.curso, d.nome AS disciplina
          FROM matriculas m
          JOIN alunos a ON a.id = m.aluno_id
          JOIN disciplinas d ON d.id = m.disciplina_id
         WHERE d.professor_id = %s AND m.ativo = 1
         ORDER BY d.nome, a.nome
        """,
        (professor_id,)
    )
    
    return render_template(
        "alunos_minhas_disciplinas.html",
        alunos=alunos
    )


# ============= PROTEGER ROTA DO INDEX =============
@app.route("/")
def index():
    usuario = obter_usuario_autenticado()
    if usuario:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.get("/relatorios/json")
def baixar_relatorio_json():
    conteudo = gerar_relatorio_json(get_dados_relatorio_banco())
    return send_file(
        BytesIO(conteudo.encode("utf-8")),
        mimetype="application/json",
        as_attachment=True,
        download_name="relatorio_academico.json",
    )


@app.get("/relatorios/pdf")
def baixar_relatorio_pdf():
    conteudo = gerar_relatorio_pdf(get_dados_relatorio_banco())
    return send_file(
        BytesIO(conteudo),
        mimetype="application/pdf",
        as_attachment=True,
        download_name="relatorio_academico.pdf",
    )


@app.route("/alunos", methods=["GET", "POST"])
@requer_tipo("secretaria")
def alunos():
    if request.method == "POST":
        dados, erros = validar_campos_obrigatorios(
            {
                "nome": "Nome",
                "cpf": "CPF",
                "matricula": "Matricula",
                "curso": "Curso",
            }
        )
        if erros:
            for erro in erros:
                flash(erro, "warning")
            return redirect(url_for("alunos"))
        erro_cpf = validar_cpf(dados["cpf"])
        if erro_cpf:
            flash(erro_cpf, "warning")
            return redirect(url_for("alunos"))

        try:
            execute(
                """
                INSERT INTO alunos (nome, cpf, matricula, curso)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    dados["nome"],
                    dados["cpf"],
                    dados["matricula"],
                    dados["curso"],
                ),
            )
            flash("Aluno cadastrado com sucesso.", "success")
        except IntegrityError:
            flash("Ja existe aluno com este CPF ou matricula.", "warning")
        return redirect(url_for("alunos"))

    pesquisa = request.args.get("pesquisa", "").strip()
    filtro_nome = ""
    params = ()
    if pesquisa:
        filtro_nome = "WHERE LOWER(a.nome) LIKE LOWER(%s)"
        params = (f"%{pesquisa}%",)

    group_concat = "GROUP_CONCAT(d.nome, ', ')" if is_sqlite() else "GROUP_CONCAT(d.nome ORDER BY d.nome SEPARATOR ', ')"
    lista = fetch_all(
        f"""
        SELECT a.*,
               {group_concat} AS disciplinas
          FROM alunos a
          LEFT JOIN matriculas m ON m.aluno_id = a.id AND m.ativo = 1
          LEFT JOIN disciplinas d ON d.id = m.disciplina_id
         {filtro_nome}
         GROUP BY a.id
         ORDER BY a.nome
        """,
        params,
    )
    return render_template("alunos.html", alunos=lista, pesquisa=pesquisa)


@app.route("/alunos/<int:aluno_id>/editar", methods=["GET", "POST"])
@requer_tipo("secretaria")
def editar_aluno(aluno_id):
    aluno = fetch_one("SELECT * FROM alunos WHERE id = %s", (aluno_id,))
    if not aluno:
        flash("Aluno nao encontrado.", "warning")
        return redirect(url_for("alunos"))

    if request.method == "POST":
        dados, erros = validar_campos_obrigatorios(
            {
                "nome": "Nome",
                "cpf": "CPF",
                "matricula": "Matricula",
                "curso": "Curso",
            }
        )
        if erros:
            for erro in erros:
                flash(erro, "warning")
            return redirect(url_for("editar_aluno", aluno_id=aluno_id))
        erro_cpf = validar_cpf(dados["cpf"])
        if erro_cpf:
            flash(erro_cpf, "warning")
            return redirect(url_for("editar_aluno", aluno_id=aluno_id))

        try:
            execute(
                """
                UPDATE alunos
                   SET nome = %s, cpf = %s, matricula = %s, curso = %s
                 WHERE id = %s
                """,
                (
                    dados["nome"],
                    dados["cpf"],
                    dados["matricula"],
                    dados["curso"],
                    aluno_id,
                ),
            )
            flash("Aluno atualizado com sucesso.", "success")
            return redirect(url_for("alunos"))
        except IntegrityError:
            flash("Ja existe aluno com este CPF ou matricula.", "warning")

    return render_template("editar_aluno.html", aluno=aluno)


@app.route("/professores", methods=["GET", "POST"])
@requer_tipo("secretaria")
def professores():
    if request.method == "POST":
        dados, erros = validar_campos_obrigatorios(
            {
                "nome": "Nome",
                "cpf": "CPF",
                "registro": "Registro",
                "area": "Area",
            }
        )
        if erros:
            for erro in erros:
                flash(erro, "warning")
            return redirect(url_for("professores"))
        erro_cpf = validar_cpf(dados["cpf"])
        if erro_cpf:
            flash(erro_cpf, "warning")
            return redirect(url_for("professores"))

        try:
            execute(
                """
                INSERT INTO professores (nome, cpf, registro, area)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    dados["nome"],
                    dados["cpf"],
                    dados["registro"],
                    dados["area"],
                ),
            )
            flash("Professor cadastrado com sucesso.", "success")
        except IntegrityError:
            flash("Ja existe professor com este CPF ou registro.", "warning")
        return redirect(url_for("professores"))

    pesquisa = request.args.get("pesquisa", "").strip()
    filtro = ""
    params = ()
    if pesquisa:
        filtro = """
        WHERE LOWER(p.nome) LIKE LOWER(%s)
           OR LOWER(p.registro) LIKE LOWER(%s)
           OR LOWER(p.area) LIKE LOWER(%s)
        """
        params = (f"%{pesquisa}%", f"%{pesquisa}%", f"%{pesquisa}%")

    group_concat = "GROUP_CONCAT(d.nome, ', ')" if is_sqlite() else "GROUP_CONCAT(d.nome ORDER BY d.nome SEPARATOR ', ')"
    lista = fetch_all(
        f"""
        SELECT p.*,
               {group_concat} AS disciplinas
          FROM professores p
          LEFT JOIN disciplinas d ON d.professor_id = p.id
         {filtro}
         GROUP BY p.id
         ORDER BY p.nome
        """,
        params,
    )
    return render_template("professores.html", professores=lista, pesquisa=pesquisa)


@app.route("/professores/<int:professor_id>/editar", methods=["GET", "POST"])
@requer_tipo("secretaria")
def editar_professor(professor_id):
    professor = fetch_one("SELECT * FROM professores WHERE id = %s", (professor_id,))
    if not professor:
        flash("Professor nao encontrado.", "warning")
        return redirect(url_for("professores"))

    if request.method == "POST":
        dados, erros = validar_campos_obrigatorios(
            {
                "nome": "Nome",
                "cpf": "CPF",
                "registro": "Registro",
                "area": "Area",
            }
        )
        if erros:
            for erro in erros:
                flash(erro, "warning")
            return redirect(url_for("editar_professor", professor_id=professor_id))
        erro_cpf = validar_cpf(dados["cpf"])
        if erro_cpf:
            flash(erro_cpf, "warning")
            return redirect(url_for("editar_professor", professor_id=professor_id))

        try:
            execute(
                """
                UPDATE professores
                   SET nome = %s, cpf = %s, registro = %s, area = %s
                 WHERE id = %s
                """,
                (
                    dados["nome"],
                    dados["cpf"],
                    dados["registro"],
                    dados["area"],
                    professor_id,
                ),
            )
            flash("Professor atualizado com sucesso.", "success")
            return redirect(url_for("professores"))
        except IntegrityError:
            flash("Ja existe professor com este CPF ou registro.", "warning")

    return render_template("editar_professor.html", professor=professor)


@app.route("/disciplinas", methods=["GET", "POST"])
@requer_tipo("secretaria")
def disciplinas():
    if request.method == "POST":
        dados, erros = validar_campos_obrigatorios(
            {
                "nome": "Nome",
                "codigo": "Codigo",
            }
        )
        carga_horaria, erro_carga = validar_carga_horaria()
        if erro_carga:
            erros.append(erro_carga)
        if erros:
            for erro in erros:
                flash(erro, "warning")
            return redirect(url_for("disciplinas"))

        professor_id = request.form.get("professor_id") or None
        try:
            execute(
                """
                INSERT INTO disciplinas (nome, codigo, carga_horaria, professor_id)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    dados["nome"],
                    dados["codigo"],
                    carga_horaria,
                    professor_id,
                ),
            )
            flash("Disciplina cadastrada com sucesso.", "success")
        except IntegrityError:
            flash("Ja existe disciplina com este codigo.", "warning")
        return redirect(url_for("disciplinas"))

    professores_lista = fetch_all("SELECT id, nome FROM professores ORDER BY nome")
    pesquisa = request.args.get("pesquisa", "").strip()
    filtro = ""
    params = ()
    if pesquisa:
        filtro = """
        WHERE LOWER(d.nome) LIKE LOWER(%s)
           OR LOWER(d.codigo) LIKE LOWER(%s)
           OR LOWER(p.nome) LIKE LOWER(%s)
        """
        params = (f"%{pesquisa}%", f"%{pesquisa}%", f"%{pesquisa}%")

    lista = fetch_all(
        """
        SELECT d.*, COALESCE(p.nome, 'Sem professor') AS professor,
               COUNT(m.aluno_id) AS total_alunos
          FROM disciplinas d
          LEFT JOIN professores p ON p.id = d.professor_id
          LEFT JOIN matriculas m ON m.disciplina_id = d.id AND m.ativo = 1
        {filtro}
         GROUP BY d.id, p.nome
         ORDER BY d.nome
        """.format(filtro=filtro),
        params,
    )
    return render_template(
        "disciplinas.html",
        disciplinas=lista,
        professores=professores_lista,
        pesquisa=pesquisa,
    )


@app.route("/disciplinas/<int:disciplina_id>/editar", methods=["GET", "POST"])
@requer_tipo("secretaria")
def editar_disciplina(disciplina_id):
    disciplina = fetch_one("SELECT * FROM disciplinas WHERE id = %s", (disciplina_id,))
    if not disciplina:
        flash("Disciplina nao encontrada.", "warning")
        return redirect(url_for("disciplinas"))

    professores_lista = fetch_all("SELECT id, nome FROM professores ORDER BY nome")

    if request.method == "POST":
        dados, erros = validar_campos_obrigatorios(
            {
                "nome": "Nome",
                "codigo": "Codigo",
            }
        )
        carga_horaria, erro_carga = validar_carga_horaria()
        if erro_carga:
            erros.append(erro_carga)
        if erros:
            for erro in erros:
                flash(erro, "warning")
            return redirect(url_for("editar_disciplina", disciplina_id=disciplina_id))

        professor_id = request.form.get("professor_id") or None
        try:
            execute(
                """
                UPDATE disciplinas
                   SET nome = %s, codigo = %s, carga_horaria = %s, professor_id = %s
                WHERE id = %s
                """,
                (
                    dados["nome"],
                    dados["codigo"],
                    carga_horaria,
                    professor_id,
                    disciplina_id,
                ),
            )
            flash("Disciplina atualizada com sucesso.", "success")
            return redirect(url_for("disciplinas"))
        except IntegrityError:
            flash("Ja existe disciplina com este codigo.", "warning")

    return render_template(
        "editar_disciplina.html",
        disciplina=disciplina,
        professores=professores_lista,
    )


@app.route("/matriculas", methods=["GET", "POST"])
@requer_tipo("secretaria")
def matriculas():
    if request.method == "POST":
        aluno_id = request.form.get("aluno_id")
        disciplina_id = request.form.get("disciplina_id")
        if not aluno_id or not disciplina_id:
            flash("Selecione um aluno e uma disciplina para realizar a matricula.", "warning")
            return redirect(url_for("matriculas"))

        matricula_existente = fetch_one(
            """
            SELECT id, ativo
              FROM matriculas
             WHERE aluno_id = %s AND disciplina_id = %s
            """,
            (aluno_id, disciplina_id),
        )

        if matricula_existente and matricula_existente["ativo"]:
            flash("Este aluno ja esta matriculado nessa disciplina.", "warning")
        elif matricula_existente:
            execute(
                """
                UPDATE matriculas
                   SET ativo = 1, removido_em = NULL
                 WHERE id = %s
                """,
                (matricula_existente["id"],),
            )
            flash("Matricula reativada com sucesso.", "success")
        else:
            try:
                execute(
                    """
                    INSERT INTO matriculas (aluno_id, disciplina_id, ativo)
                    VALUES (%s, %s, 1)
                    """,
                    (aluno_id, disciplina_id),
                )
                flash("Aluno matriculado com sucesso.", "success")
            except IntegrityError:
                flash("Este aluno ja esta matriculado nessa disciplina.", "warning")
        return redirect(url_for("matriculas"))

    alunos_lista = fetch_all("SELECT id, nome, matricula FROM alunos ORDER BY nome")
    disciplinas_lista = fetch_all("SELECT id, nome, codigo FROM disciplinas ORDER BY nome")
    lista = fetch_all(
        """
        SELECT m.id, a.nome AS aluno, a.matricula, d.nome AS disciplina, d.codigo
          FROM matriculas m
          JOIN alunos a ON a.id = m.aluno_id
          JOIN disciplinas d ON d.id = m.disciplina_id
         WHERE m.ativo = 1
         ORDER BY d.nome, a.nome
        """
    )
    return render_template(
        "matriculas.html",
        alunos=alunos_lista,
        disciplinas=disciplinas_lista,
        matriculas=lista,
    )


@app.route("/matriculas/<int:matricula_id>/editar", methods=["GET", "POST"])
@requer_tipo("secretaria")
def editar_matricula(matricula_id):
    matricula = fetch_one("SELECT * FROM matriculas WHERE id = %s", (matricula_id,))
    if not matricula:
        flash("Matricula nao encontrada.", "warning")
        return redirect(url_for("matriculas"))

    alunos_lista = fetch_all("SELECT id, nome, matricula FROM alunos ORDER BY nome")
    disciplinas_lista = fetch_all("SELECT id, nome, codigo FROM disciplinas ORDER BY nome")

    if request.method == "POST":
        aluno_id = request.form.get("aluno_id")
        disciplina_id = request.form.get("disciplina_id")
        if not aluno_id or not disciplina_id:
            flash("Selecione um aluno e uma disciplina para atualizar a matricula.", "warning")
            return redirect(url_for("editar_matricula", matricula_id=matricula_id))

        try:
            execute(
                """
                UPDATE matriculas
                   SET aluno_id = %s, disciplina_id = %s, ativo = 1, removido_em = NULL
                WHERE id = %s
                """,
                (
                    aluno_id,
                    disciplina_id,
                    matricula_id,
                ),
            )
            flash("Matricula atualizada com sucesso.", "success")
            return redirect(url_for("matriculas"))
        except IntegrityError:
            flash("Este aluno ja esta matriculado nessa disciplina.", "warning")

    return render_template(
        "editar_matricula.html",
        matricula=matricula,
        alunos=alunos_lista,
        disciplinas=disciplinas_lista,
    )


@app.post("/matriculas/<int:matricula_id>/excluir")
def excluir_matricula(matricula_id):
    execute(
        """
        UPDATE matriculas
           SET ativo = 0, removido_em = CURRENT_TIMESTAMP
         WHERE id = %s
        """,
        (matricula_id,),
    )
    flash("Matricula removida da interface. O registro continua no banco.", "success")
    return redirect(url_for("matriculas"))


@app.route("/notas/minhas", methods=["GET"])
@requer_tipo("aluno")
def minhas_notas():
    usuario = obter_usuario_autenticado()
    aluno_id = usuario['aluno_id']
    
    notas = fetch_all(
        """
        SELECT d.nome AS disciplina,
               d.codigo,
               n.nota,
               p.nome AS professor,
               n.atualizado_em
          FROM notas n
          JOIN disciplinas d ON d.id = n.disciplina_id
          JOIN professores p ON p.id = n.professor_id
         WHERE n.aluno_id = %s
         ORDER BY d.nome
        """,
        (aluno_id,)
    )
    
    return render_template(
        "minhas_notas.html",
        notas=notas
    )


@app.route("/notas/gerenciar", methods=["GET", "POST"])
@requer_tipo("professor")
def gerenciar_notas():
    usuario = obter_usuario_autenticado()
    professor_id = usuario['professor_id']
    
    if not professor_id:
        flash("Você não está vinculado a nenhuma disciplina.", "warning")
        return redirect(url_for("dashboard"))
    
    # Buscar alunos e disciplinas do professor
    alunos_disciplinas = fetch_all(
        """
        SELECT DISTINCT 
               m.id AS matricula_id,
               a.id AS aluno_id,
               a.nome AS aluno_nome,
               a.matricula AS aluno_matricula,
               d.id AS disciplina_id,
               d.nome AS disciplina_nome,
               COALESCE(n.nota, '') AS nota
          FROM matriculas m
          JOIN alunos a ON a.id = m.aluno_id
          JOIN disciplinas d ON d.id = m.disciplina_id
          LEFT JOIN notas n ON n.aluno_id = a.id AND n.disciplina_id = d.id
         WHERE d.professor_id = %s AND m.ativo = 1
         ORDER BY d.nome, a.nome
        """,
        (professor_id,)
    )
    
    if request.method == "POST":
        aluno_id = request.form.get("aluno_id")
        disciplina_id = request.form.get("disciplina_id")
        nota = request.form.get("nota")
        
        if not aluno_id or not disciplina_id or not nota:
            flash("Todos os campos são obrigatórios.", "warning")
            return redirect(url_for("gerenciar_notas"))
        
        try:
            nota_float = float(nota)
            if nota_float < 0 or nota_float > 10:
                flash("A nota deve estar entre 0 e 10.", "warning")
                return redirect(url_for("gerenciar_notas"))
        except ValueError:
            flash("A nota deve ser um número válido.", "warning")
            return redirect(url_for("gerenciar_notas"))
        
        # Verificar se já existe nota
        nota_existente = fetch_one(
            "SELECT id FROM notas WHERE aluno_id = %s AND disciplina_id = %s",
            (aluno_id, disciplina_id)
        )
        
        if nota_existente:
            execute(
                """
                UPDATE notas
                   SET nota = %s, atualizado_em = CURRENT_TIMESTAMP
                 WHERE aluno_id = %s AND disciplina_id = %s
                """,
                (nota_float, aluno_id, disciplina_id)
            )
            flash("Nota atualizada com sucesso.", "success")
        else:
            execute(
                """
                INSERT INTO notas (aluno_id, disciplina_id, nota, professor_id)
                VALUES (%s, %s, %s, %s)
                """,
                (aluno_id, disciplina_id, nota_float, professor_id)
            )
            flash("Nota lançada com sucesso.", "success")
        
        return redirect(url_for("gerenciar_notas"))
    
    return render_template(
        "gerenciar_notas.html",
        alunos_disciplinas=alunos_disciplinas
    )


if __name__ == "__main__":
    debug = os.getenv("FLASK_DEBUG", "").lower() in {"1", "true", "yes"}
    app.run(debug=debug)
