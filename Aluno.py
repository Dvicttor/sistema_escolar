from Pessoa import Pessoa


class Aluno(Pessoa):
    def __init__(self, nome, cpf, matricula, curso):
        super().__init__(nome, cpf)
        self.matricula = matricula
        self.curso = curso
        self.disciplinas = []
        self.ativo = True

    def adicionar_disciplina(self, disciplina):
        if disciplina not in self.disciplinas:
            self.disciplinas.append(disciplina)

    def listar_disciplinas(self):
        if not self.disciplinas:
            return "Nenhuma disciplina matriculada."

        return ", ".join(disciplina.nome for disciplina in self.disciplinas)

    def remover_dados(self):
        for disciplina in self.disciplinas:
            if self in disciplina.alunos:
                disciplina.alunos.remove(self)

        self.disciplinas.clear()
        self.ativo = False

    def __str__(self):
        status = "ativo" if self.ativo else "removido"
        return (
            f"Aluno: {self.nome} | CPF: {self.cpf} | "
            f"Matricula: {self.matricula} | Curso: {self.curso} | "
            f"Status: {status}"
        )
