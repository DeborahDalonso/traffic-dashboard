"""Coleta os acessos e monta a página do painel.

Lê history.json (o histórico já aberto pelo workflow), busca os dados novos
e grava de volta. Do GoatCounter vêm só os acessos novos desde a última
exportação; o GitHub só guarda 14 dias de visitas aos repositórios. O
histórico acumula os dois a cada execução.

Variáveis de ambiente:
    GOATCOUNTER_TOKEN   token da API do GoatCounter (Read statistics + Export)
    GH_TRAFFIC_TOKEN    token do GitHub com Administration: Read-only
"""
import csv
import gzip
import io
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
HISTORICO = RAIZ / "history.json"
MODELO = RAIZ / "template" / "dashboard.html"
SAIDA = RAIZ / "build" / "index.html"

GOATCOUNTER = "https://deborahdalonso.goatcounter.com/api/v0"
GITHUB = "https://api.github.com"
USUARIO = "DeborahDalonso"


def pedir(url, token, metodo="GET", corpo=None, extra=None):
    cabecalhos = {"Authorization": f"Bearer {token}", "User-Agent": "traffic-dashboard"}
    cabecalhos.update(extra or {})
    dados = None
    if corpo is not None:
        dados = json.dumps(corpo).encode()
        cabecalhos["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=dados, headers=cabecalhos, method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        e.msg = f"{e.msg} em {metodo} {url.split('?')[0]}: {e.read()[:200].decode(errors='replace')}"
        raise


def pagina_do_caminho(caminho):
    """'/bakery-landing-demo/index.html?pedido=x' -> '/bakery-landing-demo/'."""
    caminho = caminho.split("?")[0].split("#")[0]
    if caminho.startswith("/github-profile"):
        return "/github-profile"
    partes = [p for p in caminho.split("/") if p]
    return f"/{partes[0]}/" if partes else "/"


def coletar_goatcounter(token, ultimo_id):
    """Exporta em CSV os acessos posteriores a ultimo_id. A API gera o arquivo
    em segundo plano e só aceita uma exportação por hora."""
    exp = json.loads(pedir(f"{GOATCOUNTER}/export", token, "POST", {"format": "csv", "start_from_hit_id": ultimo_id}))
    for _ in range(30):
        if exp.get("finished_at"):
            break
        time.sleep(4)
        exp = json.loads(pedir(f"{GOATCOUNTER}/export/{exp['id']}", token))
    else:
        raise RuntimeError("export do GoatCounter não terminou")
    if exp.get("error"):
        raise RuntimeError(exp["error"])
    # Sem acessos novos o GoatCounter não gera arquivo, e o download daria 404.
    if not exp.get("num_rows"):
        return [], ultimo_id

    bruto = pedir(f"{GOATCOUNTER}/export/{exp['id']}/download", token)
    if bruto[:2] == b"\x1f\x8b":
        bruto = gzip.decompress(bruto)
    leitor = csv.DictReader(io.StringIO(bruto.decode("utf-8")))
    # A primeira coluna vem com o número da versão do formato na frente ("2Path").
    leitor.fieldnames = [c.lstrip("0123456789") for c in leitor.fieldnames]

    acessos = []
    for l in leitor:
        pagina = pagina_do_caminho(l["Path"])
        # A imagem do perfil é buscada pelo cache do GitHub, que o GoatCounter
        # costuma marcar como robô. Ali o robô é o próprio acesso.
        if l.get("Bot", "0") not in ("", "0") and pagina != "/github-profile":
            continue
        acessos.append({
            "t": l["Date"],
            "p": pagina,
            "r": l.get("Referrer", ""),
            "loc": l.get("Location", ""),
            "nav": l.get("Browser", ""),
            "so": l.get("System", ""),
            "s": l.get("Session", ""),
        })
    return acessos, exp.get("last_hit_id") or ultimo_id


def coletar_github(token, repos_antes):
    repos = {k: dict(v) for k, v in repos_antes.items()}
    lista, pagina = [], 1
    while True:
        lote = json.loads(pedir(f"{GITHUB}/user/repos?affiliation=owner&per_page=100&page={pagina}", token))
        lista += lote
        if len(lote) < 100:
            break
        pagina += 1
    for r in lista:
        if r["fork"]:
            continue
        nome = r["name"]
        try:
            v = json.loads(pedir(f"{GITHUB}/repos/{USUARIO}/{nome}/traffic/views", token,
                                 extra={"Accept": "application/vnd.github+json"}))
        except urllib.error.HTTPError as e:
            print(f"sem acesso ao tráfego de {nome}: {e.code}")
            continue
        dias = repos.setdefault(nome, {})
        for d in v["views"]:
            # O dia em curso ainda está crescendo; a leitura mais nova vale.
            dias[d["timestamp"][:10]] = [d["count"], d["uniques"]]
    return {k: v for k, v in sorted(repos.items()) if v}


def main():
    historico = json.loads(HISTORICO.read_text()) if HISTORICO.exists() else {}
    acessos = historico.get("hits", [])
    repos = historico.get("repos", {})
    ultimo_id = historico.get("gc_last_hit_id", 0)

    try:
        novos, ultimo_id = coletar_goatcounter(os.environ["GOATCOUNTER_TOKEN"], ultimo_id)
        acessos = sorted(acessos + novos, key=lambda a: a["t"])
    except Exception as e:  # mantém o histórico anterior e tenta de novo na próxima hora
        print(f"::warning::GoatCounter falhou: {e}")
    try:
        repos = coletar_github(os.environ["GH_TRAFFIC_TOKEN"], repos)
    except Exception as e:
        print(f"::warning::GitHub falhou: {e}")

    HISTORICO.write_text(json.dumps({"hits": acessos, "repos": repos, "gc_last_hit_id": ultimo_id}, sort_keys=True, ensure_ascii=False))

    dados = {"atualizado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "hits": acessos, "repos": repos}
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    html = MODELO.read_text(encoding="utf-8").replace(
        "/*DADOS*/null", json.dumps(dados, ensure_ascii=False).replace("</", "<\\/"))
    SAIDA.write_text(html, encoding="utf-8")
    print(f"{len(acessos)} acessos, {len(repos)} repositórios")


if __name__ == "__main__":
    main()
