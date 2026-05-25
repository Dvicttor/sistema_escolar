import os
from functools import wraps
from flask import session, redirect, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash
from db import execute, fetch_one, IntegrityError


def hash_password(password):
    """Gera um hash seguro para a senha."""
    return generate_password_hash(password)


def verify_password(password, password_hash):
    """Verifica se a senha corresponde ao hash."""
    return check_password_hash(password_hash, password)


def obter_usuario_autenticado():
    """Retorna os dados do usuário autenticado da sessão."""
    usuario_id = session.get('usuario_id')
    if not usuario_id:
        return None
    
    usuario = fetch_one(
        "SELECT id, username, email, tipo, professor_id, aluno_id FROM usuarios WHERE id = %s AND ativo = 1",
        (usuario_id,)
    )
    return usuario


def login_usuario(username, senha):
    """
    Realiza login do usuário.
    Retorna dict com sucesso e mensagem.
    """
    usuario = fetch_one(
        "SELECT id, username, email, tipo, senha_hash, professor_id, aluno_id FROM usuarios WHERE username = %s AND ativo = 1",
        (username,)
    )
    
    if not usuario:
        return {
            'sucesso': False,
            'mensagem': 'Usuario ou senha incorretos.'
        }
    
    if not verify_password(senha, usuario['senha_hash']):
        return {
            'sucesso': False,
            'mensagem': 'Usuario ou senha incorretos.'
        }
    
    session['usuario_id'] = usuario['id']
    session['username'] = usuario['username']
    session['tipo'] = usuario['tipo']
    session['professor_id'] = usuario['professor_id']
    session['aluno_id'] = usuario['aluno_id']
    
    return {
        'sucesso': True,
        'mensagem': 'Login realizado com sucesso.',
        'tipo': usuario['tipo']
    }


def logout_usuario():
    """Realiza logout do usuário."""
    session.clear()


def registrar_usuario(username, email, senha, tipo, professor_id=None, aluno_id=None):
    """
    Registra um novo usuário.
    Retorna dict com sucesso e mensagem.
    """
    if len(senha) < 6:
        return {
            'sucesso': False,
            'mensagem': 'A senha deve ter pelo menos 6 caracteres.'
        }
    
    senha_hash = hash_password(senha)
    
    try:
        execute(
            """
            INSERT INTO usuarios (username, email, senha_hash, tipo, professor_id, aluno_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (username, email, senha_hash, tipo, professor_id, aluno_id)
        )
        return {
            'sucesso': True,
            'mensagem': 'Usuario registrado com sucesso.'
        }
    except IntegrityError as e:
        erro_msg = str(e)
        if 'username' in erro_msg:
            return {
                'sucesso': False,
                'mensagem': 'Este nome de usuario ja existe.'
            }
        elif 'email' in erro_msg:
            return {
                'sucesso': False,
                'mensagem': 'Este email ja existe.'
            }
        else:
            return {
                'sucesso': False,
                'mensagem': f'Erro ao registrar usuario: {erro_msg}'
            }


def requer_autenticacao(f):
    """Decorator para proteger rotas que requerem autenticação."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not obter_usuario_autenticado():
            flash('Voce precisa estar autenticado para acessar esta pagina.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def requer_tipo(tipo_requerido):
    """Decorator para proteger rotas por tipo de usuario."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            usuario = obter_usuario_autenticado()
            if not usuario:
                flash('Voce precisa estar autenticado.', 'warning')
                return redirect(url_for('login'))
            
            if usuario['tipo'] not in (tipo_requerido if isinstance(tipo_requerido, (list, tuple)) else [tipo_requerido]):
                flash('Voce nao tem permissao para acessar esta pagina.', 'warning')
                return redirect(url_for('dashboard'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator
