from flask import Flask, render_template, request, redirect, make_response, session, flash, url_for
from instance import config
from flask_sqlalchemy import SQLAlchemy
from collections import Counter
from datetime import datetime
from sqlalchemy import func
from functools import wraps
import zoneinfo
import csv
import os
import io

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///tickets_ti.db'
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'chave_padrao_para_testes')

SENHA_TI = config.SENHA_TI
db = SQLAlchemy(app)

def get_hora_brasil():
    return datetime.now(zoneinfo.ZoneInfo('America/Sao_Paulo'))

class Tag(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(50), nullable=False, unique=True)
    cor = db.Column(db.String(20), nullable=False, default='#8e44ad')

class Ticket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    solicitante = db.Column(db.String(100), nullable=False)
    setor = db.Column(db.String(50), nullable=False)
    assunto = db.Column(db.String(100), nullable=False)
    descricao = db.Column(db.Text, nullable=False)
    tipo = db.Column(db.String(20), nullable=False) 
    prioridade = db.Column(db.String(20), default='Média') 
    tecnico = db.Column(db.String(50), default='Lucas')
    status = db.Column(db.String(20), default='Aberto') 
    tags = db.Column(db.String(200), default='') 
    motivo_pendencia = db.Column(db.Text)
    solucao_aplicada = db.Column(db.Text)
    data_abertura = db.Column(db.DateTime, default=get_hora_brasil)
    data_fechamento = db.Column(db.DateTime)

with app.app_context():
    db.create_all()

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logado' not in session:
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        senha_digitada = request.form.get('senha')
        if senha_digitada == SENHA_TI:
            session['logado'] = True
            return redirect('/')
        else:
            flash('Senha incorreta. Acesso negado.')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logado', None)
    return redirect('/login')

@app.route('/tags', methods=['GET', 'POST'])
@login_required
def gerenciar_tags():
    if request.method == 'POST':
        nome_raw = request.form.get('nome')
        if not nome_raw:
            return redirect('/tags')
            
        nome = nome_raw.strip()
        cor = request.form.get('cor')
        if nome:
            existe = Tag.query.filter_by(nome=nome).first()
            if not existe:
                nova_tag = Tag(nome=nome, cor=cor)
                db.session.add(nova_tag)
                db.session.commit()
        return redirect('/tags')
    
    tags = Tag.query.all()
    return render_template('tags.html', tags=tags)

@app.route('/tags/excluir/<int:id>', methods=['POST'])
@login_required
def excluir_tag(id):
    tag = Tag.query.get_or_404(id)
    db.session.delete(tag)
    db.session.commit()
    return redirect('/tags')

@app.route('/')
@login_required
def dashboard():
    total_tickets = Ticket.query.count()
    abertos = Ticket.query.filter_by(status='Aberto').count()
    em_andamento = Ticket.query.filter_by(status='Em andamento').count()
    pendentes = Ticket.query.filter_by(status='Pendente').count()
    concluidos = Ticket.query.filter_by(status='Concluído').count()
    
    incidentes = Ticket.query.filter_by(tipo='Incidente').count()
    requisicoes = Ticket.query.filter_by(tipo='Requisição').count()
    ativos_criticos = Ticket.query.filter(Ticket.prioridade.in_(['Alta', 'Crítica']), Ticket.status != 'Concluído').count()

    setor_data = db.session.query(Ticket.setor, func.count(Ticket.id)).group_by(Ticket.setor).all()
    labels_setor = [s[0] for s in setor_data]
    valores_setor = [s[1] for s in setor_data]
    
    todos_tickets = Ticket.query.with_entities(Ticket.tags).all()
    contador_tags = Counter()
    
    for t in todos_tickets:
        if t.tags:
            tags_lista = [tag.strip() for tag in t.tags.split(',') if tag.strip()]
            contador_tags.update(tags_lista)
    
    tags_comuns = contador_tags.most_common(10)
    labels_tags = [t[0] for t in tags_comuns]
    valores_tags = [t[1] for t in tags_comuns]

    cores_banco = {t.nome: t.cor for t in Tag.query.all()}
    cores_grafico = [cores_banco.get(tag, '#3498db') for tag in labels_tags]

    return render_template('dashboard.html', 
                           total=total_tickets, abertos=abertos, em_andamento=em_andamento,
                           pendentes=pendentes, concluidos=concluidos, 
                           incidentes=incidentes, requisicoes=requisicoes,
                           criticos=ativos_criticos,
                           labels_setor=labels_setor, valores_setor=valores_setor,
                           labels_tags=labels_tags, valores_tags=valores_tags,
                           cores_grafico=cores_grafico)

