# Sistema Academico Web

Interface web em Flask para cadastrar alunos, professores, disciplinas e
matriculas usando MySQL.

O objetivo do sistema e ajudar a secretaria, professores e alunos a organizar
cadastros academicos, vinculos de matricula, pesquisas e relatorios.

Se o MySQL nao estiver instalado ou iniciado, a aplicacao usa automaticamente
um banco SQLite local chamado `sistema_academico.sqlite3`, para permitir testar
a interface sem travar na conexao.

## 1. Criar o banco

No MySQL, execute:

```bash
mysql -u root -p < schema.sql
```

O script cria o banco `sistema_academico`, as tabelas e alguns dados iniciais.

## 2. Instalar dependencias

```bash
python3 -m pip install -r requirements.txt
```

## 3. Configurar conexao

Por padrao, a aplicacao usa:

```text
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=
MYSQL_DATABASE=sistema_academico
```

Se precisar, defina as variaveis antes de iniciar:

```bash
export MYSQL_USER=root
export MYSQL_PASSWORD=sua_senha
export MYSQL_DATABASE=sistema_academico
```

Para uso fora do ambiente de testes, configure tambem:

```bash
export FLASK_SECRET_KEY=uma_chave_segura
export FLASK_DEBUG=0
```

## 4. Rodar a interface

```bash
python3 app.py
```

Depois acesse:

```text
http://127.0.0.1:5000
```

Para obrigar o uso do MySQL e desativar o modo SQLite local:

```bash
MYSQL_REQUIRED=1 python3 app.py
```

## Funcionalidades principais

- Cadastro, listagem e edicao de alunos, professores e disciplinas.
- Pesquisa de alunos por nome.
- Pesquisa de professores por nome, registro ou area.
- Pesquisa de disciplinas por nome, codigo ou professor.
- Matricula de alunos em disciplinas sem duplicidade.
- Remocao de matricula pela interface mantendo historico no banco.
- Relatorios em PDF e JSON.
- Validacao de campos obrigatorios, CPF e carga horaria.

## Arquivos adicionados

- `app.py`: rotas da aplicacao Flask.
- `db.py`: conexao e funcoes simples para consultar o MySQL.
- `schema.sql`: criacao do banco e tabelas.
- `templates/`: telas HTML.
- `static/styles.css`: estilo visual da interface.
