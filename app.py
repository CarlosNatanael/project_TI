from flask import Flask, render_template, request, redirect, make_response
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import zoneinfo
import csv
import io

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///tickets_ti.db'
db = SQLAlchemy(app)

def get_hora_brasil():
    return datetime.now(zoneinfo.ZoneInfo('America/Sao_Paulo'))

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
    motivo_pendencia = db.Column(db.Text)
    solucao_aplicada = db.Column(db.Text)
    data_abertura = db.Column(db.DateTime, default=get_hora_brasil)
    data_fechamento = db.Column(db.DateTime)

with app.app_context():
    db.create_all()

@app.route('/dashboard')
def dashboard():
    # Métricas gerais de status
    total_tickets = Ticket.query.count()
    abertos = Ticket.query.filter_by(status='Aberto').count()
    em_andamento = Ticket.query.filter_by(status='Em andamento').count()
    pendentes = Ticket.query.filter_by(status='Pendente').count()
    concluidos = Ticket.query.filter_by(status='Concluído').count()
    
    # Métricas por Tipo
    incidentes = Ticket.query.filter_by(tipo='Incidente').count()
    requisicoes = Ticket.query.filter_by(tipo='Requisição').count()
    
    ativos_criticos = Ticket.query.filter(Ticket.prioridade.in_(['Alta', 'Crítica']), Ticket.status != 'Concluído').count()

    return render_template('dashboard.html', 
                           total=total_tickets, abertos=abertos, em_andamento=em_andamento,
                           pendentes=pendentes, concluidos=concluidos, 
                           incidentes=incidentes, requisicoes=requisicoes,
                           criticos=ativos_criticos)

@app.route('/exportar')
def exportar():
    tickets = Ticket.query.order_by(Ticket.id.desc()).all()
    
    output_buffer = io.StringIO()
    writer = csv.writer(output_buffer, delimiter=';')

    writer.writerow([
        'Número Ticket', 'Solicitante', 'Setor', 'Assunto', 
        'Tipo', 'Prioridade', 'Status', 'Técnico', 
        'Data Abertura', 'Data Fechamento', 'Motivo Pendência', 'Solução Aplicada'
    ])
    
    for t in tickets:
        abertura = t.data_abertura.strftime('%d/%m/%Y %H:%M') if t.data_abertura else ''
        fechamento = t.data_fechamento.strftime('%d/%m/%Y %H:%M') if t.data_fechamento else ''
        
        writer.writerow([
            f"#{t.id}", t.solicitante, t.setor, t.assunto,
            t.tipo, t.prioridade, t.status, t.tecnico or 'Não Atribuído',
            abertura, fechamento, t.motivo_pendencia or '', t.solucao_aplicada or ''
        ])
    
    response_data = output_buffer.getvalue().encode('utf-8-sig')
    
    response = make_response(response_data)
    response.headers["Content-Disposition"] = "attachment; filename=relatorio_tickets_ti.csv"
    response.headers["Content-type"] = "text/csv; charset=utf-8"
    return response

@app.route('/excluir/<int:id>', methods=['GET', 'POST'])
def excluir(id):
    ticket = Ticket.query.get_or_404(id)
    db.session.delete(ticket)
    db.session.commit()
    return redirect('/consulta')

@app.route('/consulta')
def consulta():
    search = request.args.get('search', '')
    status_filtro = request.args.get('status', '')
    tecnico_filtro = request.args.get('tecnico', '')
    prioridade_filtro = request.args.get('prioridade', '')

    query = Ticket.query

    if search:
        query = query.filter(
            (Ticket.solicitante.contains(search)) | 
            (Ticket.assunto.contains(search)) |
            (Ticket.id == search if search.isdigit() else False)
        )

    if status_filtro:
        query = query.filter(Ticket.status == status_filtro)
    if tecnico_filtro:
        query = query.filter(Ticket.tecnico == tecnico_filtro)
    if prioridade_filtro:
        query = query.filter(Ticket.prioridade == prioridade_filtro)

    query = query.order_by(Ticket.status == 'Concluído', Ticket.data_abertura.desc())
    resultados = query.all()
    tecnicos = ["Lucas"]
    
    return render_template('consulta.html', chamados=resultados, tecnicos=tecnicos)

@app.route('/', methods=['GET', 'POST'])
def entrada():
    if request.method == 'POST':
        novo_ticket = Ticket(
            solicitante=request.form['solicitante'],
            setor=request.form['setor'],
            assunto=request.form['assunto'],
            descricao=request.form['descricao'],
            tipo=request.form['tipo'],
            prioridade=request.form.get('prioridade', 'Média'),
            status='Aberto'
        )
        db.session.add(novo_ticket)
        db.session.commit()
        return redirect('/consulta')
    
    return render_template('entrada.html')

@app.route('/editar/<int:id>', methods=['GET', 'POST'])
def editar(id):
    ticket = Ticket.query.get_or_404(id)
    if request.method == 'POST':
        ticket.tecnico = request.form.get('tecnico', ticket.tecnico)
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
    
    tecnicos = ["Lucas"]
    return render_template('entrada.html', ticket=ticket, tecnicos=tecnicos)

if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0")