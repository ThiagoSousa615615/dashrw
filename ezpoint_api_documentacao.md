# EzPoint Web API – Documentação de Integração

Esta documentação auxilia a integração entre o software de ponto **EzPoint Web** e sistemas parceiros.

---

## Endpoint

```
https://api.ezpointweb.com.br/ezweb-ws
```

---

## Recursos disponíveis

- `login` (POST)
- `funcionario` (GET)
- `batida` (GET)

---

# Autenticação

Para realizar a integração, é necessário possuir **usuário e senha da API** cadastrados no módulo **Admin do EzPoint Web**.

Caso ainda não possua, solicite ao representante comercial.

Após obter os dados, utilize o endpoint `login`.

---

# Login

**POST**
```
https://api.ezpointweb.com.br/ezweb-ws/login
```

### Body (JSON)

```json
{
  "empresa": "rwtech",
  "usuario": "usuarioapi",
  "senha": "senhaapi"
}
```

### Retorno

A API retorna um **hash de autenticação**.

Esse hash deve ser enviado no header de todas as próximas requisições:

```
Authorization: Bearer SEU_TOKEN_AQUI
```

---

# Funcionários

## Endpoint

```
GET https://api.ezpointweb.com.br/ezweb-ws/funcionario
```

## Listar todos os funcionários

```
https://api.ezpointweb.com.br/ezweb-ws/funcionario
```

## Listar com filtros

Exemplo:

```
https://api.ezpointweb.com.br/ezweb-ws/funcionario?empresa=rwtech&ocultarDemitidos=true&nome=Rafael
```

### Querystring

| Parâmetro | Obrigatório | Descrição |
|---|---|---|
| empresa (string) | Sim | Empresa utilizada para login |
| ocultarDemitidos (boolean) | Sim | Oculta funcionários demitidos |
| nome | Não | Nome do funcionário |
| pis | Não | PIS do funcionário |
| cpf | Não | CPF do funcionário |

### Exemplo de retorno

```json
{
  "listaDeFuncionarios": [
    {
      "matricula": "1",
      "nome": "Adriana",
      "pis": "010101010106",
      "cargo": "Analista de RH",
      "cnpjCpfEmpresa": "86708665000170"
    },
    {
      "matricula": "2",
      "nome": "Beatriz",
      "pis": "011111111116",
      "cargo": "Analista Fiscal",
      "cnpjCpfEmpresa": "86708665000170"
    }
  ]
}
```

---

# Batidas (Marcações de ponto)

## Endpoint

```
GET https://api.ezpointweb.com.br/ezweb-ws/batida
```

## Consulta com filtros

```
https://api.ezpointweb.com.br/ezweb-ws/batida?empresa=rwtech&pagina=1&dataInicio=2022-01-01&dataFim=2022-01-01
```

### Querystring

| Parâmetro | Obrigatório | Descrição |
|---|---|---|
| empresa (string) | Sim | Empresa utilizada para login |
| pagina (integer) | Sim | Página da consulta |
| dataInicio (string) | Sim | Data inicial (yyyy-MM-dd) |
| dataFim (string) | Sim | Data final (yyyy-MM-dd) |

⚠️ Período máximo permitido: **6 meses**.

### Exemplo de retorno

```json
{
  "listaDeBatidas": [
    {
      "nomeFuncionario": "Adriana",
      "pis": "010101010106",
      "matriculaFuncionario": "1",
      "data": "2022-01-01",
      "hora": "07:00:00",
      "nomeRep": "MATRIZ",
      "numeroSerieRep": "00043005620000001",
      "ipRep": "192.168.1.100"
    },
    {
      "nomeFuncionario": "Beatriz",
      "pis": "011111111116",
      "matriculaFuncionario": "2",
      "data": "2022-01-01",
      "hora": "07:30:00",
      "nomeRep": "FILIAL",
      "numeroSerieRep": "00043005620000002",
      "ipRep": "192.168.1.102"
    }
  ],
  "totalPaginas": 1
}
```

### Paginação

A API retorna:

- lista de batidas
- `totalPaginas`

A aplicação deve continuar fazendo requisições incrementando `pagina` até atingir `totalPaginas`.

---

# Limite de requisições

Máximo de **30 requisições por minuto**.

---

# Versão

| Versão | Data | Descrição |
|---|---|---|
| 1.0 | 17/02/2022 | Versão inicial |