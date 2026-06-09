---
name: frontend-design
description: Diretrizes de design frontend para o Escala Médica. CSS customizado + Bootstrap Icons + Inter. Minimalista e profissional.
---

## Stack

- **CSS:** `app/static/css/app.css` — arquivo único, sem framework CSS externo
- **Ícones:** Bootstrap Icons 1.11 via CDN (`<i class="bi bi-nome">`)
- **Fonte:** Inter via Google Fonts (400, 500, 600, 700)

## Tokens de design

| Token            | Valor          | Uso                         |
|------------------|----------------|-----------------------------|
| `--primary`      | `#2563eb`      | Botões, links ativos, foco  |
| `--primary-dk`   | `#1d4ed8`      | Hover do primário           |
| `--danger`       | `#dc2626`      | Erros, delete               |
| `--success`      | `#16a34a`      | Sucesso, ativo              |
| `--warning`      | `#d97706`      | Alertas                     |
| `--bg`           | `#f8fafc`      | Fundo da página             |
| `--surface`      | `#ffffff`      | Cards, sidebar, navbar      |
| `--border`       | `#e2e8f0`      | Bordas de elementos         |
| `--text`         | `#0f172a`      | Texto principal             |
| `--text-muted`   | `#64748b`      | Texto secundário            |
| `--radius`       | `8px`          | Border-radius padrão        |

## Layout

```
┌─────────────────────────────────────────────┐
│ .app-navbar (56px, branco, borda inferior)  │
├─────────┬───────────────────────────────────┤
│         │                                   │
│ .app-   │  .app-main                        │
│ sidebar │  (fundo --bg, padding 1.75rem)    │
│ (232px) │                                   │
│ branco  │                                   │
│ borda   │                                   │
│ direita │                                   │
└─────────┴───────────────────────────────────┘
```

- Mobile (< 768px): sidebar escondida → botão hamburger → `.open` toggle

## Classes de componentes

| Classe           | Descrição                                     |
|------------------|-----------------------------------------------|
| `.app-navbar`    | Barra de topo sticky                          |
| `.app-sidebar`   | Sidebar esquerda                              |
| `.app-main`      | Conteúdo principal                            |
| `.sidebar-section` | Label de grupo na sidebar (uppercase tiny)  |
| `.sidebar-item`  | Link da sidebar; `.active` para item ativo    |
| `.page-header`   | Flex row: título + botão de ação              |
| `.kpi-card`      | Card de indicador com valor grande            |
| `.kpi-grid`      | Grid auto-fill de kpi-cards                   |
| `.empty-state`   | Estado vazio centralizado                     |
| `.form-group`    | Wrapper de campo (margin-bottom)              |
| `.form-grid`     | Grid 2 colunas para formulários               |
| `.form-error`    | Mensagem de erro inline                       |
| `.btn-outline`   | Botão neutro (borda cinza, texto muted)       |
| `.badge-medico`  | Badge verde suave                             |
| `.badge-admin`   | Badge azul suave                              |
| `.table-wrapper` | Overflow-x para tabelas responsivas           |

## Anatomia de uma página

```html
{% extends "base.html" %}
{% block content %}
<div class="page-header">
  <h1><i class="bi bi-icone"></i> Título</h1>
  <a href="..." class="btn btn-primary">Ação</a>
</div>

<div class="card">
  <div class="card-header">
    <h3>Subtítulo</h3>
    <span style="color:var(--text-muted)">N itens</span>
  </div>
  <div class="table-wrapper">
    <table>...</table>
  </div>
  <!-- OU -->
  <div class="card-body empty-state">
    <div class="empty-state__icon"><i class="bi bi-icone"></i></div>
    <h3>Sem dados</h3>
    <p>Mensagem auxiliar</p>
  </div>
</div>
{% endblock %}
```

## Ícones recomendados (Bootstrap Icons)

| Contexto      | Ícone                        |
|---------------|------------------------------|
| Dashboard     | `bi-grid-1x2`                |
| Médicos       | `bi-person-lines-fill`       |
| Locais        | `bi-hospital`                |
| Vínculos      | `bi-link-45deg`              |
| Janelas/Datas | `bi-calendar3`               |
| Trocas        | `bi-arrow-left-right`        |
| KPIs          | `bi-bar-chart-line`          |
| Confirmar     | `bi-check2-circle`           |
| Restrições    | `bi-slash-circle`            |
| Escala médico | `bi-calendar2-check`         |
| Aviso         | `bi-exclamation-triangle`    |
| Sucesso       | `bi-check-circle`            |