@app.route('/exportar')
@login_required
def exportar():
    tickets = Ticket.query.order_by(Ticket.id.desc()).all()
    output_buffer = io.StringIO()
    writer = csv.writer(output_buffer, delimiter=';')

    writer.writerow(['Número Ticket', 'Solicitante', 'Setor', 'Assunto', 'Tags', 'Tipo', 'Prioridade', 'Status', 'Técnico', 'Data Abertura', 'Data Fechamento', 'Motivo Pendência', 'Solução Aplicada'])
    
    for t in tickets:
        abertura = t.data_abertura.strftime('%d/%m/%Y %H:%M') if t.data_abertura else ''
        fechamento = t.data_fechamento.strftime('%d/%m/%Y %H:%M') if t.data_fechamento else ''
        writer.writerow([f"#{t.id}", t.solicitante, t.setor, t.assunto, t.tags, t.tipo, t.prioridade, t.status, t.tecnico or 'Não Atribuído', abertura, fechamento, t.motivo_pendencia or '', t.solucao_aplicada or ''])
    
    response_data = output_buffer.getvalue().encode('utf-8-sig')
    response = make_response(response_data)
    response.headers["Content-Disposition"] = "attachment; filename=relatorio_tickets_ti.csv"
    response.headers["Content-type"] = "text/csv; charset=utf-8"
    return response

@app.route('/excluir/<int:id>', methods=['POST'])
@login_required
def excluir(id):
    ticket = Ticket.query.get_or_404(id)
    db.session.delete(ticket)
    db.session.commit()
    return redirect('/consulta')

@app.route('/consulta')
@login_required
def consulta():
    search = request.args.get('search', '')
    status_filtro = request.args.get('status', '')
    prioridade_filtro = request.args.get('prioridade', '')
    tag_filtro = request.args.get('tag', '')
    setor_filtro = request.args.get('setor', '')
    
    page = request.args.get('page', 1, type=int)
    query = Ticket.query

    if search:
        query = query.filter((Ticket.solicitante.contains(search)) | (Ticket.assunto.contains(search)) | (Ticket.id == search if search.isdigit() else False) | (Ticket.tags.contains(search)))
    if status_filtro:
        query = query.filter(Ticket.status == status_filtro)
    if prioridade_filtro:
        query = query.filter(Ticket.prioridade == prioridade_filtro)
    if tag_filtro:
        query = query.filter(Ticket.tags.contains(tag_filtro))
    if setor_filtro:
        query = query.filter(Ticket.setor == setor_filtro)

    query = query.order_by(Ticket.status == 'Concluído', Ticket.data_abertura.desc())
    chamados_paginados = query.paginate(page=page, per_page=15, error_out=False)

    cores_tags = {t.nome: t.cor for t in Tag.query.all()}

    return render_template('consulta.html', chamados=chamados_paginados, cores_tags=cores_tags, tag_ativa=tag_filtro)

@app.route('/novo', methods=['GET', 'POST'])
@login_required
def entrada():
    if request.method == 'POST':
        tags_selecionadas = ','.join(request.form.getlist('tags'))
        novo_ticket = Ticket(
            solicitante=request.form['solicitante'],
            setor=request.form['setor'],
            assunto=request.form['assunto'],
            descricao=request.form['descricao'],
            tipo=request.form['tipo'],
            tags=tags_selecionadas,
            prioridade=request.form.get('prioridade', 'Média'),
            status='Aberto'
        )
        db.session.add(novo_ticket)
        db.session.commit()
        return redirect('/consulta')
    
    tags_disponiveis = Tag.query.all()
    return render_template('entrada.html', tags_disponiveis=tags_disponiveis, tags_ativas=[])

@app.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar(id):
    ticket = Ticket.query.get_or_404(id)
    
    if request.method == 'POST':
        ticket.solicitante = request.form.get('solicitante', ticket.solicitante)
        ticket.setor = request.form.get('setor', ticket.setor)
        ticket.assunto = request.form.get('assunto', ticket.assunto)
        ticket.tipo = request.form.get('tipo', ticket.tipo)
        ticket.descricao = request.form.get('descricao', ticket.descricao)
        ticket.tags = ','.join(request.form.getlist('tags'))
        novo_tecnico = request.form.get('tecnico')
        if novo_tecnico and novo_tecnico.strip() != "":
            ticket.tecnico = novo_tecnico.strip()
        ticket.status = request.form.get('status', ticket.status)
        ticket.prioridade = request.form.get('prioridade', ticket.prioridade)
        ticket.motivo_pendencia = request.form.get('motivo_pendencia', '')
        ticket.solucao_aplicada = request.form.get('solucao_aplicada', '')

        if ticket.status == 'Concluído' and not ticket.data_fechamento:
            ticket.data_fechamento = get_hora_brasil()
        elif ticket.status != 'Concluído':
            ticket.data_fechamento = None
            
        db.session.commit()
        return redirect('/consulta')
    
    tags_disponiveis = Tag.query.all()
    tags_ativas = [t.strip() for t in ticket.tags.split(',')] if ticket.tags else []
    return render_template('entrada.html', ticket=ticket, tags_disponiveis=tags_disponiveis, tags_ativas=tags_ativas)

if __name__ == '__main__':
    app.run(debug=False)