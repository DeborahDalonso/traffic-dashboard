# Traffic dashboard

Painel privado com os acessos ao portfólio: páginas de exemplo, perfil e repositórios do GitHub.

Página: https://deborahdalonso.github.io/traffic-dashboard/ (pede senha)

## Como funciona

- As páginas de exemplo e o perfil têm o contador do [GoatCounter](https://deborahdalonso.goatcounter.com), que guarda data e hora de cada acesso.
- O GitHub informa as visitas aos repositórios só dos últimos 14 dias, por dia. O histórico acumula esses dias.
- De hora em hora, a automação em `.github/workflows/update.yml` coleta os dados, monta a página e publica com senha (StatiCrypt).
- O histórico fica em `history.enc`, criptografado com a mesma senha.

## Segredos do repositório

| Nome | O que é |
|---|---|
| `DASHBOARD_PASSWORD` | senha do painel e do histórico |
| `GOATCOUNTER_TOKEN` | token da API do GoatCounter (Read statistics + Export) |
| `GH_TRAFFIC_TOKEN` | token do GitHub com Administration: Read-only em todos os repositórios |

O salt em `.staticrypt.json` não é segredo; mantê-lo fixo faz o "lembrar neste aparelho" sobreviver às atualizações.
